"""Tests for the Part 5 deadline sweeper.

Each test drives ``deadline_sweeper._tick`` directly against an in-memory DB
with a fixed clock, rather than the real ``run_forever`` loop - the loop
itself is just ``asyncio.sleep`` + ``_tick``, so there is nothing else to
exercise there.
"""

from datetime import datetime, timedelta

from application.constants import FailureClass, PaymentArtifactKind
from application.entities import Message, TransactionState
from application.helpers import IST
from application.operations import deadline_sweeper, payment_artifacts

BUSINESS_HOURS_IST = datetime(2026, 3, 4, 11, 0, tzinfo=IST)
QUIET_HOURS_IST = datetime(2026, 3, 4, 21, 40, tzinfo=IST)


def _make_txn(db, transaction_id="txn_sweep_1", amount_minor=500000):
    txn = TransactionState(
        transaction_id=transaction_id,
        razorpay_payment_id="pay_sweep_1",
        failure_class=FailureClass.B2B_RECEIVABLES,
        merchant_id="m1",
        customer_contact="+919999999999",
        amount_minor=amount_minor,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def _make_partial_artifact(db, txn, *, deadline, amount_minor=200000):
    return payment_artifacts.mint(
        db,
        txn,
        PaymentArtifactKind.LINK,
        amount_minor=amount_minor,
        accept_partial=True,
        first_min_partial_minor=amount_minor,
        deadline=deadline,
    )


def test_sweeper_sends_followup_when_deadline_passed_and_balance_remains(db_session):
    txn = _make_txn(db_session)
    artifact = _make_partial_artifact(
        db_session, txn, deadline=BUSINESS_HOURS_IST - timedelta(days=1)
    )

    deadline_sweeper._tick(db_session, clock=BUSINESS_HOURS_IST)

    db_session.refresh(artifact)
    assert artifact.followed_up_at is not None

    messages = db_session.query(Message).filter_by(transaction_id=txn.transaction_id).all()
    assert len(messages) == 1
    assert "3,000" in messages[0].body or "₹3,000" in messages[0].body
    assert messages[0].meta_json["deadline_followup"] is True


def test_sweeper_is_idempotent(db_session):
    txn = _make_txn(db_session)
    _make_partial_artifact(db_session, txn, deadline=BUSINESS_HOURS_IST - timedelta(days=1))

    deadline_sweeper._tick(db_session, clock=BUSINESS_HOURS_IST)
    deadline_sweeper._tick(db_session, clock=BUSINESS_HOURS_IST + timedelta(minutes=1))

    messages = db_session.query(Message).filter_by(transaction_id=txn.transaction_id).all()
    assert len(messages) == 1


def test_sweeper_skips_a_reconciled_paid_artifact(db_session):
    txn = _make_txn(db_session)
    artifact = _make_partial_artifact(
        db_session, txn, deadline=BUSINESS_HOURS_IST - timedelta(days=1)
    )
    payment_artifacts.simulate_paid(db_session, artifact)
    db_session.refresh(artifact)
    assert artifact.status.value == "paid"

    deadline_sweeper._tick(db_session, clock=BUSINESS_HOURS_IST)

    db_session.refresh(artifact)
    assert artifact.followed_up_at is None
    messages = db_session.query(Message).filter_by(transaction_id=txn.transaction_id).all()
    assert len(messages) == 0


def test_sweeper_defers_inside_quiet_hours(db_session):
    txn = _make_txn(db_session)
    artifact = _make_partial_artifact(
        db_session, txn, deadline=BUSINESS_HOURS_IST - timedelta(days=1)
    )

    deadline_sweeper._tick(db_session, clock=QUIET_HOURS_IST)

    db_session.refresh(artifact)
    assert artifact.followed_up_at is None
    messages = db_session.query(Message).filter_by(transaction_id=txn.transaction_id).all()
    assert len(messages) == 0

    # The next tick, once quiet hours have passed, sends the follow-up.
    deadline_sweeper._tick(db_session, clock=BUSINESS_HOURS_IST + timedelta(days=1))
    db_session.refresh(artifact)
    assert artifact.followed_up_at is not None


def test_sweeper_ignores_a_future_deadline(db_session):
    txn = _make_txn(db_session)
    artifact = _make_partial_artifact(
        db_session, txn, deadline=BUSINESS_HOURS_IST + timedelta(days=1)
    )

    deadline_sweeper._tick(db_session, clock=BUSINESS_HOURS_IST)

    db_session.refresh(artifact)
    assert artifact.followed_up_at is None
    assert db_session.query(Message).filter_by(transaction_id=txn.transaction_id).count() == 0
