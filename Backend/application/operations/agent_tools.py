"""Closed agent tool set and the deterministic gates around each proposal.

The first four channel pairings mirror ``PLAYBOOK_ACTION`` in
``operations/playbook_map.py`` and must stay consistent with it.  ``AgentTool``
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
from dataclasses import asdict, dataclass, replace
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
from application.entities import TransactionState
from application.helpers import next_quiet_hours_end, next_salary_window, now_ist as _now_ist
from application.operations import policy_repository
from application.operations.audit_service import record_audit
from application.operations.compliance_rules import (
    VOICE_ATTEMPT_CAP,
    WHATSAPP_NUDGE_CAP,
    is_within_quiet_hours,
    retry_cap_exceeded,
    voice_attempts_exhausted,
    whatsapp_nudges_exhausted,
)
from application.operations.message_attempts import whatsapp_nudge_count
from application.operations.playbook_map import DEFAULT_PLAYBOOK, PLAYBOOK_ACTION
from application.operations.escalation_service import enqueue_escalation
from application.operations.model_router import (
    ModelRouter,
    ProviderUnavailable,
    RouteDecision,
    explain_route,
    router,
)
from application.operations.policy_guard import PolicySandbox, ProposedAction
from application.operations.repayment_model import predict_for_case
from application.operations.voice_attempts import voice_attempt_count

logger = logging.getLogger(__name__)


class AgentTool(str, Enum):
    """The closed set of tools the DECIDE prompt is allowed to propose."""

    SEND_WHATSAPP = "SEND_WHATSAPP"
    VOICE_CALL = "VOICE_CALL"
    GENERATE_PAYMENT_LINK = "GENERATE_PAYMENT_LINK"
    GENERATE_QR_CODE = "GENERATE_QR_CODE"
    OFFER_PARTIAL_PLAN = "OFFER_PARTIAL_PLAN"
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
    request_amount_minor: int | None = None
    deadline_days: int | None = None
    # Advisory score from the demo repayment model (operations/repayment_model).
    # It informs the DECIDE prompt and is surfaced on the live theatre; it never
    # gates a tool.
    repayment_probability: float | None = None
    repayment_band: str | None = None

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
    AgentTool.GENERATE_QR_CODE: (
        InterventionAction.GENERATE_QR_CODE,
        InterventionChannel.PAYMENT_LINK,
        None,
    ),
    AgentTool.OFFER_PARTIAL_PLAN: (
        InterventionAction.OFFER_PARTIAL_PLAN,
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
    action, channel = PLAYBOOK_ACTION[playbook]
    for tool, (tool_action, tool_channel, _state) in _TOOL_RESOLUTION.items():
        if tool_action == action and tool_channel == channel:
            return tool
    raise ValueError(f"No AgentTool mapping for playbook {playbook!r}")


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
    whatsapp_nudges: int = 0,
    recent_messages: list[str] | None = None,
    repayment: Any | None = None,
) -> str:
    offered = ", ".join(tool.value for tool in AgentTool)
    meta = getattr(txn, "metadata_json", None) or {}
    lines = [
        "You are the decision layer of a payment-recovery agent.",
        f"The failure class is {failure_class.name} ({failure_class.value}).",
        f"The transaction amount is ₹{txn.amount_minor / 100:,.2f}.",
        f"Retries already used: {txn.retry_count} of {txn.max_retries}.",
        f"Voice attempts already used: {voice_attempts} of {VOICE_ATTEMPT_CAP}.",
        f"WhatsApp nudges already sent: {whatsapp_nudges} of {WHATSAPP_NUDGE_CAP}. "
        f"Once {WHATSAPP_NUDGE_CAP} nudges have gone out without payment, prefer VOICE_CALL "
        f"over another SEND_WHATSAPP.",
        f"The merchant policy discount cap is {policy['max_discount_pct']}%.",
    ]
    if repayment is not None:
        top = ", ".join(
            f"{name} ({'+' if delta >= 0 else ''}{delta:.2f})"
            for name, delta in repayment.contributions[:3]
        )
        lines.append(
            f"A demo repayment model estimates this customer's probability of paying at "
            f"{repayment.probability:.0%} ({repayment.band} confidence band). "
            f"Largest drivers (log-odds): {top}. "
            f"Treat this as advisory: a low probability favours a cheaper, lower-effort tool "
            f"(WhatsApp nudge, payment link) or HANDOFF_TO_HUMAN over spending a voice attempt "
            f"or a discount; a high probability supports a direct payment ask. It never "
            f"overrides merchant policy or a guardrail."
        )
    ceiling_minor = policy.get("max_intervention_amount_minor")
    if ceiling_minor is not None:
        lines.append(
            f"A single payment action (link, QR, or partial plan's first payment) cannot "
            f"exceed ₹{int(ceiling_minor) / 100:,.0f} — propose a smaller first payment instead "
            f"of a full amount that would be refused."
        )
    balance_due = meta.get("balance_due_minor")
    if balance_due is not None:
        lines.append(f"A partial plan already exists: ₹{int(balance_due) / 100:,.2f} balance still due.")
        deadline = meta.get("balance_deadline")
        if deadline:
            lines.append(f"That balance is due by {deadline}.")
    allow_partial = bool(policy.get("allow_partial_payment", True))
    min_partial_pct = int(policy.get("min_partial_payment_pct", 50))
    min_partial_inr = (txn.amount_minor / 100) * (min_partial_pct / 100)
    lines.append(f"Merchant policy partial payment allowed: {'YES' if allow_partial else 'NO'}.")
    lines.append(f"Merchant policy minimum partial payment: {min_partial_pct}% (minimum ₹{min_partial_inr:,.2f}).")
    lines.append(
        "CRITICAL RULE ON PARTIAL PAYMENT: You MUST check merchant policy before agreeing to or generating a partial payment link. "
        "If partial payments are NOT permitted by policy, or if the customer's proposed amount is below the minimum percentage, "
        "do NOT propose a partial payment link or OFFER_PARTIAL_PLAN. Politely refuse and request full payment or HANDOFF_TO_HUMAN."
    )
    if recent_messages:
        lines.append("Recent thread (oldest first):")
        lines.extend(f"- {entry}" for entry in recent_messages)
    lines.append(f"Choose exactly one tool from: {offered}.")
    lines.append(
        'Return STRICT JSON: {"tool": string, "reason": string, "message": string|null, '
        '"discount_pct": number|null, "partial_amount_inr": number|null, '
        '"deadline_days": number|null, "confidence": number}.'
    )
    lines.append(
        '"partial_amount_inr" is the amount to request now if generating a partial payment link or OFFER_PARTIAL_PLAN; '
        '"deadline_days" is when the remaining balance falls due.'
    )
    lines.append("Never invent a tool, widen the policy, or treat a disposition as a channel dispatch.")
    return "\n".join(lines)


def _route_fallback(task: str, **kwargs: Any) -> RouteDecision:
    return explain_route(task, **kwargs)


def gate_tool(
    db: Session,
    txn: TransactionState,
    tool: AgentTool,
    *,
    route_decision: RouteDecision,
    model_reason: str = "",
    message: str | None = None,
    discount_pct: float | None = None,
    request_amount_minor: int | None = None,
    deadline_days: int | None = None,
    voice_attempts: int = 0,
    now_ist: datetime | None = None,
    sandbox: PolicySandbox | None = None,
) -> AgentDecision:
    """Evaluate the deterministic gates for one proposed tool and commit the result.

    Precedence is intentionally identical to workflow_nodes.execute: HANDOFF /
    STOP short-circuit first, then quiet hours -> retry cap -> voice cap ->
    PolicySandbox.validate(). This is the gate chain shared by decide_tool
    (a model proposal) and the voice agent's client-side function calls
    (Part 4) - the sandbox never sees a difference between the two callers.
    """
    transaction_id = txn.transaction_id
    proposed_tool = tool
    action, channel, default_state = _TOOL_RESOLUTION[proposed_tool]
    amount_minor = request_amount_minor if request_amount_minor is not None else txn.amount_minor

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

    if channel == InterventionChannel.VOICE and voice_attempts_exhausted(voice_attempts):
        reason = f"Voice attempt cap reached ({voice_attempts} of {VOICE_ATTEMPT_CAP} calls in 72 hours)."
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
            amount_minor=amount_minor,
            total_amount_minor=txn.amount_minor,
            is_partial=(amount_minor < txn.amount_minor) or (proposed_tool == AgentTool.OFFER_PARTIAL_PLAN),
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
        request_amount_minor=amount_minor,
        deadline_days=deadline_days,
    )


def _recent_thread(db: Session, transaction_id: str, limit: int = 6) -> list[str]:
    from application.entities import Message

    rows = (
        db.query(Message)
        .filter_by(transaction_id=transaction_id)
        .order_by(Message.seq.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [f"{row.sender.value}: {row.body}" for row in rows]


def decide_tool(
    db: Session,
    transaction_id: str,
    *,
    failure_class: FailureClass | int | None = None,
    voice_attempts: int | None = None,
    discount_pct: float | None = None,
    proposed_discount_pct: float | None = None,
    customer_text: str | None = None,
    agent_draft: str | None = None,
    now_ist: datetime | None = None,
    model_router: ModelRouter | None = None,
    sandbox: PolicySandbox | None = None,
) -> AgentDecision:
    """Route a model proposal for one tool, then run it through ``gate_tool``.

    Call it exactly once per turn. It does not dispatch a channel adapter;
    callers use the returned decision to perform an allowed dispatch.
    """
    txn = db.query(TransactionState).filter_by(transaction_id=transaction_id).one_or_none()
    if txn is None:
        raise ValueError(f"Unknown transaction: {transaction_id!r}")

    fc = FailureClass(failure_class if failure_class is not None else txn.failure_class)
    policy = policy_repository.get_policy(db)
    attempts = voice_attempt_count(db, transaction_id, voice_attempts)
    nudges = whatsapp_nudge_count(db, transaction_id)
    amount_inr = float(txn.amount_minor) / 100
    active_router = model_router or router
    recent = _recent_thread(db, transaction_id)
    if customer_text:
        recent = recent + [f"customer: {customer_text}"]
    if agent_draft:
        recent = recent + [f"agent (drafted): {agent_draft}"]

    clock = now_ist or _now_ist()
    meta = getattr(txn, "metadata_json", None) or {}
    days_overdue = int(meta.get("days_overdue") or 0)
    if not days_overdue and txn.created_at is not None:
        try:
            days_overdue = max(0, (clock.date() - txn.created_at.date()).days)
        except (TypeError, ValueError):
            days_overdue = 0
    repayment = predict_for_case(
        failure_class=int(fc),
        amount_inr=amount_inr,
        days_overdue=days_overdue,
        retries_used=int(txn.retry_count),
        prior_repayments=int(meta.get("prior_repayments") or 0),
        in_quiet_hours=is_within_quiet_hours(clock),
    )

    prompt = _decide_prompt(
        txn,
        fc,
        policy=policy,
        voice_attempts=attempts,
        whatsapp_nudges=nudges,
        recent_messages=recent,
        repayment=repayment,
    )
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
        default_playbook = DEFAULT_PLAYBOOK[fc]
        logger.warning(
            "The model returned unsupported tool %r; applying the deterministic class default.",
            raw_tool,
        )
        proposed_tool = _tool_for_playbook(default_playbook)

    model_reason = str(payload.get("reason") or "")
    message = payload.get("message")
    message = str(message) if message is not None else None

    # After three WhatsApp nudges without payment, the agent switches the next
    # contact to a voice call on its own - the operator no longer has to ask for
    # it. This is a deterministic override of the model proposal, not a stopping
    # rule: quiet hours and the voice-attempt cap still bind in gate_tool below,
    # and if a call is not permitted there the case escalates to a human. Only a
    # plain SEND_WHATSAPP nudge is redirected; a payment link, partial plan, or
    # deliberate handoff/stop is left alone. Voice must be a permitted channel,
    # and a voice attempt must still be available.
    voice_is_permitted = (
        InterventionChannel.VOICE.value in policy.get("allowed_channels", [])
        and InterventionAction.VOICE_CALL.value in policy.get("allowed_actions", [])
    )
    if (
        proposed_tool == AgentTool.SEND_WHATSAPP
        and whatsapp_nudges_exhausted(nudges)
        and not voice_attempts_exhausted(attempts)
        and voice_is_permitted
    ):
        logger.info(
            "WhatsApp nudge cap reached (%d of %d) for %s; auto-escalating this turn to VOICE_CALL.",
            nudges,
            WHATSAPP_NUDGE_CAP,
            transaction_id,
        )
        proposed_tool = AgentTool.VOICE_CALL
        model_reason = (
            f"Auto-escalated to a voice call: {nudges} WhatsApp nudges already sent "
            f"without payment (cap {WHATSAPP_NUDGE_CAP})."
            + (f" Model rationale for continued contact: {model_reason}" if model_reason else "")
        )
    raw_discount = payload.get("discount_pct", route_discount)
    # Preserve an integer percentage so PolicySandbox's user-facing sentence
    # remains exactly "Discount 20% ...", rather than changing it to 20.0%.
    if isinstance(raw_discount, Real) and not isinstance(raw_discount, bool):
        discount_pct = int(raw_discount) if float(raw_discount).is_integer() else float(raw_discount)
    else:
        discount_pct = None

    # The model proposes an amount and deadline; the code bounds them. Neither
    # field can widen what PolicySandbox.validate() will accept.
    request_amount_minor: int | None = None
    raw_partial = payload.get("partial_amount_inr") if payload.get("partial_amount_inr") is not None else payload.get("amount_inr")
    if isinstance(raw_partial, Real) and not isinstance(raw_partial, bool):
        clamped_inr = max(0.01, min(float(raw_partial), amount_inr))
        request_amount_minor = round(clamped_inr * 100)

    deadline_days: int | None = None
    raw_deadline = payload.get("deadline_days")
    if isinstance(raw_deadline, Real) and not isinstance(raw_deadline, bool):
        deadline_days = max(1, min(int(raw_deadline), 90))

    _PARTIAL_ALLOWED_TOOLS = {
        AgentTool.OFFER_PARTIAL_PLAN,
        AgentTool.GENERATE_PAYMENT_LINK,
        AgentTool.GENERATE_QR_CODE,
    }

    decision = gate_tool(
        db,
        txn,
        proposed_tool,
        route_decision=route_decision,
        model_reason=model_reason,
        message=message,
        discount_pct=discount_pct,
        request_amount_minor=request_amount_minor if proposed_tool in _PARTIAL_ALLOWED_TOOLS else None,
        deadline_days=deadline_days,
        voice_attempts=attempts,
        now_ist=now_ist,
        sandbox=sandbox,
    )
    return replace(
        decision,
        repayment_probability=repayment.probability,
        repayment_band=repayment.band,
    )


# Keep a short public spelling for the Part 3 session code and tests.
decide = decide_tool
resolve_tool = decide_tool
