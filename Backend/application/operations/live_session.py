"""Interactive recovery sessions for the live theatre.

Session coordination uses an in-process ``asyncio.Queue`` per session. This is
intentionally single-worker only: the queue is not a broker and this module
does not imply that sessions can move between workers. Durable transaction,
message, call, escalation, and audit rows remain the record of the session.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from application.constants import (
    ActionType,
    CallSpeaker,
    CallStatus,
    FailureClass,
    InterventionAction,
    InterventionChannel,
    MessageDirection,
    MessageSender,
    MessageStatus,
    NodeName,
    Outcome,
    PaymentArtifactKind,
    PaymentArtifactStatus,
    Playbook,
    StoppingRule,
    TransactionLifecycleState,
)
from application.entities import (
    AuditTrail,
    CallSession,
    CallTurn,
    Message,
    PaymentArtifact,
    TransactionState,
)
from application.helpers import next_quiet_hours_end, now_ist, resolve_clock_ist
from application.persistence import SessionLocal
from application.integrations.adapter_base import DispatchResult
from application.integrations.razorpay_mcp import payment_render_variant
from application.operations import agent_tools, payment_artifacts
from application.operations.agent_tools import AgentDecision, AgentTool, decide_tool
from application.operations.audit_service import record_audit
from application.operations.compliance_rules import is_within_quiet_hours, screen_user_message
from application.operations.batch_seed import class_profile
from application.operations.language_parser import extract_p2p_date
from application.operations.message_drafter import draft_message
from application.operations.model_router import ProviderUnavailable, RouteDecision, RoutedResult, explain_route
from application.operations.policy_repository import get_policy
from application.operations.playbook_map import DEFAULT_PLAYBOOK, PLAYBOOK_ACTION
from application.operations.reconciliation_service import compute_metrics
from application.operations.voice_attempts import voice_attempt_count
from application.operations.wire import _ser_msg
from application.simulation.scenario import CaseShape, CustomCase, Scenario, plan, to_transaction
from application.settings import settings
from application.operations.voice_agent import build_assistant


Event = tuple[str, dict[str, Any]]


def _initial_prompt(failure_class: int) -> str:
    return {
        1: "Write the first WhatsApp message: a brief technical glitch on our side caused this payment to fail — reassure it's not their fault and offer a secure 1-tap link, no OTP needed.",
        2: "Write the first WhatsApp message: their checkout dropped at the OTP/3DS step; offer a 1-tap UPI Autopay link to finish instantly.",
        3: "Write the first WhatsApp message: their subscription auto-debit failed due to a low balance before salary; reassure you'll retry around their salary date.",
        4: "Write the first WhatsApp message: their B2B invoice is overdue; politely ask when you can expect the payment.",
    }.get(failure_class, "Write a short, polite payment-recovery message.")


def _tool_for_playbook(playbook: Playbook) -> AgentTool:
    action, channel = PLAYBOOK_ACTION[playbook]
    for tool, (candidate_action, candidate_channel, _state) in agent_tools._TOOL_RESOLUTION.items():
        if candidate_action == action and candidate_channel == channel:
            return tool
    return AgentTool.HANDOFF_TO_HUMAN


class _DeterministicOpeningRouter:
    """Choose the opening class default without spending a model call.

    The opening is a seeded theatre beat. Human turns below use the production
    router, while the once-per-turn decision contract is still exercised here.
    """

    def __init__(self, tool: AgentTool):
        self.tool = tool

    def call(self, task: str, prompt: str, **kwargs: Any) -> RoutedResult:
        route = RouteDecision(
            task=str(task).upper(),
            tier="seeded",
            provider="deterministic",
            model="seeded-playbook",
            reason="Seeded opening action; no model call was made.",
            raised_by=[],
            escalated_from=None,
            latency_ms=0.0,
            tokens=None,
        )
        return RoutedResult(
            json.dumps({"tool": self.tool.value, "reason": "The class playbook is the safe opening action."}),
            route,
        )


def add_message(
    db: Session,
    transaction_id: str,
    direction: MessageDirection,
    sender: MessageSender,
    body: str,
    meta: dict[str, Any] | None = None,
) -> Message:
    """Append one thread message, keeping ``seq`` monotonic per transaction.

    Free-standing so a caller with no open ``LiveSession`` — the deadline
    sweeper (Part 5), for one — can still write into the same thread a live
    session would. ``LiveSession._add_message`` delegates here.
    """
    last = (
        db.query(Message)
        .filter_by(transaction_id=transaction_id)
        .order_by(Message.seq.desc())
        .first()
    )
    message = Message(
        transaction_id=transaction_id,
        channel=InterventionChannel.WHATSAPP,
        direction=direction,
        sender=sender,
        body=body,
        status=MessageStatus.READ,
        seq=(last.seq + 1) if last else 0,
        meta_json=meta,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _bounds(
    db: Session,
    txn: TransactionState,
    *,
    stopping_rule: str | None = None,
    clock: Callable[[], datetime] = now_ist,
) -> dict[str, Any]:
    policy = get_policy(db)
    audits = (
        db.query(AuditTrail)
        .filter(AuditTrail.transaction_id == txn.transaction_id)
        .order_by(AuditTrail.id)
        .all()
    )
    allowed = list(policy.get("allowed_channels", []))
    used: set[str] = set()
    retries = 0
    voice = 0
    total = 0
    fired = stopping_rule
    for row in audits:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if row.action_type == ActionType.INTERVENTION_DISPATCH:
            total += 1
            if payload.get("channel"):
                used.add(payload["channel"])
            if payload.get("channel") == InterventionChannel.VOICE.value or payload.get("action") == "VOICE_CALL":
                voice += 1
            if payload.get("action") == "RETRY_CHARGE":
                retries += 1
        if row.action_type == ActionType.RETRY_SCHEDULED:
            retries += 1
        fired = fired or payload.get("stopping_rule")
    closed = txn.current_state in {
        TransactionLifecycleState.RECOVERED,
        TransactionLifecycleState.ESCALATED,
        TransactionLifecycleState.CANCELLED,
        TransactionLifecycleState.FAILED,
    }
    clock = clock()
    quiet = not closed and is_within_quiet_hours(clock)
    armed_rule = None
    if not closed:
        if quiet:
            armed_rule = StoppingRule.TRAI_QUIET_HOURS.value
        elif retries >= 3:
            armed_rule = StoppingRule.RBI_MAX_RETRIES.value
        elif voice >= 2:
            armed_rule = StoppingRule.VOICE_ATTEMPT_CAP.value
        elif int(txn.failure_class) == int(FailureClass.SUBSCRIPTION_MANDATE) and retries > 0:
            armed_rule = StoppingRule.RBI_MAX_RETRIES.value
        elif voice > 0:
            armed_rule = StoppingRule.VOICE_ATTEMPT_CAP.value
    return {
        "retries": {"used": min(retries, 3), "cap": 3, "exhausted": retries >= 3},
        "voice": {"used": min(voice, 2), "cap": 2, "exhausted": voice >= 2},
        "totalDispatches": total,
        "channelsAllowed": allowed,
        "channelsUsed": [channel for channel in allowed if channel in used],
        "channelsRemaining": [channel for channel in allowed if channel not in used],
        "armedRule": armed_rule,
        "firedRule": fired,
        "nextActionAt": next_quiet_hours_end(clock).isoformat() if quiet else None,
        "inQuietHours": quiet,
        "closed": closed,
    }


@dataclass
class LiveSession:
    session_id: str
    transaction_id: str
    run_id: str
    owns_transaction: bool
    locale: str = "en"
    queue: asyncio.Queue[Event | None] = field(default_factory=asyncio.Queue)
    started: bool = False
    closed: bool = False
    terminal: bool = False
    loop: asyncio.AbstractEventLoop | None = None
    last_decision: AgentDecision | None = None
    call_session_id: int | None = None
    # Polls Razorpay for a minted artifact's payment status - there is no
    # webhook reachable from localhost in the demo, so this is what notices a
    # completed checkout and reflects it back into the WhatsApp thread.
    poll_task: asyncio.Task | None = None
    # The IST wall clock this session's compliance checks read. Injected like
    # OrchestratorDeps.clock, so an authored case can pin a moment (e.g. to demo
    # TRAI quiet hours live) via CustomCase.clock_ist - see create_session().
    clock: Callable[[], datetime] = field(default=now_ist)

    def emit(self, event: str, data: dict[str, Any]) -> None:
        if self.closed:
            return
        item: Event = (event, data)
        if self.loop is not None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is not self.loop:
                self.loop.call_soon_threadsafe(self.queue.put_nowait, item)
                return
        self.queue.put_nowait(item)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        if self.poll_task is None and not self.closed:
            self.poll_task = loop.create_task(self._poll_payments())

    def _signal_end(self) -> None:
        def put_end() -> None:
            self.queue.put_nowait(None)

        if self.loop is not None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is not self.loop:
                self.loop.call_soon_threadsafe(put_end)
                return
        put_end()

    def _txn(self, db: Session) -> TransactionState:
        txn = db.query(TransactionState).filter_by(transaction_id=self.transaction_id).one_or_none()
        if txn is None:
            raise ValueError(f"Unknown transaction: {self.transaction_id!r}")
        return txn

    def _add_message(
        self,
        db: Session,
        direction: MessageDirection,
        sender: MessageSender,
        body: str,
        meta: dict[str, Any] | None = None,
    ) -> Message:
        return add_message(db, self.transaction_id, direction, sender, body, meta)

    def _route(self, decision: RouteDecision) -> None:
        self.emit("route", decision.as_dict())

    def _opening(self, db: Session) -> None:
        txn = self._txn(db)
        fc = FailureClass(txn.failure_class)
        meta = dict(txn.metadata_json or {})
        name = str(meta.get("customer_name") or "there")
        amount = round(txn.amount_minor / 100, 2)
        profile = class_profile(fc)

        txn.current_state = TransactionLifecycleState.DIAGNOSING
        db.commit()
        record_audit(
            db,
            transaction_id=self.transaction_id,
            node_name=NodeName.INGEST,
            action_type=ActionType.STATE_TRANSITION,
            payload={"event": "FLAGGED", "class": profile["label"], "live_session_id": self.session_id},
            outcome=Outcome.SUCCESS,
        )
        self.emit("start", {"transaction_id": self.transaction_id, "failure_class": int(fc), "amount_inr": amount, "customer_name": name})
        self.emit("step", {"phase": "flagged", "label": f"Flagged: {profile['label']} · ₹{int(amount):,}"})

        playbook = DEFAULT_PLAYBOOK[fc]
        record_audit(
            db,
            transaction_id=self.transaction_id,
            node_name=NodeName.DIAGNOSE,
            action_type=ActionType.STATE_TRANSITION,
            payload={"root_cause": profile["root_cause"], "recommended_playbook": playbook.value, "confidence": profile["confidence"], "live_session_id": self.session_id},
            outcome=Outcome.SUCCESS,
        )
        self.emit("diagnosis", {"root_cause": profile["root_cause"], "playbook": playbook.value, "confidence": profile["confidence"]})

        # The opening copy is deterministic, like the existing live-recovery
        # runner. The human's first reply is the first model-backed turn.
        self.emit("typing", {"who": "agent"})
        opening = draft_message(db, self.transaction_id, _initial_prompt(int(fc)), generate=None, locale=self.locale)
        opening_decision = decide_tool(
            db,
            self.transaction_id,
            failure_class=fc,
            voice_attempts=0,
            now_ist=self.clock(),
            model_router=_DeterministicOpeningRouter(_tool_for_playbook(playbook)),
        )
        self.last_decision = opening_decision
        self.emit("decision", opening_decision.as_dict())
        self._apply_agent_decision(db, opening_decision, opening, playbook=playbook)

    def start(self, db: Session) -> None:
        if not self.started and not self.closed:
            self.started = True
            self._opening(db)

    def _mint_artifact(self, db: Session, txn: TransactionState, decision: AgentDecision) -> PaymentArtifact:
        """Mint the artifact a payment-action decision authorized.

        gate_tool has already cleared quiet hours, caps, and the sandbox
        ceiling against ``decision.request_amount_minor`` - this only decides
        *which kind* of artifact to render and, for a partial plan, books the
        remaining balance and deadline.
        """
        if decision.action == InterventionAction.GENERATE_QR_CODE:
            kind = PaymentArtifactKind.QR
        else:
            variant = payment_render_variant(int(txn.failure_class))
            kind = {
                "link": PaymentArtifactKind.LINK,
                "upi": PaymentArtifactKind.UPI_LINK,
                "qr": PaymentArtifactKind.QR,
            }.get(variant, PaymentArtifactKind.LINK)

        amount_minor = decision.request_amount_minor or txn.amount_minor
        is_partial = (amount_minor < txn.amount_minor) or (decision.action == InterventionAction.OFFER_PARTIAL_PLAN)

        # Prior active artifacts will be closed inside payment_artifacts.mint
        prior_active_ids = [
            a.id
            for a in db.query(PaymentArtifact)
            .filter(
                PaymentArtifact.transaction_id == txn.transaction_id,
                PaymentArtifact.status == PaymentArtifactStatus.CREATED,
            )
            .all()
        ]

        if is_partial:
            if settings.partial_plan_demo_seconds > 0:
                # A 14-day deadline cannot be demonstrated in a two-minute
                # video - this override lets the sweeper's follow-up land on
                # camera instead.
                deadline = self.clock() + timedelta(seconds=settings.partial_plan_demo_seconds)
            else:
                deadline_days = decision.deadline_days or settings.partial_plan_default_days
                deadline = self.clock() + timedelta(days=deadline_days)
            artifact = payment_artifacts.mint(
                db,
                txn,
                kind,
                amount_minor=amount_minor,
                accept_partial=True,
                first_min_partial_minor=amount_minor,
                deadline=deadline,
            )
        else:
            artifact = payment_artifacts.mint(db, txn, kind, amount_minor=amount_minor)

        for old_id in prior_active_ids:
            self.emit("artifact_closed", {"id": old_id})

        return artifact

    def _apply_agent_decision(
        self,
        db: Session,
        decision: AgentDecision,
        body: str | None,
        *,
        playbook: Playbook | None = None,
    ) -> PaymentArtifact | None:
        txn = self._txn(db)
        _PAYMENT_ACTIONS = {
            InterventionAction.GENERATE_PAYMENT_LINK,
            InterventionAction.GENERATE_QR_CODE,
            InterventionAction.OFFER_PARTIAL_PLAN,
        }
        if decision.allowed and decision.channel is not None:
            dispatch_result = None
            artifact = None
            if decision.action in _PAYMENT_ACTIONS:
                # gate_tool has already run quiet hours, caps, and PolicySandbox.validate().
                artifact = self._mint_artifact(db, txn, decision)
                dispatch_result = DispatchResult(
                    decision.channel.value,
                    delivered=True,
                    simulated=artifact.simulated,
                    reference=artifact.provider_id,
                    detail=artifact.detail,
                    url=artifact.url,
                    image_url=artifact.image_url,
                )
            txn.current_state = TransactionLifecycleState.INTERVENING
            db.commit()
            record_audit(
                db,
                transaction_id=self.transaction_id,
                node_name=NodeName.EXECUTE_INTERVENTION,
                action_type=ActionType.INTERVENTION_DISPATCH,
                payload={
                    "action": decision.action.value if decision.action else None,
                    "channel": decision.channel.value,
                    "playbook": playbook.value if playbook else None,
                    "agent_tool": decision.tool.value,
                    "live_session_id": self.session_id,
                },
                outcome=Outcome.SUCCESS,
            )
            if dispatch_result is not None:
                self.emit(
                    "dispatch",
                    {
                        "channel": dispatch_result.channel,
                        "delivered": dispatch_result.delivered,
                        "simulated": dispatch_result.simulated,
                        "reference": dispatch_result.reference,
                        "detail": dispatch_result.detail,
                    },
                )
            elif decision.action not in _PAYMENT_ACTIONS:
                # Non-payment channel dispatch (WhatsApp / voice / fee waiver)
                # still goes through the shared adapter routing.
                from application.integrations.routing_dispatcher import build_dispatcher
                from application.operations.policy_guard import ProposedAction

                dispatch_result = build_dispatcher(db, live_mode=settings.live_mode)(
                    ProposedAction(
                        action=decision.action,
                        channel=decision.channel,
                        discount_pct=decision.discount_pct,
                        amount_minor=txn.amount_minor,
                    ),
                    {"transaction_id": self.transaction_id},
                )
                self.emit(
                    "dispatch",
                    {
                        "channel": dispatch_result.channel,
                        "delivered": dispatch_result.delivered,
                        "simulated": dispatch_result.simulated,
                        "reference": dispatch_result.reference,
                        "detail": dispatch_result.detail,
                    },
                )
            if artifact is not None:
                self.emit("artifact", artifact.as_dict())
                if artifact.url and body and artifact.url not in body:
                    body = f"{body}\n\n{artifact.url}"
            if body:
                meta = {"ai_drafted": True}
                if artifact is not None:
                    meta["payment_artifact"] = artifact.as_dict()
                message = self._add_message(db, MessageDirection.OUTBOUND, MessageSender.AGENT, body, meta)
                self.emit("message", _ser_msg(message))
            if decision.channel == InterventionChannel.VOICE:
                call = CallSession(
                    transaction_id=self.transaction_id,
                    status=CallStatus.RINGING,
                    duration_sec=0,
                    outcome=None,
                    provider="vapi",
                )
                db.add(call)
                db.commit()
                db.refresh(call)
                self.call_session_id = call.id
                txn = self._txn(db)
                b = _bounds(db, txn, clock=self.clock)
                assistant = build_assistant(txn, self.locale, b, db=db)
                self.emit(
                    "call_offer",
                    {
                        "assistant": assistant,
                        "public_key": settings.vapi_public_key or None,
                        "call_session_id": call.id,
                    },
                )
            return artifact

        if body and decision.allowed and decision.tool in {AgentTool.STOP, AgentTool.HANDOFF_TO_HUMAN}:
            message = self._add_message(db, MessageDirection.OUTBOUND, MessageSender.SYSTEM, body)
            self.emit("message", _ser_msg(message))
        elif body and decision.terminal_state == TransactionLifecycleState.WAITING:
            # A non-dispatching tool (e.g. SCHEDULE_RETRY) still had a drafted
            # conversational reply to the customer's message — send it, rather
            # than silently discarding it.
            message = self._add_message(db, MessageDirection.OUTBOUND, MessageSender.AGENT, body, {"ai_drafted": True})
            self.emit("message", _ser_msg(message))
        else:
            # No message this turn (e.g. a silently policy-refused handoff) —
            # the client's typing indicator only clears on a "message" event,
            # so it must be told explicitly or it hangs forever.
            self.emit("typing", {"who": None})
        if decision.terminal_state in {
            TransactionLifecycleState.ESCALATED,
            TransactionLifecycleState.CANCELLED,
        }:
            self._finish(db, decision.terminal_state.value, decision.stopping_rule.value if decision.stopping_rule else None)
        elif decision.terminal_state == TransactionLifecycleState.WAITING:
            self.emit("bounds", _bounds(db, txn, clock=self.clock))
            self.emit("status", {"final_state": TransactionLifecycleState.WAITING.value})
        return None

    def _finish(self, db: Session, final_state: str, stopping_rule: str | None = None) -> None:
        txn = self._txn(db)
        txn.current_state = TransactionLifecycleState(final_state)
        meta = dict(txn.metadata_json or {})
        meta["unworked"] = False
        txn.metadata_json = meta
        db.commit()
        self.emit("bounds", _bounds(db, txn, stopping_rule=stopping_rule, clock=self.clock))
        self.emit("status", {"final_state": final_state})
        self.emit("complete", {"final_state": final_state, "metrics": compute_metrics(db, simulation_run_id=self.run_id)})
        self.terminal = True
        self._signal_end()

    def _screened_stop(self, db: Session, verdict: Any) -> None:
        txn = self._txn(db)
        if verdict.disposition == "ESCALATE":
            from application.operations.escalation_service import enqueue_escalation

            enqueue_escalation(db, transaction_id=self.transaction_id, reason=verdict.reason, rule=verdict.rule)
            final = TransactionLifecycleState.ESCALATED
            outcome = Outcome.ESCALATED
            phase = "escalated"
        else:
            final = TransactionLifecycleState.CANCELLED
            outcome = Outcome.SUCCESS
            phase = "stopped"
        txn.current_state = final
        db.commit()
        record_audit(
            db,
            transaction_id=self.transaction_id,
            node_name=NodeName.INGEST,
            action_type=ActionType.STATE_TRANSITION,
            payload={"stopping_rule": verdict.rule.value, "reason": verdict.reason, "live_session_id": self.session_id},
            outcome=outcome,
        )
        text = (
            f"Dispute raised — automation frozen, escalated to a human ({verdict.rule.value})."
            if final == TransactionLifecycleState.ESCALATED
            else f"Opt-out honoured — all contact stopped ({verdict.rule.value})."
        )
        message = self._add_message(db, MessageDirection.OUTBOUND, MessageSender.SYSTEM, text)
        self.emit("step", {"phase": phase, "rule": verdict.rule.value})
        self.emit("message", _ser_msg(message))
        self._finish(db, final.value, verdict.rule.value)

    def _converse(self, db: Session, text: str) -> tuple[str, RouteDecision]:
        txn = self._txn(db)
        route: RouteDecision | None = None

        def generate(prompt: str) -> str:
            nonlocal route
            try:
                routed = agent_tools.router.call(
                    "CONVERSE",
                    prompt,
                    amount_inr=txn.amount_minor / 100,
                    retries_used=txn.retry_count,
                    live=True,
                )
                route = routed.decision
                return routed.result
            except ProviderUnavailable as exc:
                route = exc.decision
                raise

        body = draft_message(
            db,
            self.transaction_id,
            f"Respond naturally to the customer's latest message: {text}",
            generate=generate,
            locale=self.locale,
        )
        route = route or explain_route("CONVERSE", amount_inr=txn.amount_minor / 100, live=True)
        return body, route

    def _maybe_add_reminder(self, db: Session, customer_text: str, decision: AgentDecision) -> None:
        """When the customer commits to a pay date, or the agent books a partial
        plan, record a calendar reminder on the case and tell the client so it
        can surface "Reminder added to calendar" and show it on the calendar."""
        clock = self.clock()
        is_partial = (
            decision.action == InterventionAction.OFFER_PARTIAL_PLAN
            or decision.tool == AgentTool.OFFER_PARTIAL_PLAN
        )
        p2p = extract_p2p_date(customer_text, clock.date())

        if is_partial:
            days = decision.deadline_days or settings.partial_plan_default_days
            when = (clock.date() + timedelta(days=days)).isoformat()
            kind = "partial_payment"
        elif p2p:
            when = p2p
            kind = "promise_to_pay"
        else:
            return

        txn = self._txn(db)
        meta = dict(txn.metadata_json or {})
        if meta.get("calendar_reminder", {}).get("date") == when:
            return  # already booked for this date

        amount_inr = round(txn.amount_minor / 100, 2)
        name = meta.get("customer_name") or "Customer"
        label = (
            "Partial payment balance due"
            if kind == "partial_payment"
            else f"{name} promised to pay"
        )
        reminder = {"date": when, "kind": kind, "label": label, "amount_inr": amount_inr}
        meta["calendar_reminder"] = reminder
        meta["next_debit_date"] = when
        txn.metadata_json = meta
        db.commit()

        record_audit(
            db,
            transaction_id=self.transaction_id,
            node_name=NodeName.INGEST,
            action_type=ActionType.STATE_TRANSITION,
            payload={"calendar_reminder": reminder, "live_session_id": self.session_id},
            outcome=Outcome.SUCCESS,
        )
        self.emit("reminder", {**reminder, "message": "Reminder added to calendar"})

    def reply(self, db: Session, text: str) -> dict[str, Any]:
        self.start(db)
        if self.closed or self.terminal:
            return {"session_id": self.session_id, "final_state": self._txn(db).current_state.value}
        message = self._add_message(db, MessageDirection.INBOUND, MessageSender.CUSTOMER, text)
        self.emit("message", _ser_msg(message))

        # This gate is deliberately before _converse: no model sees an opt-out
        # or dispute, and no LLM output can override either disposition.
        verdict = screen_user_message(text)
        if verdict.disposition in {"TERMINATE", "ESCALATE"}:
            self._screened_stop(db, verdict)
            return {"session_id": self.session_id, "final_state": self._txn(db).current_state.value}

        txn = self._txn(db)
        self.emit("typing", {"who": "agent"})
        body, converse_route = self._converse(db, text)
        self._route(converse_route)
        decision = decide_tool(
            db,
            self.transaction_id,
            model_router=agent_tools.router,
            now_ist=self.clock(),
            customer_text=text,
            agent_draft=body,
        )
        self.last_decision = decision
        self._route(decision.route_decision)
        self.emit("decision", decision.as_dict())
        self._apply_agent_decision(db, decision, body)
        self._maybe_add_reminder(db, text, decision)
        txn = self._txn(db)
        if not self.terminal:
            self.emit("bounds", _bounds(db, txn, clock=self.clock))
            self.emit("status", {"final_state": txn.current_state.value})
        return {"session_id": self.session_id, "final_state": txn.current_state.value}

    def call_web(self, db: Session) -> dict[str, Any]:
        if self.last_decision is None or self.last_decision.tool != AgentTool.VOICE_CALL or not self.last_decision.allowed:
            raise ValueError("A permitted VOICE_CALL decision is required before opening the web call.")
        txn = self._txn(db)
        b = _bounds(db, txn, clock=self.clock)
        assistant = build_assistant(txn, self.locale, b, db=db)
        return {
            "allowed": True,
            "provider": "vapi",
            "gated": True,
            "assistant": assistant,
            "public_key": settings.vapi_public_key or None,
            "call_session_id": self.call_session_id,
            "reason": "Vapi web-call configuration active.",
        }

    def run_agent_tool(self, db: Session, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Gate and (on allow) mint a tool the voice or chat client names directly.

        This is the one entry point the browser's Vapi tool-call handler
        calls (Part 4) - it runs the identical ``gate_tool`` chain a model
        proposal would, so the voice agent cannot mint anything the chat
        agent could not.
        """
        try:
            # Coerce through the enum first, exactly like decide_tool's
            # boundary - an unoffered function name never reaches gate_tool.
            tool = AgentTool(tool_name)
        except (TypeError, ValueError):
            raise ValueError(f"Unknown agent tool: {tool_name!r}")

        txn = self._txn(db)
        attempts = voice_attempt_count(db, self.transaction_id, None)
        route_decision = RouteDecision(
            task="TOOL_CALL",
            tier="direct",
            provider="client",
            model="named-tool",
            reason=f"The client directly named {tool.value}.",
            raised_by=[],
            escalated_from=None,
            latency_ms=0.0,
            tokens=None,
        )

        request_amount_minor: int | None = None
        if tool == AgentTool.OFFER_PARTIAL_PLAN and args.get("first_payment_inr") is not None:
            request_amount_minor = round(float(args["first_payment_inr"]) * 100)
        elif args.get("amount_inr") is not None:
            request_amount_minor = round(float(args["amount_inr"]) * 100)
        elif args.get("partial_amount_inr") is not None:
            request_amount_minor = round(float(args["partial_amount_inr"]) * 100)

        deadline_days = args.get("deadline_days")
        deadline_days = int(deadline_days) if deadline_days is not None else None

        decision = agent_tools.gate_tool(
            db,
            txn,
            tool,
            route_decision=route_decision,
            model_reason=f"Client-named tool call: {tool.value}.",
            request_amount_minor=request_amount_minor,
            deadline_days=deadline_days,
            voice_attempts=attempts,
            now_ist=self.clock(),
        )
        self.last_decision = decision
        self.emit("decision", decision.as_dict())
        artifact = self._apply_agent_decision(db, decision, None)
        txn = self._txn(db)
        if not self.terminal:
            self.emit("bounds", _bounds(db, txn, clock=self.clock))
            self.emit("status", {"final_state": txn.current_state.value})
        return {
            "allowed": decision.allowed,
            "tool": decision.tool.value,
            "reason": decision.reason,
            "sandbox_reason": decision.sandbox_reason,
            "artifact": artifact.as_dict() if artifact is not None else None,
        }

    def simulate_payment(self, db: Session, artifact_id: int) -> dict[str, Any]:
        """Demo-only: force one of this case's artifacts straight to paid and
        announce it into the thread exactly as a real reconciled payment
        would be. See ``payment_artifacts.simulate_paid``."""
        artifact = (
            db.query(PaymentArtifact)
            .filter_by(id=artifact_id, transaction_id=self.transaction_id)
            .one_or_none()
        )
        if artifact is None:
            raise LookupError(f"Unknown payment artifact: {artifact_id!r}")
        payment_artifacts.simulate_paid(db, artifact)
        self._announce_payment(db, artifact)
        return artifact.as_dict()

    def list_artifacts(self, db: Session) -> list[dict[str, Any]]:
        rows = (
            db.query(PaymentArtifact)
            .filter_by(transaction_id=self.transaction_id)
            .order_by(PaymentArtifact.id)
            .all()
        )
        return [row.as_dict() for row in rows]

    def check_latest_payment_status(self, db: Session) -> dict[str, Any]:
        """On-demand reconcile for the voice `check_payment_status` tool.

        The background poll (`_poll_payments`) already reconciles on a timer,
        but a customer who says "maine kar diya" mid-call wants the answer
        now, not at the next tick.
        """
        artifact = (
            db.query(PaymentArtifact)
            .filter_by(transaction_id=self.transaction_id)
            .order_by(PaymentArtifact.id.desc())
            .first()
        )
        if artifact is None:
            return {"found": False, "artifact": None}

        if artifact.provider_id is not None:
            before_status = artifact.status
            before_paid = artifact.amount_paid_minor
            payment_artifacts.reconcile(db, artifact)
            if artifact.status != before_status or artifact.amount_paid_minor != before_paid:
                self._announce_payment(db, artifact)

        return {"found": True, "artifact": artifact.as_dict()}

    async def _poll_payments(self) -> None:
        """Background loop: notice a completed Razorpay checkout and reflect
        it into the thread. There is no webhook reachable from localhost in
        the demo, so this poll is the only thing that ever calls ``reconcile``
        for a live session.

        ``reconcile`` makes a synchronous Razorpay call (an MCP round trip is
        itself a blocking ``future.result()`` under the hood) - run it in a
        worker thread, never inline on this coroutine, or one slow poll
        freezes the whole server's event loop for every session and request.
        """
        try:
            while not self.closed and not self.terminal:
                await asyncio.sleep(settings.payment_poll_seconds)
                if self.closed or self.terminal:
                    return
                await asyncio.to_thread(self._reconcile_pending_once)
        except asyncio.CancelledError:
            pass

    def _reconcile_pending_once(self) -> None:
        db = SessionLocal()
        try:
            self._reconcile_pending(db)
        except Exception:
            # A flaky Razorpay call must not take the session down; the next
            # tick tries again.
            pass
        finally:
            db.close()

    def _reconcile_pending(self, db: Session) -> None:
        pending = (
            db.query(PaymentArtifact)
            .filter_by(transaction_id=self.transaction_id)
            .filter(PaymentArtifact.provider_id.isnot(None))
            .filter(
                PaymentArtifact.status.in_(
                    [PaymentArtifactStatus.CREATED, PaymentArtifactStatus.PARTIALLY_PAID]
                )
            )
            .all()
        )
        for artifact in pending:
            if self.terminal:
                return
            before_status = artifact.status
            before_paid = artifact.amount_paid_minor
            payment_artifacts.reconcile(db, artifact)
            if artifact.status != before_status or artifact.amount_paid_minor != before_paid:
                self._announce_payment(db, artifact)

    def _announce_payment(self, db: Session, artifact: PaymentArtifact) -> None:
        if self.closed:
            return
        txn = self._txn(db)
        hi = self.locale == "hi"
        paid_now = f"₹{int(artifact.amount_paid_minor / 100):,}"

        if artifact.status == PaymentArtifactStatus.PAID and not artifact.accept_partial:
            body = (
                f"भुगतान मिल गया — {paid_now}। धन्यवाद!"
                if hi
                else f"Payment received — {paid_now}. Thank you!"
            )
        elif artifact.status == PaymentArtifactStatus.PARTIALLY_PAID:
            balance = int((txn.metadata_json or {}).get("balance_due_minor", 0))
            balance_text = f"₹{balance:,}"
            body = (
                f"भुगतान मिल गया — {paid_now}। शेष {balance_text} अभी भी बकाया है।"
                if hi
                else f"Payment received — {paid_now}. {balance_text} still due."
            )
        elif artifact.status == PaymentArtifactStatus.PAID and artifact.accept_partial:
            # The partial plan's remaining balance just got cleared in full.
            body = (
                f"भुगतान मिल गया — {paid_now}। आपका पूरा बकाया चुक गया है, धन्यवाद!"
                if hi
                else f"Payment received — {paid_now}. That clears the balance in full — thank you!"
            )
        else:
            return

        message = self._add_message(
            db,
            MessageDirection.OUTBOUND,
            MessageSender.SYSTEM,
            body,
            {"payment_confirmed": True, "payment_artifact": artifact.as_dict()},
        )
        self.emit("message", _ser_msg(message))
        self.emit("artifact", artifact.as_dict())
        record_audit(
            db,
            transaction_id=self.transaction_id,
            node_name=NodeName.RECONCILE,
            action_type=ActionType.STATE_TRANSITION,
            payload={
                "event": "PAYMENT_RECONCILED",
                "artifact_id": artifact.id,
                "status": artifact.status.value,
                "amount_paid_minor": artifact.amount_paid_minor,
            },
            outcome=Outcome.SUCCESS,
        )

        txn = self._txn(db)
        if self.terminal:
            return
        if txn.current_state == TransactionLifecycleState.RECOVERED:
            self._finish(db, txn.current_state.value)
        else:
            self.emit("bounds", _bounds(db, txn, clock=self.clock))
            self.emit("status", {"final_state": txn.current_state.value})

    def ingest_turn(self, db: Session, speaker: str, text: str, at_offset_sec: int = 0) -> dict[str, Any]:
        if self.call_session_id is None:
            call = CallSession(transaction_id=self.transaction_id, status=CallStatus.IN_PROGRESS, provider="vapi")
            db.add(call)
            db.commit()
            db.refresh(call)
            self.call_session_id = call.id
        try:
            who = CallSpeaker(speaker.upper())
        except ValueError as exc:
            raise ValueError("speaker must be AGENT or CUSTOMER") from exc
        count = db.query(CallTurn).filter_by(call_session_id=self.call_session_id).count()
        turn = CallTurn(call_session_id=self.call_session_id, speaker=who, text=text, seq=count, at_offset_sec=at_offset_sec)
        db.add(turn)
        call = db.query(CallSession).filter_by(id=self.call_session_id).first()
        if call:
            if call.status == CallStatus.RINGING:
                call.status = CallStatus.IN_PROGRESS
            if at_offset_sec > (call.duration_sec or 0):
                call.duration_sec = at_offset_sec
        db.commit()
        label = f"{who.value}: {text[:60]}{'…' if len(text) > 60 else ''}"
        self.emit("step", {"phase": "voice_turn", "label": label})
        return {"call_session_id": self.call_session_id, "speaker": who.value, "text": text, "seq": count}

    def close(self, db: Session) -> None:
        if self.closed:
            return
        self.closed = True
        if self.poll_task is not None:
            self.poll_task.cancel()
        # DELETE ends the in-process session only. Durable rows intentionally
        # remain so the transcript and append-only audit evidence can still be
        # read after leaving the theatre. In particular, never bulk-delete
        # AuditTrail rows: their ORM guard is part of the data contract.
        def signal_close() -> None:
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self.queue.put_nowait(None)

        if self.loop is not None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is not self.loop:
                self.loop.call_soon_threadsafe(signal_close)
                return
        signal_close()


_SESSIONS: dict[str, LiveSession] = {}


def create_session(
    db: Session,
    *,
    custom_case: dict[str, Any] | None = None,
    transaction_id: str | None = None,
    locale: str = "en",
) -> LiveSession:
    session_id = f"live_{uuid.uuid4().hex}"
    run_id = session_id
    if custom_case is not None:
        case = CustomCase.model_validate(custom_case)
        scenario = Scenario(cases=CaseShape(count=0), custom_cases=[case])
        planned = plan(scenario, run_id)[0]
        txn = to_transaction(planned, run_id)
        owns = True
    elif transaction_id:
        txn = db.query(TransactionState).filter_by(transaction_id=transaction_id).one_or_none()
        if txn is None:
            raise LookupError(transaction_id)
        owns = False
    else:
        raise ValueError("custom_case or transaction_id is required")

    meta = dict(txn.metadata_json or {})
    meta["simulation_run_id"] = run_id
    meta["live_session_id"] = session_id
    txn.metadata_json = meta
    if owns:
        db.add(txn)
    db.commit()

    # An authored case's clock_ist ("HH:MM") freezes this session's compliance
    # clock at that time of day today, so a demo can deliberately show TRAI
    # quiet hours (or a daytime pass) instead of depending on when it happens
    # to be run. Absent it, the session reads the real clock like everything
    # else in the graph.
    authored_moment = resolve_clock_ist(meta.get("clock_ist"))
    clock = (lambda moment=authored_moment: moment) if authored_moment is not None else now_ist

    session = LiveSession(
        session_id,
        txn.transaction_id,
        run_id,
        owns,
        locale=locale if locale in ("en", "hi") else "en",
        clock=clock,
    )
    _SESSIONS[session_id] = session
    return session


def get_session(session_id: str) -> LiveSession | None:
    return _SESSIONS.get(session_id)


def find_session_by_transaction(transaction_id: str) -> LiveSession | None:
    """The live session for a transaction, if one is open right now.

    Used by the deadline sweeper (Part 5): a follow-up it drafts still has to
    reach an open theatre's SSE stream, not just the durable ``Message`` row,
    or the follow-up never appears on screen mid-demo.
    """
    for session in _SESSIONS.values():
        if session.transaction_id == transaction_id and not session.closed:
            return session
    return None


def remove_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


def prune_sessions(db: Session) -> None:
    """Drop in-process handles while preserving every durable session row.

    A restart cannot resume an in-process queue. The transaction and audit
    records are deliberately retained for evidence; no bulk delete is used.
    """
    for session_id in list(_SESSIONS):
        _SESSIONS.pop(session_id, None)
