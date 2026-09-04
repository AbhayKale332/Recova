"""One durable source for the voice-attempt bound."""

from sqlalchemy.orm import Session

from application.constants import ActionType, InterventionChannel
from application.entities import AuditTrail


def voice_attempt_count(db: Session, transaction_id: str, seeded: int | None = None) -> int:
    """Return seeded attempts when supplied, otherwise count voice dispatch audits."""
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
    return sum(1 for row in rows if (row.payload or {}).get("channel") == InterventionChannel.VOICE.value)
