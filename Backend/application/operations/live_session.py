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
from typing import Any

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
    Playbook,
    StoppingRule,
    TransactionLifecycleState,
)
from application.entities import (
    AuditTrail,
    CallSession,
    CallTurn,
    Message,
    TransactionState,
)
from application.helpers import next_quiet_hours_end, now_ist
from application.operations import agent_tools
from application.operations.agent_tools import AgentDecision, AgentTool, decide_tool
from application.operations.audit_service import record_audit
from application.operations.compliance_rules import is_within_quiet_hours, screen_user_message
from application.operations.batch_seed import class_profile
from application.operations.message_drafter import draft_message
from application.operations.model_router import ProviderUnavailable, RouteDecision, RoutedResult, explain_route
from application.operations.policy_repository import get_policy
from application.operations.playbook_map import DEFAULT_PLAYBOOK, PLAYBOOK_ACTION
from application.operations.reconciliation_service import compute_metrics
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


def _bounds(db: Session, txn: TransactionState, *, stopping_rule: str | None = None) -> dict[str, Any]:
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
    clock = now_ist()
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
        last = (
            db.query(Message)
            .filter_by(transaction_id=self.transaction_id)
            .order_by(Message.seq.desc())
            .first()
        )
        message = Message(
            transaction_id=self.transaction_id,
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
            now_ist=now_ist(),
            model_router=_DeterministicOpeningRouter(_tool_for_playbook(playbook)),
        )
        self.last_decision = opening_decision
        self.emit("decision", opening_decision.as_dict())
        self._apply_agent_decision(db, opening_decision, opening, playbook=playbook)

    def start(self, db: Session) -> None:
        if not self.started and not self.closed:
            self.started = True
            self._opening(db)

    def _apply_agent_decision(
        self,
        db: Session,
        decision: AgentDecision,
        body: str | None,
        *,
        playbook: Playbook | None = None,
    ) -> None:
        txn = self._txn(db)
        if decision.allowed and decision.channel is not None:
            dispatch_result = None
            if decision.action == InterventionAction.GENERATE_PAYMENT_LINK:
                # decide_tool has already run quiet hours, caps, and PolicySandbox.validate().
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
            if body:
                message = self._add_message(db, MessageDirection.OUTBOUND, MessageSender.AGENT, body, {"ai_drafted": True})
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
                b = _bounds(db, txn)
                assistant = build_assistant(txn, self.locale, b, db=db)
                self.emit(
                    "call_offer",
                    {
                        "assistant": assistant,
                        "public_key": settings.vapi_public_key or None,
                        "call_session_id": call.id,
                    },
                )
            return

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
            self.emit("bounds", _bounds(db, txn))
            self.emit("status", {"final_state": TransactionLifecycleState.WAITING.value})

    def _finish(self, db: Session, final_state: str, stopping_rule: str | None = None) -> None:
        txn = self._txn(db)
        txn.current_state = TransactionLifecycleState(final_state)
        meta = dict(txn.metadata_json or {})
        meta["unworked"] = False
        txn.metadata_json = meta
        db.commit()
        self.emit("bounds", _bounds(db, txn, stopping_rule=stopping_rule))
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
        decision = decide_tool(db, self.transaction_id, model_router=agent_tools.router, now_ist=now_ist())
        self.last_decision = decision
        self._route(decision.route_decision)
        self.emit("decision", decision.as_dict())
        self._apply_agent_decision(db, decision, body)
        txn = self._txn(db)
        if not self.terminal:
            self.emit("bounds", _bounds(db, txn))
            self.emit("status", {"final_state": txn.current_state.value})
        return {"session_id": self.session_id, "final_state": txn.current_state.value}

    def call_web(self, db: Session) -> dict[str, Any]:
        if self.last_decision is None or self.last_decision.tool != AgentTool.VOICE_CALL or not self.last_decision.allowed:
            raise ValueError("A permitted VOICE_CALL decision is required before opening the web call.")
        txn = self._txn(db)
        b = _bounds(db, txn)
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
        return {"call_session_id": self.call_session_id, "speaker": who.value, "text": text, "seq": count}

    def close(self, db: Session) -> None:
        if self.closed:
            return
        self.closed = True
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
    session = LiveSession(
        session_id,
        txn.transaction_id,
        run_id,
        owns,
        locale=locale if locale in ("en", "hi") else "en",
    )
    _SESSIONS[session_id] = session
    return session


def get_session(session_id: str) -> LiveSession | None:
    return _SESSIONS.get(session_id)


def remove_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


def prune_sessions(db: Session) -> None:
    """Drop in-process handles while preserving every durable session row.

    A restart cannot resume an in-process queue. The transaction and audit
    records are deliberately retained for evidence; no bulk delete is used.
    """
    for session_id in list(_SESSIONS):
        _SESSIONS.pop(session_id, None)
