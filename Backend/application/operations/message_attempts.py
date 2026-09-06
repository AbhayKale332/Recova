"""One durable source for the outbound WhatsApp nudge count."""

from sqlalchemy.orm import Session

from application.constants import ActionType, InterventionChannel
from application.entities import AuditTrail


def whatsapp_nudge_count(db: Session, transaction_id: str, seeded: int | None = None) -> int:
    """Return seeded nudges when supplied, otherwise count WhatsApp dispatch audits.

    Counts the same ``INTERVENTION_DISPATCH`` rows the bounds gauge does, so a
    seeded case and a live case never disagree on how many messages have gone
    out. A payment-link or QR dispatch is on the ``PAYMENT_LINK`` channel and is
    not counted here, even when a covering message rides along with it.
    """
    if seeded is not None:
        return int(seeded)
    rows = (
        db.query(AuditTrail)
        .filter(
            AuditTrail.transaction_id == transaction_id,
            AuditTrail.action_type == ActionType.INTERVENTION_DISPATCH,
        )
        .all()
    )
    return sum(
        1 for row in rows if (row.payload or {}).get("channel") == InterventionChannel.WHATSAPP.value
    )
