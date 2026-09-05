"""Single mint path for a Razorpay payment artifact (link, UPI link, or QR).

Replaces the two divergent implementations that used to exist
(``payment_link_service.create_payment_link`` and
``RazorpayActionsAdapter.create_payment_link``) with one: MCP -> SDK ->
simulated, in that precedence, with the same ``detail`` strings the existing
tests assert on. This module persists the artifact row and updates the case's
outstanding-balance metadata; it never writes a ``Message`` - the caller owns
the thread.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from application.constants import PaymentArtifactKind, PaymentArtifactStatus, TransactionLifecycleState
from application.entities import PaymentArtifact, TransactionState
from application.integrations.razorpay_mcp import default_client, mcp_dispatch_enabled
from application.settings import settings


def _build_client():
    """Construct a real Razorpay client from the configured (test) keys."""
    import razorpay

    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def _mcp_mint(
    kind: PaymentArtifactKind,
    txn: TransactionState,
    *,
    amount_minor: int,
    accept_partial: bool,
    first_min_partial_minor: int | None,
    deadline: datetime | None,
    description: str,
) -> dict[str, Any] | None:
    if not mcp_dispatch_enabled():
        return None
    client = default_client()
    notes = {"transaction_id": txn.transaction_id, "merchant_id": txn.merchant_id}
    close_by = int(deadline.timestamp()) if deadline else None
    if kind == PaymentArtifactKind.QR:
        return client.create_qr(
            amount_minor=amount_minor, description=description, notes=notes, close_by=close_by
        )
    return client.create_link(
        amount_minor=amount_minor,
        currency=txn.currency or "INR",
        contact=txn.customer_contact,
        description=description,
        notes=notes,
        accept_partial=accept_partial,
        first_min_partial_minor=first_min_partial_minor,
        expire_by=close_by,
        upi=kind == PaymentArtifactKind.UPI_LINK,
    )


def _sdk_mint(txn: TransactionState, *, amount_minor: int, description: str) -> dict[str, Any] | None:
    """The SDK fallback only creates a plain payment link - Razorpay's Python
    SDK has no first-class QR/partial-plan call, so those rely on MCP or fall
    back to the simulated artifact."""
    client = _build_client()
    return client.payment_link.create(
        {
            "amount": int(amount_minor),
            "currency": txn.currency or "INR",
            "description": description,
            "customer": {"contact": txn.customer_contact},
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {"transaction_id": txn.transaction_id, "merchant_id": txn.merchant_id},
        }
    )


def mint(
    db: Session,
    txn: TransactionState,
    kind: PaymentArtifactKind,
    *,
    amount_minor: int,
    accept_partial: bool = False,
    first_min_partial_minor: int | None = None,
    deadline: datetime | None = None,
    description: str | None = None,
) -> PaymentArtifact:
    description = description or f"Payment recovery for {txn.transaction_id}"

    provider_id: str | None = None
    url: str | None = None
    image_url: str | None = None
    detail = "simulated"

    try:
        result = _mcp_mint(
            kind,
            txn,
            amount_minor=amount_minor,
            accept_partial=accept_partial,
            first_min_partial_minor=first_min_partial_minor,
            deadline=deadline,
            description=description,
        )
    except Exception:
        result = None
    if result and result.get("id"):
        provider_id = str(result["id"])
        url = result.get("short_url")
        image_url = result.get("image_url") or result.get("qr_code")
        detail = "mcp"

    if provider_id is None and kind != PaymentArtifactKind.QR:
        have_keys = bool(settings.razorpay_key_id and settings.razorpay_key_secret)
        if have_keys:
            try:
                link = _sdk_mint(txn, amount_minor=amount_minor, description=description)
                provider_id = link.get("id")
                url = link.get("short_url")
                detail = "sdk"
            except Exception:
                provider_id = None

    simulated = provider_id is None
    if simulated:
        detail = "simulated"
        provider_id = f"sim_{txn.transaction_id[-6:]}"
        url = None if kind == PaymentArtifactKind.QR else f"https://rzp.io/i/{txn.transaction_id[-6:]}"
    # Graciously close and deactivate prior active payment links for this case
    prior_active = (
        db.query(PaymentArtifact)
        .filter(
            PaymentArtifact.transaction_id == txn.transaction_id,
            PaymentArtifact.status == PaymentArtifactStatus.CREATED,
        )
        .all()
    )
    for old_art in prior_active:
        if old_art.provider_id and not old_art.simulated and settings.razorpay_key_id and settings.razorpay_key_secret:
            try:
                import razorpay
                rzp_client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
                rzp_client.payment_link.cancel(old_art.provider_id)
            except Exception as exc:
                logger.warning("Could not cancel previous Razorpay link %s: %s", old_art.provider_id, exc)
        old_art.status = PaymentArtifactStatus.CLOSED

    # Update previous message records carrying this artifact so the thread reflects its closure
    closed_ids = {a.id for a in prior_active}
    if closed_ids:
        from application.entities import Message
        messages = (
            db.query(Message)
            .filter(Message.transaction_id == txn.transaction_id)
            .all()
        )
        for msg in messages:
            if msg.meta_json and isinstance(msg.meta_json, dict):
                art_data = msg.meta_json.get("payment_artifact")
                if isinstance(art_data, dict) and art_data.get("id") in closed_ids:
                    msg_meta = dict(msg.meta_json)
                    msg_meta["payment_artifact"] = dict(art_data)
                    msg_meta["payment_artifact"]["status"] = PaymentArtifactStatus.CLOSED.value
                    msg.meta_json = msg_meta

    artifact = PaymentArtifact(
        transaction_id=txn.transaction_id,
        kind=kind,
        provider_id=None if simulated else provider_id,
        url=url,
        image_url=image_url,
        amount_minor=amount_minor,
        accept_partial=accept_partial,
        first_min_partial_minor=first_min_partial_minor,
        deadline=deadline,
        status=PaymentArtifactStatus.CREATED,
        amount_paid_minor=0,
        simulated=simulated,
        detail=detail,
        meta_json={"description": description},
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)

    meta = dict(txn.metadata_json or {})
    meta["payment_link_id"] = None if simulated else provider_id
    if accept_partial:
        balance = max(int(txn.amount_minor) - int(amount_minor), 0)
        meta["balance_due_minor"] = balance
        if deadline is not None:
            meta["balance_deadline"] = deadline.isoformat()
    txn.metadata_json = meta
    db.commit()
    db.refresh(txn)
    return artifact


def _apply_txn_state(db: Session, artifact: PaymentArtifact) -> None:
    """Fold an artifact's just-updated status/amount_paid into the case's
    outstanding-balance bookkeeping and lifecycle state. Shared by ``reconcile``
    (a real Razorpay status change) and ``simulate_paid`` (a demo-forced one) -
    both end with the exact same case-side effects."""
    txn = db.query(TransactionState).filter_by(transaction_id=artifact.transaction_id).one_or_none()
    if txn is None:
        return
    _CLOSED = {TransactionLifecycleState.ESCALATED, TransactionLifecycleState.CANCELLED}
    if artifact.accept_partial:
        balance = max(int(txn.amount_minor) - int(artifact.amount_paid_minor), 0)
        meta = dict(txn.metadata_json or {})
        meta["balance_due_minor"] = balance
        txn.metadata_json = meta
        # A partial payment closes the balance, not the case - only a
        # fully cleared balance (or a plain, non-partial link) recovers it.
        if balance <= 0:
            txn.current_state = TransactionLifecycleState.RECOVERED
        elif artifact.status == PaymentArtifactStatus.PARTIALLY_PAID and txn.current_state not in _CLOSED:
            txn.current_state = TransactionLifecycleState.WAITING
        db.commit()
    elif artifact.status == PaymentArtifactStatus.PAID and txn.current_state not in _CLOSED:
        # A plain (non-partial) link or QR has no balance to book - a full
        # payment recovers the case outright.
        txn.current_state = TransactionLifecycleState.RECOVERED
        db.commit()


def reconcile(db: Session, artifact: PaymentArtifact) -> PaymentArtifact:
    """Poll Razorpay for the artifact's live status and update it (and, for a
    partial plan, the case's outstanding balance) accordingly."""
    if artifact.provider_id is None:
        return artifact

    status_str: str | None = None
    amount_paid: int | None = None

    if mcp_dispatch_enabled():
        try:
            data = (
                default_client().fetch_qr_code(artifact.provider_id)
                if artifact.kind == PaymentArtifactKind.QR
                else default_client().fetch_payment_link(artifact.provider_id)
            )
        except Exception:
            data = None
        if data:
            status_str = data.get("status")
            amount_paid = data.get("amount_paid")

    if (
        status_str is None
        and artifact.kind != PaymentArtifactKind.QR
        and settings.razorpay_key_id
        and settings.razorpay_key_secret
    ):
        try:
            data = _build_client().payment_link.fetch(artifact.provider_id) or {}
            status_str = data.get("status")
            amount_paid = data.get("amount_paid")
        except Exception:
            status_str = None

    if status_str == "paid":
        artifact.status = PaymentArtifactStatus.PAID
        artifact.amount_paid_minor = artifact.amount_minor
    elif amount_paid is not None and int(amount_paid) > 0:
        artifact.amount_paid_minor = int(amount_paid)
        artifact.status = (
            PaymentArtifactStatus.PAID
            if artifact.amount_paid_minor >= artifact.amount_minor
            else PaymentArtifactStatus.PARTIALLY_PAID
        )
    elif status_str == "expired":
        artifact.status = PaymentArtifactStatus.EXPIRED

    db.commit()
    db.refresh(artifact)
    _apply_txn_state(db, artifact)
    return artifact


def simulate_paid(db: Session, artifact: PaymentArtifact) -> PaymentArtifact:
    """Force an artifact straight to fully paid, bypassing Razorpay entirely.

    This is the demo/theatre fallback: a simulated QR/link has no
    ``provider_id`` and is never picked up by the background poller (there is
    nothing at Razorpay to poll), and even a real MCP-minted one may not be
    convenient to actually scan-and-pay live. This gives the same end state
    (and the same ``_apply_txn_state`` case side effects) a genuine payment
    would, so ``LiveSession._announce_payment`` can't tell the difference.
    """
    if artifact.status in {PaymentArtifactStatus.PAID, PaymentArtifactStatus.EXPIRED}:
        raise ValueError(f"artifact {artifact.id} is already {artifact.status.value}")

    artifact.status = PaymentArtifactStatus.PAID
    artifact.amount_paid_minor = artifact.amount_minor
    db.commit()
    db.refresh(artifact)
    _apply_txn_state(db, artifact)
    return artifact
