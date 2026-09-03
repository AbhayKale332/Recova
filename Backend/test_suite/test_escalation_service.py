from application .constants import (
EscalationStatus ,
FailureClass ,
StoppingRule ,
TransactionLifecycleState ,
)
from application .entities import EscalationQueue ,TransactionState
from application .operations .escalation_service import enqueue_escalation


def _seed_transaction (db_session ):
    db_session .add (
    TransactionState (
    transaction_id ="txn_esc",
    razorpay_payment_id ="pay_esc",
    failure_class =FailureClass .B2B_RECEIVABLES ,
    current_state =TransactionLifecycleState .INTERVENING ,
    merchant_id ="merch_1",
    customer_contact ="+919999999999",
    amount_minor =500000 ,
    )
    )
    db_session .commit ()


def test_enqueue_creates_open_ticket (db_session ):
    _seed_transaction (db_session )

    ticket =enqueue_escalation (
    db_session ,
    transaction_id ="txn_esc",
    reason ="Customer disputes the invoice line item.",
    rule =StoppingRule .DISPUTE_FREEZE ,
    )

    stored =db_session .query (EscalationQueue ).filter_by (id =ticket .id ).one ()
    assert stored .transaction_id =="txn_esc"
    assert stored .status ==EscalationStatus .OPEN
    assert stored .rule ==StoppingRule .DISPUTE_FREEZE
    assert "disputes"in stored .reason .lower ()


def test_enqueue_without_rule_is_allowed (db_session ):

    _seed_transaction (db_session )
    ticket =enqueue_escalation (
    db_session ,
    transaction_id ="txn_esc",
    reason ="Unrecognised failure signal.",
    )
    assert ticket .rule is None
    assert ticket .status ==EscalationStatus .OPEN
