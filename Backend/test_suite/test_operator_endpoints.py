"""Operator actions: work the recovery by hand — change status, add notes,
resolve escalations — each written to the append-only audit trail."""

import pytest

from application .constants import StoppingRule ,TransactionLifecycleState
from application .entities import AuditTrail ,EscalationQueue ,TransactionState


@pytest .fixture ()
def txn (client ,db_session ):
    db_session .add (TransactionState (
    transaction_id ="op_1",
    razorpay_payment_id ="pay_op_1",
    failure_class =2 ,
    current_state =TransactionLifecycleState .INTERVENING ,
    merchant_id ="m",
    customer_contact ="+919900000000",
    amount_minor =149900 ,
    metadata_json ={"customer_name":"Aarav Mehta","is_at_risk":True },
    ))
    db_session .commit ()
    return client


def test_operator_marks_recovered (txn ,db_session ):
    resp =txn .post ("/api/v1/transactions/op_1/status",json ={"status":"RECOVERED","note":"Customer paid"})
    assert resp .status_code ==200
    assert resp .json ()["status"]=="RECOVERED"
    row =db_session .query (TransactionState ).filter_by (transaction_id ="op_1").one ()
    assert row .current_state ==TransactionLifecycleState .RECOVERED

    entry =(
    db_session .query (AuditTrail )
    .filter_by (transaction_id ="op_1")
    .order_by (AuditTrail .id .desc ())
    .first ()
    )
    assert entry .node_name .value =="OPERATOR"
    assert entry .payload ["to"]=="RECOVERED"
    assert entry .payload ["note"]=="Customer paid"


def test_recovered_reflects_in_metrics (txn ):
    before =txn .get ("/api/v1/metrics").json ()["counts"]["recovered"]
    txn .post ("/api/v1/transactions/op_1/status",json ={"status":"RECOVERED"})
    after =txn .get ("/api/v1/metrics").json ()["counts"]["recovered"]
    assert after ==before +1


def test_escalating_enqueues_a_ticket (txn ,db_session ):
    txn .post ("/api/v1/transactions/op_1/status",json ={"status":"ESCALATED","note":"needs a human"})
    tickets =db_session .query (EscalationQueue ).filter_by (transaction_id ="op_1").all ()
    assert len (tickets )==1
    assert tickets [0 ].status .value =="OPEN"


def test_invalid_status_rejected (txn ):
    assert txn .post ("/api/v1/transactions/op_1/status",json ={"status":"BOGUS"}).status_code ==422


def test_status_404 (txn ):
    assert txn .post ("/api/v1/transactions/nope/status",json ={"status":"RECOVERED"}).status_code ==404


def test_add_note (txn ,db_session ):
    resp =txn .post ("/api/v1/transactions/op_1/note",json ={"note":"Left a voicemail"})
    assert resp .status_code ==201
    entry =(
    db_session .query (AuditTrail )
    .filter_by (transaction_id ="op_1")
    .order_by (AuditTrail .id .desc ())
    .first ()
    )
    assert entry .node_name .value =="OPERATOR"
    assert entry .payload ["note"]=="Left a voicemail"


def test_resolve_escalation (txn ,db_session ):
    db_session .add (EscalationQueue (transaction_id ="op_1",reason ="dispute",rule =StoppingRule .DISPUTE_FREEZE ))
    db_session .commit ()
    ticket_id =db_session .query (EscalationQueue ).one ().id
    resp =txn .post (f"/api/v1/escalations/{ticket_id }/resolve",json ={})
    assert resp .status_code ==200
    assert resp .json ()["status"]=="RESOLVED"


def test_resolve_escalation_404 (txn ):
    assert txn .post ("/api/v1/escalations/9999/resolve",json ={}).status_code ==404
