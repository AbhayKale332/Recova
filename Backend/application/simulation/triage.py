"""Would production spend an advisory model call on this case, and where did it land?

The batch runs the real graph with the *deterministic* diagnosis engine, because
one live model call per case would dominate the latency the console is measuring
and hit a rate limit mid-demo (see ``runner._run_one``). That is the right call
for the run, but it hides a question a judge will ask: *of these 200 cases, how
many actually need the LLM?*

This module answers it without making a call. ``assess`` mirrors the raisers the
real ``model_router`` already uses - stakes and guardrail proximity - and adds
the two signals that mean a cheap deterministic guess is genuinely shaky: a
free-text customer reply the compliance screen could not classify, and a failure
class with no machine telemetry to diagnose from.

``disposition`` then places each finished case in exactly one *outcome* lane:

    closed      reached a terminal resolution on its own (RECOVERED / CANCELLED / FAILED)
    human       handed to a person (ESCALATED)
    postponed   deferred by a timing rule (WAITING - quiet hours / salary window)
    in_flight   still open when the run ended

``llm`` is reported alongside those, not as one of them: a case can consult the
model and still close without a human, so it overlaps every lane.

Pure and model-free on purpose: it is evidence about routing, so it must not
itself depend on a provider being reachable.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from application.constants import TransactionLifecycleState
from application.operations.batch_seed import class_profile
from application.operations.compliance_rules import (
    RBI_MAX_RETRIES,
    VOICE_ATTEMPT_CAP,
    screen_user_message,
)
from application.settings import settings
from application.simulation.scenario import PlannedCase

# Plain-language reasons, so the console can show *why* a case was routed to the
# model rather than just a count.
REASON_FREE_TEXT = "free-text reply the screen could not classify"
REASON_NO_TELEMETRY = "no machine signal to diagnose from"
REASON_STAKES = "high value at stake"
REASON_GUARDRAIL = "one step from a guardrail"

LANE_CLOSED = "closed"
LANE_HUMAN = "human"
LANE_POSTPONED = "postponed"
LANE_IN_FLIGHT = "in_flight"

_CLOSED_STATES = frozenset(
    {
        TransactionLifecycleState.RECOVERED.value,
        TransactionLifecycleState.CANCELLED.value,
        TransactionLifecycleState.FAILED.value,
    }
)


@dataclass(frozen=True)
class ModelNeed:
    """Whether an advisory model call is warranted for one case, and why."""

    needs_model: bool
    reasons: list[str] = field(default_factory=list)


def assess(case: PlannedCase) -> ModelNeed:
    """Decide whether production would route this case to the advisory model.

    Any one signal is enough. The bulk of a book - a clean rail timeout at a
    routine amount, retries unspent, no customer message to interpret - trips
    none of them and stays on the deterministic path.
    """
    reasons: list[str] = []

    message = case.user_message
    if message and screen_user_message(message).disposition == "CONTINUE":
        # The deterministic screen catches a clean opt-out / cancel / dispute on
        # its own. Anything it lets through is free text whose intent only a
        # model can read - a promise-to-pay date, a partial offer, a complaint.
        reasons.append(REASON_FREE_TEXT)

    if class_profile(case.failure_class)["error_code"] is None:
        # An invoice drifting overdue carries no gateway error code. The root
        # cause - approval lag vs. a dispute brewing vs. an AP outage - is a
        # judgement call, which is exactly what the advisory model is for.
        reasons.append(REASON_NO_TELEMETRY)

    if case.amount_inr >= settings.router_stakes_threshold_inr:
        reasons.append(REASON_STAKES)

    if (
        case.retries_used == RBI_MAX_RETRIES - 1
        or case.voice_attempts == VOICE_ATTEMPT_CAP - 1
    ):
        reasons.append(REASON_GUARDRAIL)

    return ModelNeed(needs_model=bool(reasons), reasons=reasons)


def disposition(final_state: str) -> str:
    """Place a finished case in exactly one outcome lane."""
    if final_state == TransactionLifecycleState.ESCALATED.value:
        return LANE_HUMAN
    if final_state == TransactionLifecycleState.WAITING.value:
        return LANE_POSTPONED
    if final_state in _CLOSED_STATES:
        return LANE_CLOSED
    return LANE_IN_FLIGHT


def summarise(
    entries: Iterable[tuple[bool, list[str], str]],
    *,
    live_diagnosis: bool,
) -> dict:
    """Aggregate ``(needs_model, reasons, lane)`` per case into the routing block.

    ``closed + human + postponed + in_flight`` sums to the case total. ``llm``
    sits outside that sum - a case can need a model call and still close on its
    own - and answers the headline question directly: of N cases, how many would
    production hand to the LLM.
    """
    rows = list(entries)
    total = len(rows)
    lanes = Counter(lane for _, _, lane in rows)

    reason_counts: Counter[str] = Counter()
    llm = 0
    for needs, reasons, _ in rows:
        if needs:
            llm += 1
            reason_counts.update(reasons)

    return {
        "total": total,
        # Advisory-model escalation - overlaps every outcome lane below.
        "llm": llm,
        "llm_share": round(llm / total, 4) if total else 0.0,
        "deterministic_only": total - llm,
        # Outcome lanes - mutually exclusive, sum to total.
        "closed": lanes[LANE_CLOSED],
        "human": lanes[LANE_HUMAN],
        "postponed": lanes[LANE_POSTPONED],
        "in_flight": lanes[LANE_IN_FLIGHT],
        # A batch run keeps diagnosis offline unless the operator opts in, so the
        # console can show the model calls the run saved against production.
        "model_calls_made": llm if live_diagnosis else 0,
        "model_calls_saved": 0 if live_diagnosis else llm,
        "llm_reasons": dict(reason_counts),
    }
