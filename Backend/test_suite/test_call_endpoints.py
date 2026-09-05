"""On-demand AI voice call: start a (simulated) call for any transaction."""

from datetime import datetime

import pytest

from application .endpoints .transaction_api import _call_clock
from application .entities import CallSession ,TransactionState
from application .helpers import IST
from application .server import app


def _pin_clock (moment :datetime )->None :
    app .dependency_overrides [_call_clock ]=lambda :(lambda :moment )


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


def test_start_call_quiet_hours_refusal_409_naming_trai_quiet_hours (txn ,db_session ):
    _pin_clock (datetime (2026 ,3 ,4 ,21 ,40 ,tzinfo =IST ))
    resp =txn .post ("/api/v1/transactions/call_1/call/start")
    assert resp .status_code ==409
    assert "TRAI_QUIET_HOURS" in resp .json ()["detail"]


def test_start_call_voice_cap_refusal_409_naming_voice_attempt_cap (txn ,db_session ):
    _pin_clock (datetime (2026 ,3 ,4 ,11 ,0 ,tzinfo =IST ))
    # First call at daytime succeeds
    r1 =txn .post ("/api/v1/transactions/call_1/call/start")
    assert r1 .status_code ==201
    # Second call at daytime succeeds (voice cap is 2)
    r2 =txn .post ("/api/v1/transactions/call_1/call/start")
    assert r2 .status_code ==201
    # Third call exceeds the cap -> 409 naming VOICE_ATTEMPT_CAP
    r3 =txn .post ("/api/v1/transactions/call_1/call/start")
    assert r3 .status_code ==409
    assert "VOICE_ATTEMPT_CAP" in r3 .json ()["detail"]


def test_start_call_respects_authored_clock_ist_on_the_transaction (txn ,db_session ):
    """A case authored with a clock_ist in its metadata pins the gate's clock,

    without any caller-supplied override - the bypass this replaces let any
    request set the clock; this lets only whoever authored the case do so.
    """
    row =db_session .query (TransactionState ).filter_by (transaction_id ="call_1").one ()
    row .metadata_json ={**(row .metadata_json or {}),"clock_ist":"21:40"}
    db_session .commit ()
    resp =txn .post ("/api/v1/transactions/call_1/call/start")
    assert resp .status_code ==409
    assert "TRAI_QUIET_HOURS" in resp .json ()["detail"]


def test_start_call_clock_ist_query_param_no_longer_bypasses_the_gate (txn ,db_session ):
    """The removed public override: passing clock_ist on the request must do nothing."""
    _pin_clock (datetime (2026 ,3 ,4 ,21 ,40 ,tzinfo =IST ))
    resp =txn .post ("/api/v1/transactions/call_1/call/start?clock_ist=2026-03-04T11:00:00%2B05:30")
    assert resp .status_code ==409
    assert "TRAI_QUIET_HOURS" in resp .json ()["detail"]
