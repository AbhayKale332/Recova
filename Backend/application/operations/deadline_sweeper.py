"""Background sweeper: fires the deadline a partial-payment plan booked.

There is no scheduler in this repo, so this is the smallest thing that is
not one: an ``asyncio.create_task`` started from ``server.py``'s lifespan,
ticking every ``settings.deadline_sweep_seconds`` with its own DB session.

Each tick finds every open partial-plan artifact whose deadline has passed,
reconciles it first (a customer who paid in the meantime must not be
chased), and — if a balance remains — runs the *same* ``gate_tool`` chain a
model proposal or a voice tool call would, naming ``AgentTool.SEND_WHATSAPP``.
That is deliberate: this is outbound contact, so TRAI quiet hours apply here
exactly as everywhere else, and a deadline that lands at 21:00 correctly
defers rather than messaging.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from application.constants import (
    ActionType,
    MessageDirection,
    MessageSender,
    NodeName,
    Outcome,
    PaymentArtifactStatus,
    TransactionLifecycleState,
)
from application.entities import PaymentArtifact, TransactionState
from application.helpers import now_ist
from application.operations import agent_tools, payment_artifacts
from application.operations.agent_tools import AgentTool
from application.operations.audit_service import record_audit
from application.operations.live_session import add_message, find_session_by_transaction
from application.operations.model_router import RouteDecision
from application.operations.wire import _ser_msg
from application.persistence import SessionLocal
from application.settings import settings

logger = logging.getLogger(__name__)

_TERMINAL_STATES = {
    TransactionLifecycleState.RECOVERED,
    TransactionLifecycleState.ESCALATED,
    TransactionLifecycleState.CANCELLED,
    TransactionLifecycleState.FAILED,
}

_OPEN_ARTIFACT_STATUSES = (PaymentArtifactStatus.CREATED, PaymentArtifactStatus.PARTIALLY_PAID)


async def run_forever() -> None:
    """The sweeper's main loop. Cancelled from ``server.py``'s lifespan on shutdown."""
    try:
        while True:
            await asyncio.sleep(settings.deadline_sweep_seconds)
            await asyncio.to_thread(_tick_once)
    except asyncio.CancelledError:
        pass


def _tick_once() -> None:
    db = SessionLocal()
    try:
        _tick(db)
    except Exception:
        # A flaky tick must not take the sweeper down - the next one tries again.
        logger.exception("Deadline sweeper tick failed")
    finally:
        db.close()


def _tick(db: Session, clock: datetime | None = None) -> None:
    """One sweep. ``clock`` defaults to the real IST clock; a test passes a
    fixed one to make quiet-hours deferral deterministic."""
    now = clock or now_ist()
    due = (
        db.query(PaymentArtifact)
        .join(TransactionState, TransactionState.transaction_id == PaymentArtifact.transaction_id)
        .filter(PaymentArtifact.accept_partial.is_(True))
        .filter(PaymentArtifact.deadline.isnot(None))
        .filter(PaymentArtifact.deadline <= now)
        .filter(PaymentArtifact.followed_up_at.is_(None))
        .filter(PaymentArtifact.status.in_(_OPEN_ARTIFACT_STATUSES))
        .filter(TransactionState.current_state.notin_(_TERMINAL_STATES))
        .all()
    )
    for artifact in due:
        _process_artifact(db, artifact, now)


def _process_artifact(db: Session, artifact: PaymentArtifact, now: datetime) -> None:
    txn = db.query(TransactionState).filter_by(transaction_id=artifact.transaction_id).one_or_none()
    if txn is None:
        return

    # 1. Reconcile first - a customer who paid in the meantime must not be chased.
    payment_artifacts.reconcile(db, artifact)
    db.refresh(txn)
    if txn.current_state in _TERMINAL_STATES or artifact.status not in _OPEN_ARTIFACT_STATUSES:
        # Reconcile just recovered the case (or otherwise closed it) - nothing
        # to chase, and the next tick's own filters exclude this artifact.
        return

    balance_minor = int((txn.metadata_json or {}).get("balance_due_minor", 0))
    if balance_minor <= 0:
        return

    # 2. Outbound contact - the exact same gate chain a model proposal or a
    # voice tool call runs, so TRAI quiet hours apply here too.
    route_decision = RouteDecision(
        task="DEADLINE_SWEEP",
        tier="direct",
        provider="system",
        model="deadline-sweeper",
        reason="Partial-payment plan's deadline passed with a balance outstanding.",
        raised_by=[],
        escalated_from=None,
        latency_ms=0.0,
        tokens=None,
    )
    decision = agent_tools.gate_tool(
        db,
        txn,
        AgentTool.SEND_WHATSAPP,
        route_decision=route_decision,
        model_reason="Automated follow-up: partial-payment deadline passed.",
        now_ist=now,
    )
    if not decision.allowed:
        # e.g. TRAI quiet hours - defers. `followed_up_at` stays null, so the
        # next tick tries again.
        return

    # 3. Allowed: draft, persist, audit, stamp, and (if the case is live) emit.
    live = find_session_by_transaction(txn.transaction_id)
    hi = live is not None and live.locale == "hi"
    balance_text = f"₹{balance_minor // 100:,}"
    deadline_text = artifact.deadline.astimezone(now.tzinfo).strftime("%d %b") if artifact.deadline else ""
    link_text = f" {artifact.url}" if artifact.url else ""
    body = (
        f"Namaste, aapke payment plan ka {balance_text} balance {deadline_text} tak due tha aur abhi tak "
        f"nahi aaya hai. Kripya jald se jald complete karein:{link_text}"
        if hi
        else f"Hi, the {balance_text} balance from your payment plan was due by {deadline_text} and hasn't "
        f"come in yet. Please complete it at your earliest:{link_text}"
    ).strip()

    message = add_message(
        db,
        txn.transaction_id,
        MessageDirection.OUTBOUND,
        MessageSender.SYSTEM,
        body,
        {"deadline_followup": True, "payment_artifact": artifact.as_dict()},
    )

    artifact.followed_up_at = now
    db.commit()

    record_audit(
        db,
        transaction_id=txn.transaction_id,
        node_name=NodeName.EXECUTE_INTERVENTION,
        action_type=ActionType.INTERVENTION_DISPATCH,
        payload={
            "event": "DEADLINE_FOLLOWUP",
            "agent_tool": AgentTool.SEND_WHATSAPP.value,
            "artifact_id": artifact.id,
            "balance_minor": balance_minor,
        },
        outcome=Outcome.SUCCESS,
    )

    if live is not None:
        live.emit("message", _ser_msg(message))
