"""Persistence model for a minted Razorpay payment artifact (link, UPI link, or QR)."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
)

from application.persistence import Base
from application.constants import PaymentArtifactKind, PaymentArtifactStatus
from application.helpers import utcnow


class PaymentArtifact(Base):
    """One Razorpay artifact minted for a case: a link, UPI link, or QR.

    A new table, so schema creation needs no migration. The case's own
    outstanding-balance position lives on ``TransactionState.metadata_json``
    (see ``operations/payment_artifacts.py``); this row is the record of what
    was actually minted and its own payment status.
    """

    __tablename__ = "payment_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(
        String(64),
        ForeignKey("transaction_states.transaction_id"),
        index=True,
        nullable=False,
    )
    kind = Column(Enum(PaymentArtifactKind, validate_strings=True), nullable=False)
    provider_id = Column(String(64), nullable=True)
    url = Column(String(512), nullable=True)
    image_url = Column(String(512), nullable=True)
    amount_minor = Column(Integer, nullable=False)
    accept_partial = Column(Boolean, default=False, nullable=False)
    first_min_partial_minor = Column(Integer, nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        Enum(PaymentArtifactStatus, validate_strings=True),
        default=PaymentArtifactStatus.CREATED,
        nullable=False,
    )
    amount_paid_minor = Column(Integer, default=0, nullable=False)
    simulated = Column(Boolean, default=False, nullable=False)
    detail = Column(String(16), nullable=False)
    followed_up_at = Column(DateTime(timezone=True), nullable=True)
    meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "kind": self.kind.value,
            "provider_id": self.provider_id,
            "url": self.url,
            "image_url": self.image_url,
            "amount_minor": self.amount_minor,
            "accept_partial": self.accept_partial,
            "first_min_partial_minor": self.first_min_partial_minor,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "status": self.status.value,
            "amount_paid_minor": self.amount_paid_minor,
            "simulated": self.simulated,
            "detail": self.detail,
            "created_at": self.created_at.isoformat(),
        }
