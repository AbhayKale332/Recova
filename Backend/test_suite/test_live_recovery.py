"""The live recovery run — a live recovery run a flagged case step by step."""

import pytest

from application .constants import TransactionLifecycleState
from application .entities import EscalationQueue ,Message ,TransactionState
from application .operations .live_recovery import run_recovery

NOOP =lambda _s :None


def _flagged (db ,tid ="run_1",fc =1 ,run_outcome ="recovered",amount =249900 ):
    db .add (TransactionState (
    transaction_id =tid ,
    razorpay_payment_id =f"pay_{tid }",
    failure_class =fc ,
    current_state =TransactionLifecycleState .PENDING ,
    merchant_id ="m",
    customer_contact ="+919900000000",
    amount_minor =amount ,
    metadata_json ={"customer_name":"Aarav Mehta","is_at_risk":True ,
    "unworked":True ,"run_outcome":run_outcome },
    ))
    db .commit ()


def _draft (_db ,_tid ,_prompt ):
    return "Hi! There was a glitch on our side — here's a secure 1-tap link to finish."


def _events (db ,tid ):
    return list (run_recovery (db ,tid ,pause =NOOP ,drafter =_draft ))


def test_run_streams_the_agent_loop_and_recovers (db_session ):
    _flagged (db_session )
    events =_events (db_session ,"run_1")
    names =[e [0 ]for e in events ]
    assert names [0 ]=="start"
    assert "diagnosis"in names
    assert names .count ("message")>=2
    assert names [-1 ]=="complete"

    row =db_session .query (TransactionState ).filter_by (transaction_id ="run_1").one ()
    assert row .current_state ==TransactionLifecycleState .RECOVERED
    assert (row .metadata_json or {}).get ("unworked")is False
    final =events [-1 ][1 ]
    assert final ["final_state"]=="RECOVERED"
    assert "metrics"in final


def test_diagnosis_event_uses_playbook_enum_key (db_session ):


    _flagged (db_session ,fc =1 )
    events =_events (db_session ,"run_1")
    diag =next (payload for name ,payload in events if name =="diagnosis")
    assert diag ["playbook"]=="REROUTE_RAIL"

    from application .entities import AuditTrail

    row =(
    db_session .query (AuditTrail )
    .filter_by (transaction_id ="run_1",node_name ="DIAGNOSE")
    .one ()
    )
    assert row .payload ["recommended_playbook"]=="REROUTE_RAIL"


def test_run_persists_the_conversation (db_session ):
    _flagged (db_session )
    _events (db_session ,"run_1")
    msgs =db_session .query (Message ).filter_by (transaction_id ="run_1").all ()
    assert any (m .sender .value =="AGENT"for m in msgs )
    assert any (m .sender .value =="CUSTOMER"for m in msgs )


def test_run_optout_stops_compliantly (db_session ):
    _flagged (db_session ,fc =2 ,run_outcome ="optout")
    events =_events (db_session ,"run_1")
    assert events [-1 ][1 ]["final_state"]=="CANCELLED"
    row =db_session .query (TransactionState ).filter_by (transaction_id ="run_1").one ()
    assert row .current_state ==TransactionLifecycleState .CANCELLED


def test_run_dispute_escalates_and_queues (db_session ):
    _flagged (db_session ,fc =4 ,run_outcome ="dispute")
    events =_events (db_session ,"run_1")
    assert events [-1 ][1 ]["final_state"]=="ESCALATED"
    assert db_session .query (EscalationQueue ).filter_by (transaction_id ="run_1").count ()==1


def test_run_b2b_p2p_extracts_and_recovers (db_session ):
    _flagged (db_session ,fc =4 ,run_outcome ="p2p",amount =8400000 )
    events =_events (db_session ,"run_1")
    assert any (e [0 ]=="step"and e [1 ].get ("phase")=="waiting"for e in events )
    row =db_session .query (TransactionState ).filter_by (transaction_id ="run_1").one ()
    assert (row .metadata_json or {}).get ("p2p_date")


def test_run_mandate_places_a_call (db_session ):
    _flagged (db_session ,fc =3 ,run_outcome ="recovered",amount =89900 )
    events =_events (db_session ,"run_1")
    assert any (e [0 ]=="call"for e in events )


def test_run_unknown_transaction_raises (db_session ):
    with pytest .raises (ValueError ):
        _events (db_session ,"nope")
