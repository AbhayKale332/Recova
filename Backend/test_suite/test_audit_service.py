from application .constants import ActionType ,FailureClass ,NodeName ,Outcome ,TransactionLifecycleState
from application .entities import AuditTrail ,TransactionState
from application .operations .audit_service import record_audit


def _seed_transaction (db_session ):
    txn =TransactionState (
    transaction_id ="txn_audit",
    razorpay_payment_id ="pay_audit",
    failure_class =FailureClass .REALTIME_DEGRADATION ,
    current_state =TransactionLifecycleState .PENDING ,
    merchant_id ="merch_1",
    customer_contact ="+919999999999",
    amount_minor =150000 ,
    )
    db_session .add (txn )
    db_session .commit ()


def test_record_audit_persists_entry (db_session ):
    _seed_transaction (db_session )

    entry =record_audit (
    db_session ,
    transaction_id ="txn_audit",
    node_name =NodeName .INGEST ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"event":"WEBHOOK_INGESTED"},
    outcome =Outcome .SUCCESS ,
    )

    stored =db_session .query (AuditTrail ).filter_by (id =entry .id ).one ()
    assert stored .transaction_id =="txn_audit"
    assert stored .payload =={"event":"WEBHOOK_INGESTED"}
    assert stored .outcome ==Outcome .SUCCESS


def test_record_audit_generates_unique_event_ids (db_session ):
    _seed_transaction (db_session )

    first =record_audit (
    db_session ,
    transaction_id ="txn_audit",
    node_name =NodeName .INGEST ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"n":1 },
    outcome =Outcome .SUCCESS ,
    )
    second =record_audit (
    db_session ,
    transaction_id ="txn_audit",
    node_name =NodeName .DIAGNOSE ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"n":2 },
    outcome =Outcome .SUCCESS ,
    )


    assert first .event_id !=second .event_id
