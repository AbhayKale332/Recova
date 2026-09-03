import pytest
from sqlalchemy import text
from sqlalchemy .exc import InvalidRequestError ,IntegrityError

from application .constants import (
ActionType ,
FailureClass ,
NodeName ,
Outcome ,
TransactionLifecycleState ,
)
from application .entities import AuditTrail ,TransactionState


def _make_transaction (**overrides ):
    defaults =dict (
    transaction_id ="txn_1",
    razorpay_payment_id ="pay_1",
    failure_class =FailureClass .SUBSCRIPTION_MANDATE ,
    current_state =TransactionLifecycleState .PENDING ,
    merchant_id ="merch_1",
    customer_contact ="+919999999999",
    amount_minor =150000 ,
    currency ="INR",
    )
    defaults .update (overrides )
    return TransactionState (**defaults )


def test_transaction_persists_and_encrypts_contact (db_session ):
    txn =_make_transaction ()
    db_session .add (txn )
    db_session .commit ()


    assert txn .customer_contact =="+919999999999"


    raw =db_session .execute (
    text ("SELECT customer_contact FROM transaction_states WHERE id = :id"),
    {"id":txn .id },
    ).scalar_one ()
    assert raw !="+919999999999"


def test_failure_class_check_constraint (db_session ):
    db_session .add (_make_transaction (transaction_id ="txn_bad",failure_class =9 ))
    with pytest .raises (IntegrityError ):
        db_session .commit ()


def test_audit_trail_is_append_only (db_session ):
    db_session .add (_make_transaction ())
    db_session .commit ()

    entry =AuditTrail (
    event_id ="evt_1",
    transaction_id ="txn_1",
    node_name =NodeName .INGEST ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"from":"PENDING","to":"DIAGNOSING"},
    outcome =Outcome .SUCCESS ,
    )
    db_session .add (entry )
    db_session .commit ()


    entry .outcome =Outcome .FAILURE
    with pytest .raises (InvalidRequestError ):
        db_session .commit ()
    db_session .rollback ()


    db_session .delete (entry )
    with pytest .raises (InvalidRequestError ):
        db_session .commit ()
    db_session .rollback ()
