"""On-demand AI voice call: start a (simulated) call for any transaction."""

import pytest

from application .entities import CallSession ,TransactionState


@pytest .fixture ()
def txn (client ,db_session ):
    db_session .add (TransactionState (
    transaction_id ="call_1",
    razorpay_payment_id ="pay_call_1",
    failure_class =4 ,
    merchant_id ="m",
    customer_contact ="+919900000000",
    amount_minor =8400000 ,
    metadata_json ={"customer_name":"Aarav Mehta"},
    ))
    db_session .commit ()
    return client


def test_start_call_creates_session_with_transcript (txn ,db_session ):
    resp =txn .post ("/api/v1/transactions/call_1/call/start")
    assert resp .status_code ==201
    call =resp .json ()
    assert call ["status"]
    assert len (call ["turns"])>=3
    assert call ["turns"][0 ]["speaker"]=="AGENT"
    assert call ["provider"]=="simulated"

    assert db_session .query (CallSession ).filter_by (transaction_id ="call_1").count ()==1
    convo =txn .get ("/api/v1/transactions/call_1/conversation").json ()
    assert convo ["call"]is not None


def test_start_call_404_for_unknown (txn ):
    assert txn .post ("/api/v1/transactions/nope/call/start").status_code ==404


def test_call_log_lists_all_calls_newest_first (txn ):
    txn .post ("/api/v1/transactions/call_1/call/start")
    txn .post ("/api/v1/transactions/call_1/call/start")
    resp =txn .get ("/api/v1/transactions/call_1/calls")
    assert resp .status_code ==200
    calls =resp .json ()["calls"]
    assert len (calls )==2
    assert calls [0 ]["id"]>calls [1 ]["id"]
    assert calls [0 ]["started_at"]
    assert calls [0 ]["turns"]


def test_call_log_404 (txn ):
    assert txn .get ("/api/v1/transactions/nope/calls").status_code ==404
