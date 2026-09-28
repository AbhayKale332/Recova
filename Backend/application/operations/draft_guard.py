"""Verify an LLM-drafted customer message before it is sent.

The RBI Fair Practices Code bars coercive recovery: threats, shaming, and
contacting family or employers. A generative model can drift into any of that,
or promise a concession the merchant policy does not allow. Jev judges each
condition; code checks the numbers (amounts against the bill, percentages
against the discount cap) and the policy flags. A draft that fails any check is
replaced by the standard template.

If Jev is unavailable the draft passes on the code-side checks alone, as drafts
did before this guard existed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from application.operations import jev_client
from application.operations.jev_client import DecisionUnavailable, Judgments

logger = logging.getLogger(__name__)

# A blocked good draft costs warmth (the template is plainer); a sent coercive
# one is a regulatory breach. Probe (2026-09-28): the four clean drafts peaked
# at 0.26 (leaks_internal on "I'll check back then"); every violating draft
# scored 0.94-0.99 on its question.
COERCIVE_GATE = 0.5
OFF_TOPIC_GATE = 0.5
LEAK_GATE = 0.5
CONCESSION_GATE = 0.5

QUESTIONS: dict[str, dict[str, Any]] = {
    "coercive": jev_client.noul(
        "Does `draft` threaten, shame, pressure, or intimidate the customer?",
        true=(
            "It threatens legal action, police, or credit damage; mentions telling family, friends, or an "
            "employer; insults or shames; or uses aggressive, fear-based pressure."
        ),
        false="It is a polite reminder or reply, even if it mentions the amount due or a date.",
    ),
    "off_topic": jev_client.noul(
        "Is `draft` about something other than this customer's pending payment?",
        true="It is about an unrelated subject.",
        false="It is a message to the customer about their payment.",
    ),
    "leaks_internal": jev_client.noul(
        "Does `draft` contain text meant for staff or the system rather than the customer?",
        true="It includes system notes, internal labels, risk scores, instructions to an AI, or operator comments.",
        false="Everything in it is written to the customer.",
    ),
    "promises_discount": jev_client.noul(
        "Does `draft` offer or promise the customer a discount, fee waiver, or reduced amount?",
        true="It offers money off, waives a fee, or says the customer can pay less than the full bill.",
        false="It asks for the amount due without any reduction.",
    ),
    "agrees_to_partial": jev_client.noul(
        "Does `draft` agree that the customer can pay part of the amount now and the rest later?",
        true="It accepts or proposes paying in parts or installments.",
        false="It asks for the full amount, or refuses a partial payment.",
    ),
}

_RUPEES = re.compile(r"(?:₹|rs\.?|inr)\s*(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)", re.IGNORECASE)
_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


@dataclass
class GuardResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    judgments: Judgments | None = None

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"task": "DRAFT_GUARD", "ok": self.ok, "reasons": self.reasons}
        if self.judgments is not None:
            out.update(jev_client.summarise(self.judgments))
        return out


def check_draft(
    draft: str,
    *,
    amount_inr: float,
    policy: dict[str, Any],
    decide: Callable[..., Judgments] | None = None,
) -> GuardResult:
    reasons: list[str] = []

    # Code-side: numbers are never the model's job.
    amounts = [float(m.replace(",", "")) for m in _RUPEES.findall(draft)]
    if any(a > amount_inr + 0.5 for a in amounts):
        reasons.append("mentions an amount above the bill")
    cap = float(policy.get("max_discount_pct") or 0)

    # The upfront payment is selected from the draft's own amounts, never
    # generated; the balance due later is naturally below the minimum.
    candidates = {f"₹{a:,.0f}": a for a in amounts}
    questions = dict(QUESTIONS)
    if candidates:
        questions["upfront_amount"] = jev_client.choice(
            "Which amount in `draft` is the customer asked to pay now (the first or only payment)?",
            {
                **{label: f"{label} is the amount to pay now." for label in candidates},
                "none": "No amount is asked for now; any amount is the total, a balance due later, or a past figure.",
            },
        )

    judgments: Judgments | None = None
    try:
        judgments = (decide or jev_client.decide)({"draft": draft}, questions)
    except DecisionUnavailable as exc:
        logger.info("Jev unavailable for the draft guard (%s); code-side checks only.", exc)

    if judgments is not None:
        if judgments.noul("coercive") >= COERCIVE_GATE:
            reasons.append(f"coercive (Jev p={judgments.noul('coercive'):.2f})")
        if judgments.noul("off_topic") >= OFF_TOPIC_GATE:
            reasons.append(f"off topic (Jev p={judgments.noul('off_topic'):.2f})")
        if judgments.noul("leaks_internal") >= LEAK_GATE:
            reasons.append(f"leaks internal text (Jev p={judgments.noul('leaks_internal'):.2f})")
        if judgments.noul("promises_discount") >= CONCESSION_GATE:
            percents = [float(p) for p in _PERCENT.findall(draft)]
            if cap <= 0 or any(p > cap for p in percents):
                reasons.append(f"promises a discount beyond the {cap:.0f}% policy cap")
        if judgments.noul("agrees_to_partial") >= CONCESSION_GATE:
            if not bool(policy.get("allow_partial_payment", True)):
                reasons.append("agrees to a partial payment the policy does not allow")
            elif candidates:
                floor = amount_inr * int(policy.get("min_partial_payment_pct", 50)) / 100
                upfront = candidates.get(judgments.choice("upfront_amount").choice)
                if upfront is not None and upfront < floor - 0.5:
                    reasons.append("agrees to a partial payment below the policy minimum")

    return GuardResult(ok=not reasons, reasons=reasons, judgments=judgments)
