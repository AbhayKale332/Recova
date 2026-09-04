"""Closed agent tool set and the deterministic gates around each proposal.

The first four channel pairings mirror ``_PLAYBOOK_ACTION`` in
``workflow/workflow_nodes.py`` and must stay consistent with it.  ``AgentTool``
is intentionally its own enum: ``InterventionAction`` is the closed set of
things that reach a channel adapter, while ``SCHEDULE_RETRY``,
``HANDOFF_TO_HUMAN``, and ``STOP`` are dispositions that never dispatch.

The model proposes a tool; quiet hours, retry/voice caps, and the live merchant
policy remain deterministic and run in that order before any channel action is
accepted.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from numbers import Real
from typing import Any

from sqlalchemy.orm import Session

from application.constants import (
    ActionType,
    FailureClass,
    InterventionAction,
    InterventionChannel,
    NodeName,
    Outcome,
    StoppingRule,
    TransactionLifecycleState,
)
from application.entities import AuditTrail, TransactionState
from application.helpers import next_quiet_hours_end, next_salary_window, now_ist as _now_ist
from application.operations import policy_repository
from application.operations.audit_service import record_audit
from application.operations.compliance_rules import (
    VOICE_ATTEMPT_CAP,
    is_within_quiet_hours,
    retry_cap_exceeded,
    voice_attempts_exhausted,
)
from application.operations.diagnosis_service import _DEFAULT_PLAYBOOK
from application.operations.escalation_service import enqueue_escalation
from application.operations.model_router import (
    ModelRouter,
    ProviderUnavailable,
    RouteDecision,
    explain_route,
    router,
)
from application.operations.policy_guard import PolicySandbox, ProposedAction
from application.workflow.workflow_nodes import _PLAYBOOK_ACTION

logger = logging.getLogger(__name__)


class AgentTool(str, Enum):
    """The closed set of tools the DECIDE prompt is allowed to propose."""

    SEND_WHATSAPP = "SEND_WHATSAPP"
    VOICE_CALL = "VOICE_CALL"
    GENERATE_PAYMENT_LINK = "GENERATE_PAYMENT_LINK"
    OFFER_FEE_WAIVER = "OFFER_FEE_WAIVER"
    SCHEDULE_RETRY = "SCHEDULE_RETRY"
    HANDOFF_TO_HUMAN = "HANDOFF_TO_HUMAN"
    STOP = "STOP"


@dataclass(frozen=True)
class AgentDecision:
    """The model proposal after routing and deterministic gate evaluation."""

    tool: AgentTool
    action: InterventionAction | None
    channel: InterventionChannel | None
    terminal_state: TransactionLifecycleState | None
    allowed: bool
    reason: str
    stopping_rule: StoppingRule | None
    route_decision: RouteDecision
    model_reason: str = ""
    sandbox_reason: str | None = None
    message: str | None = None
    discount_pct: float | None = None
    requested_tool: AgentTool | None = None
    scheduled_for: str | None = None

    @property
    def state(self) -> TransactionLifecycleState | None:
        """Alias used by callers that treat WAITING as a resolved state."""
        return self.terminal_state

    @property
    def armed_rule(self) -> StoppingRule | None:
        return self.stopping_rule

    @property
    def route(self) -> RouteDecision:
        return self.route_decision

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("tool", "action", "channel", "terminal_state", "stopping_rule", "requested_tool"):
            item = value[key]
            value[key] = item.value if isinstance(item, Enum) else item
        value["route_decision"] = self.route_decision.as_dict()
        return value


_TOOL_RESOLUTION: dict[
    AgentTool, tuple[InterventionAction | None, InterventionChannel | None, TransactionLifecycleState | None]
] = {
    AgentTool.SEND_WHATSAPP: (
        InterventionAction.SEND_WHATSAPP,
        InterventionChannel.WHATSAPP,
        None,
    ),
    AgentTool.VOICE_CALL: (InterventionAction.VOICE_CALL, InterventionChannel.VOICE, None),
    AgentTool.GENERATE_PAYMENT_LINK: (
        InterventionAction.GENERATE_PAYMENT_LINK,
        InterventionChannel.PAYMENT_LINK,
        None,
    ),
    AgentTool.OFFER_FEE_WAIVER: (
        InterventionAction.OFFER_FEE_WAIVER,
        InterventionChannel.WHATSAPP,
        None,
    ),
    AgentTool.SCHEDULE_RETRY: (
        InterventionAction.RETRY_CHARGE,
        None,
        TransactionLifecycleState.WAITING,
    ),
    AgentTool.HANDOFF_TO_HUMAN: (None, None, TransactionLifecycleState.ESCALATED),
    AgentTool.STOP: (None, None, TransactionLifecycleState.CANCELLED),
}


def _tool_for_playbook(playbook) -> AgentTool:
    action, channel = _PLAYBOOK_ACTION[playbook]
    for tool, (tool_action, tool_channel, _state) in _TOOL_RESOLUTION.items():
        if tool_action == action and tool_channel == channel:
            return tool
    raise ValueError(f"No AgentTool mapping for playbook {playbook!r}")


def _voice_attempt_count(db: Session, transaction_id: str) -> int:
    rows = (
        db.query(AuditTrail)
        .filter(
            AuditTrail.transaction_id == transaction_id,
            AuditTrail.action_type == ActionType.INTERVENTION_DISPATCH,
        )
        .all()
    )
    return sum(1 for row in rows if (row.payload or {}).get("channel") == InterventionChannel.VOICE.value)


def _set_state(
    db: Session,
    txn: TransactionState,
    state: TransactionLifecycleState,
    *,
    action_type: ActionType,
    payload: dict[str, Any],
    outcome: Outcome = Outcome.SUCCESS,
) -> None:
    txn.current_state = state
    db.commit()
    record_audit(
        db,
        transaction_id=txn.transaction_id,
        node_name=NodeName.EXECUTE_INTERVENTION,
        action_type=action_type,
        payload=payload,
        outcome=outcome,
    )


def _decide_prompt(
    txn: TransactionState,
    failure_class: FailureClass,
    *,
    policy: dict[str, Any],
    voice_attempts: int,
) -> str:
    offered = ", ".join(tool.value for tool in AgentTool)
    return "\n".join(
        [
            "You are the decision layer of a payment-recovery agent.",
            f"The failure class is {failure_class.name} ({failure_class.value}).",
            f"The transaction amount is ₹{txn.amount_minor / 100:,.2f}.",
            f"Retries already used: {txn.retry_count} of {txn.max_retries}.",
            f"Voice attempts already used: {voice_attempts} of {VOICE_ATTEMPT_CAP}.",
            f"The merchant policy discount cap is {policy['max_discount_pct']}%.",
            f"Choose exactly one tool from: {offered}.",
            'Return STRICT JSON: {"tool": string, "reason": string, "message": string|null, '
            '"discount_pct": number|null, "confidence": number}.',
            "Never invent a tool, widen the policy, or treat a disposition as a channel dispatch.",
        ]
    )


def _route_fallback(task: str, **kwargs: Any) -> RouteDecision:
    return explain_route(task, **kwargs)


def decide_tool(
    db: Session,
    transaction_id: str,
    *,
    failure_class: FailureClass | int | None = None,
    voice_attempts: int | None = None,
    discount_pct: float | None = None,
    proposed_discount_pct: float | None = None,
    now_ist: datetime | None = None,
    model_router: ModelRouter | None = None,
    sandbox: PolicySandbox | None = None,
) -> AgentDecision:
    """Route DECIDE, coerce its closed tool, and apply the existing gates.

    This function deliberately does not dispatch a channel action. Part 3 owns
    the interactive session and can use the resolved action/channel after this
    function has proven that the proposal is allowed.
    """
    txn = db.query(TransactionState).filter_by(transaction_id=transaction_id).one_or_none()
    if txn is None:
        raise ValueError(f"Unknown transaction: {transaction_id!r}")

    fc = FailureClass(failure_class if failure_class is not None else txn.failure_class)
    policy = policy_repository.get_policy(db)
    attempts = _voice_attempt_count(db, transaction_id) if voice_attempts is None else int(voice_attempts)
    amount_inr = float(txn.amount_minor) / 100
    active_router = model_router or router
    prompt = _decide_prompt(txn, fc, policy=policy, voice_attempts=attempts)
    route_discount = proposed_discount_pct if proposed_discount_pct is not None else discount_pct
    route_kwargs = {
        "amount_inr": amount_inr,
        "retries_used": int(txn.retry_count),
        "voice_attempts": attempts,
        "discount_pct": route_discount,
        "policy_cap_pct": policy["max_discount_pct"],
    }

    routed: Any = None
    route_decision: RouteDecision
    try:
        routed = active_router.call("DECIDE", prompt, **route_kwargs)
        route_decision = routed.decision
        payload = json.loads(routed.result)
        if not isinstance(payload, dict):
            raise ValueError("DECIDE response must be a JSON object")
    except ProviderUnavailable as exc:
        logger.warning("DECIDE providers unavailable; applying the class default tool: %s", exc)
        route_decision = getattr(exc, "decision", None) or _route_fallback("DECIDE", **route_kwargs)
        payload = {}
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("DECIDE response parsing failed (%s); applying the class default tool.", exc)
        route_decision = (
            routed.decision
            if routed is not None and getattr(routed, "decision", None) is not None
            else _route_fallback("DECIDE", **route_kwargs)
        )
        payload = {}

    raw_tool = payload.get("tool")
    try:
        # Coerce directly through the enum before mapping, validating, or logging
        # any proposed action so an unoffered string cannot widen permissions.
        proposed_tool = AgentTool(raw_tool)
    except (TypeError, ValueError):
        default_playbook = _DEFAULT_PLAYBOOK[fc]
        logger.warning(
            "The model returned unsupported tool %r; applying the deterministic class default.",
            raw_tool,
        )
        proposed_tool = _tool_for_playbook(default_playbook)

    model_reason = str(payload.get("reason") or "")
    message = payload.get("message")
    message = str(message) if message is not None else None
    raw_discount = payload.get("discount_pct", route_discount)
    # Preserve an integer percentage so PolicySandbox's user-facing sentence
    # remains exactly "Discount 20% ...", rather than changing it to 20.0%.
    if isinstance(raw_discount, Real) and not isinstance(raw_discount, bool):
        discount_pct = int(raw_discount) if float(raw_discount).is_integer() else float(raw_discount)
    else:
        discount_pct = None
    action, channel, default_state = _TOOL_RESOLUTION[proposed_tool]

    if proposed_tool == AgentTool.HANDOFF_TO_HUMAN:
        reason = model_reason or "The agent requested human review."
        enqueue_escalation(db, transaction_id=transaction_id, reason=reason)
        _set_state(
            db,
            txn,
            TransactionLifecycleState.ESCALATED,
            action_type=ActionType.ESCALATION,
            payload={"agent_tool": proposed_tool.value, "reason": reason},
            outcome=Outcome.ESCALATED,
        )
        return AgentDecision(
            proposed_tool,
            None,
            None,
            TransactionLifecycleState.ESCALATED,
            True,
            reason,
            None,
            route_decision,
            model_reason=model_reason,
            message=message,
            discount_pct=discount_pct,
            requested_tool=proposed_tool,
        )

    if proposed_tool == AgentTool.STOP:
        reason = model_reason or "The agent stopped the recovery workflow."
        _set_state(
            db,
            txn,
            TransactionLifecycleState.CANCELLED,
            action_type=ActionType.STATE_TRANSITION,
            payload={"agent_tool": proposed_tool.value, "reason": reason},
        )
        return AgentDecision(
            proposed_tool,
            None,
            None,
            TransactionLifecycleState.CANCELLED,
            True,
            reason,
            None,
            route_decision,
            model_reason=model_reason,
            message=message,
            discount_pct=discount_pct,
            requested_tool=proposed_tool,
        )

    # Precedence is intentionally identical to workflow_nodes.execute:
    # quiet hours -> retry cap -> voice cap -> PolicySandbox.validate().
    clock = now_ist or _now_ist()
    if channel is not None and is_within_quiet_hours(clock):
        resume_at = next_quiet_hours_end(clock)
        reason = f"TRAI quiet hours - no contact until {resume_at.strftime('%H:%M')} IST."
        _set_state(
            db,
            txn,
            TransactionLifecycleState.WAITING,
            action_type=ActionType.RETRY_SCHEDULED,
            payload={
                "agent_tool": proposed_tool.value,
                "stopping_rule": StoppingRule.TRAI_QUIET_HOURS.value,
                "reason": reason,
                "scheduled_for": resume_at.isoformat(),
                "deferred_action": action.value,
            },
        )
        return AgentDecision(
            proposed_tool,
            action,
            channel,
            TransactionLifecycleState.WAITING,
            False,
            reason,
            StoppingRule.TRAI_QUIET_HOURS,
            route_decision,
            model_reason=model_reason,
            sandbox_reason=reason,
            message=message,
            discount_pct=discount_pct,
            requested_tool=proposed_tool,
        )

    if action == InterventionAction.RETRY_CHARGE and retry_cap_exceeded(
        int(txn.retry_count), int(txn.max_retries)
    ):
        reason = f"RBI retry cap reached ({txn.retry_count} of {txn.max_retries} retries)."
        _set_state(
            db,
            txn,
            TransactionLifecycleState.CANCELLED,
            action_type=ActionType.STATE_TRANSITION,
            payload={
                "agent_tool": proposed_tool.value,
                "stopping_rule": StoppingRule.RBI_MAX_RETRIES.value,
                "reason": reason,
            },
        )
        return AgentDecision(
            proposed_tool,
            action,
            channel,
            TransactionLifecycleState.CANCELLED,
            False,
            reason,
            StoppingRule.RBI_MAX_RETRIES,
            route_decision,
            model_reason=model_reason,
            sandbox_reason=reason,
            message=message,
            discount_pct=discount_pct,
            requested_tool=proposed_tool,
        )

    if channel == InterventionChannel.VOICE and voice_attempts_exhausted(attempts):
        reason = f"Voice attempt cap reached ({attempts} of {VOICE_ATTEMPT_CAP} calls in 72 hours)."
        _set_state(
            db,
            txn,
            TransactionLifecycleState.CANCELLED,
            action_type=ActionType.STATE_TRANSITION,
            payload={
                "agent_tool": proposed_tool.value,
                "stopping_rule": StoppingRule.VOICE_ATTEMPT_CAP.value,
                "reason": reason,
            },
        )
        return AgentDecision(
            proposed_tool,
            action,
            channel,
            TransactionLifecycleState.CANCELLED,
            False,
            reason,
            StoppingRule.VOICE_ATTEMPT_CAP,
            route_decision,
            model_reason=model_reason,
            sandbox_reason=reason,
            message=message,
            discount_pct=discount_pct,
            requested_tool=proposed_tool,
        )

    policy_decision = (sandbox or policy_repository.sandbox_for(db)).validate(
        ProposedAction(
            action=action,
            channel=channel,
            discount_pct=discount_pct,
            amount_minor=txn.amount_minor,
        )
    )
    if not policy_decision.approved:
        # Keep this exact sentence: the theatre renders it as user-facing copy.
        reason = policy_decision.reason
        enqueue_escalation(db, transaction_id=transaction_id, reason=reason)
        _set_state(
            db,
            txn,
            TransactionLifecycleState.ESCALATED,
            action_type=ActionType.ESCALATION,
            payload={
                "agent_tool": AgentTool.HANDOFF_TO_HUMAN.value,
                "requested_tool": proposed_tool.value,
                "policy_block": reason,
            },
            outcome=Outcome.ESCALATED,
        )
        return AgentDecision(
            AgentTool.HANDOFF_TO_HUMAN,
            None,
            None,
            TransactionLifecycleState.ESCALATED,
            False,
            reason,
            None,
            route_decision,
            model_reason=model_reason,
            sandbox_reason=reason,
            message=message,
            discount_pct=discount_pct,
            requested_tool=proposed_tool,
        )

    if proposed_tool == AgentTool.SCHEDULE_RETRY:
        scheduled_for = next_salary_window(date.today())
        _set_state(
            db,
            txn,
            TransactionLifecycleState.WAITING,
            action_type=ActionType.RETRY_SCHEDULED,
            payload={
                "agent_tool": proposed_tool.value,
                "scheduled_for": scheduled_for,
                "reason": model_reason or "Retry scheduled for the next salary window.",
            },
        )
    return AgentDecision(
        proposed_tool,
        action,
        channel,
        default_state,
        True,
        policy_decision.reason,
        None,
        route_decision,
        model_reason=model_reason,
        sandbox_reason=policy_decision.reason,
        message=message,
        discount_pct=discount_pct,
        requested_tool=proposed_tool,
        scheduled_for=scheduled_for if proposed_tool == AgentTool.SCHEDULE_RETRY else None,
    )


# Keep a short public spelling for the Part 3 session code and tests.
decide = decide_tool
resolve_tool = decide_tool
