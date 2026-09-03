"""The assistant's natural-language layer.

``interpret`` turns a chat message into a grounded reply plus, when the user asks
for one, a structured action drawn from a fixed set (run a recovery, set a
status, add a note, navigate). Gemini does the language understanding; the action
itself is built deterministically in code and every ambiguous reference is
resolved against real data. A deterministic keyword parser stands in when the
model is unavailable, so the assistant always answers.
"""

import json

import pytest

from application .constants import TransactionLifecycleState
from application .entities import TransactionState
from application .operations .assistant_service import interpret ,resolve_transaction


def _txn (db ,tid ,name ,fc =4 ,state =TransactionLifecycleState .PENDING ,amount =8400000 ,
ai_tag ="RECOVERY_CASE"):
    db .add (TransactionState (
    transaction_id =tid ,
    razorpay_payment_id =f"pay_{tid }",
    failure_class =fc ,
    current_state =state ,
    merchant_id ="m",
    customer_contact ="+919900000000",
    amount_minor =amount ,
    metadata_json ={"customer_name":name ,"is_at_risk":True ,"ai_tag":ai_tag },
    ))
    db .commit ()


def _gen (payload :dict ):
    """An offline generator that returns the given intent JSON."""
    return lambda _prompt :json .dumps (payload )




def test_resolve_by_name (db_session ):
    _txn (db_session ,"t1","Acme Corp")
    _txn (db_session ,"t2","Zomato Ltd")
    assert resolve_transaction (db_session ,"acme",{})=="t1"


def test_resolve_by_serial_number (db_session ):
    _txn (db_session ,"t1","Acme Corp")
    row =db_session .query (TransactionState ).filter_by (transaction_id ="t1").one ()
    for ref in (str (row .id ),f"#{row .id }",f"transaction {row .id }"):
        assert resolve_transaction (db_session ,ref ,{})=="t1",ref


def test_run_recovery_by_serial (db_session ):
    _txn (db_session ,"t1","Acme Corp",state =TransactionLifecycleState .PENDING )
    row =db_session .query (TransactionState ).filter_by (transaction_id ="t1").one ()
    out =interpret (
    db_session ,f"recover transaction {row .id }",locale ="en",
    generate =_gen ({"intent":"run_recovery","transaction_ref":str (row .id ),
    "reply":"Shall I start recovery — confirm?"}),
    )
    assert out ["action"]["transaction_id"]=="t1"
    assert out ["action"]["requires_confirmation"]is True


def test_resolve_this_uses_focused_context (db_session ):
    _txn (db_session ,"t1","Acme Corp")
    assert resolve_transaction (db_session ,"this one",{"focused_transaction_id":"t1"})=="t1"


def test_resolve_ambiguous_partial_returns_none (db_session ):

    _txn (db_session ,"t1","Acme Mumbai")
    _txn (db_session ,"t2","Acme Delhi")
    assert resolve_transaction (db_session ,"acme",{})is None


def test_resolve_exact_name_duplicate_prefers_runnable (db_session ):


    _txn (db_session ,"t1","Myra Reddy",state =TransactionLifecycleState .RECOVERED )
    _txn (db_session ,"t2","Myra Reddy",state =TransactionLifecycleState .PENDING )
    assert resolve_transaction (db_session ,"Myra Reddy",{})=="t2"




def test_run_recovery_single_asks_confirmation (db_session ):
    _txn (db_session ,"t1","Acme Corp")
    out =interpret (
    db_session ,"recover the Acme invoice",locale ="en",
    generate =_gen ({"intent":"run_recovery","transaction_ref":"Acme",
    "reply":"Shall I start recovery on Acme's case — confirm?"}),
    )
    assert out ["action"]["type"]=="run_recovery"
    assert out ["action"]["scope"]=="one"
    assert out ["action"]["transaction_id"]=="t1"
    assert out ["action"]["requires_confirmation"]is True
    assert out ["reply"]


def test_run_recovery_named_customer_with_many_cases_asks_all_or_one (db_session ):

    _txn (db_session ,"t1","Ananya Nair",fc =1 ,state =TransactionLifecycleState .PENDING )
    _txn (db_session ,"t2","Ananya Nair",fc =3 ,state =TransactionLifecycleState .PENDING )
    out =interpret (
    db_session ,"recover ananya nair",locale ="en",
    generate =_gen ({"intent":"run_recovery","transaction_ref":"Ananya Nair",
    "reply":"Ananya has two open cases — all or one?"}),
    )
    assert out ["action"]["scope"]=="batch"
    assert set (out ["action"]["transaction_ids"])=={"t1","t2"}


def test_set_status_requires_confirmation (db_session ):
    _txn (db_session ,"t1","Acme Corp")
    out =interpret (
    db_session ,"mark this recovered",locale ="en",
    context ={"focused_transaction_id":"t1"},
    generate =_gen ({"intent":"set_status","transaction_ref":"this",
    "status":"RECOVERED","reply":"I'll mark it recovered — confirm?"}),
    )
    assert out ["action"]["type"]=="set_status"
    assert out ["action"]["transaction_id"]=="t1"
    assert out ["action"]["status"]=="RECOVERED"
    assert out ["action"]["requires_confirmation"]is True


def test_add_note_no_confirmation (db_session ):
    _txn (db_session ,"t1","Acme Corp")
    out =interpret (
    db_session ,"add a note: customer promised Friday",locale ="en",
    context ={"focused_transaction_id":"t1"},
    generate =_gen ({"intent":"add_note","transaction_ref":"this",
    "note":"customer promised Friday","reply":"Noted."}),
    )
    assert out ["action"]["type"]=="add_note"
    assert out ["action"]["transaction_id"]=="t1"
    assert out ["action"]["note"]=="customer promised Friday"
    assert out ["action"]["requires_confirmation"]is False


def test_navigate_maps_to_route (db_session ):
    out =interpret (
    db_session ,"show me the overdue invoices",locale ="en",
    generate =_gen ({"intent":"navigate","route":"class:4",
    "reply":"Opening overdue invoices."}),
    )
    assert out ["action"]["type"]=="navigate"
    assert out ["action"]["route"]=="/mission-control/class/4"


def test_navigate_with_status_filter (db_session ):

    out =interpret (
    db_session ,"show only recovered failed payments",locale ="en",
    generate =_gen ({"intent":"navigate","route":"class:1","status":"RECOVERED",
    "reply":"Showing recovered failed payments."}),
    )
    assert out ["action"]["type"]=="navigate"
    assert out ["action"]["route"]=="/mission-control/class/1"
    assert out ["action"]["status"]=="RECOVERED"


def test_navigate_ignores_invalid_status_filter (db_session ):
    out =interpret (
    db_session ,"open transactions",locale ="en",
    generate =_gen ({"intent":"navigate","route":"transactions","status":"BOGUS",
    "reply":"Opening transactions."}),
    )
    assert out ["action"]["type"]=="navigate"
    assert out ["action"]["status"]is None


def test_run_recovery_batch_asks_scope (db_session ):
    _txn (db_session ,"a1","One",fc =1 ,state =TransactionLifecycleState .PENDING )
    _txn (db_session ,"a2","Two",fc =1 ,state =TransactionLifecycleState .PENDING )
    _txn (db_session ,"b1","Three",fc =2 ,state =TransactionLifecycleState .PENDING )
    out =interpret (
    db_session ,"recover all of these",locale ="en",
    context ={"route":"/mission-control/class/1"},
    generate =_gen ({"intent":"run_recovery","scope":"batch",
    "reply":"You're viewing 2 recoverable cases. Recover all 2, or just one?"}),
    )
    a =out ["action"]
    assert a ["type"]=="run_recovery"
    assert a ["scope"]=="batch"

    assert set (a ["transaction_ids"])=={"a1","a2"}
    assert "2"in out ["reply"]


def test_fallback_batch_detection (db_session ):
    _txn (db_session ,"a1","One",fc =1 ,state =TransactionLifecycleState .PENDING )
    _txn (db_session ,"a2","Two",fc =1 ,state =TransactionLifecycleState .PENDING )

    def boom (_p ):
        raise RuntimeError ("model down")

    out =interpret (db_session ,"recover all these cases",locale ="en",
    context ={"route":"/mission-control/class/1"},generate =boom )
    assert out ["action"]["scope"]=="batch"
    assert set (out ["action"]["transaction_ids"])=={"a1","a2"}


def test_recover_batch_endpoint (client ,db_session ):
    _txn (db_session ,"a1","One",fc =1 ,state =TransactionLifecycleState .PENDING )
    _txn (db_session ,"a2","Two",fc =1 ,state =TransactionLifecycleState .PENDING )
    resp =client .post ("/api/v1/transactions/recover-batch",
    json ={"transaction_ids":["a1","a2"]})
    assert resp .status_code ==200
    body =resp .json ()
    assert body ["total"]==2


def test_answer_has_no_action (db_session ):
    _txn (db_session ,"t1","Acme Corp",state =TransactionLifecycleState .RECOVERED )
    out =interpret (
    db_session ,"how are we doing?",locale ="en",
    generate =_gen ({"intent":"answer","reply":"We've recovered ₹84,000 so far."}),
    )
    assert out ["action"]is None
    assert out ["reply"]




def test_fallback_handles_recover_verb (db_session ):
    _txn (db_session ,"t1","Acme Corp")

    def boom (_p ):
        raise RuntimeError ("model down")

    out =interpret (db_session ,"recover Acme",locale ="en",generate =boom )
    assert out ["action"]["type"]=="run_recovery"
    assert out ["action"]["transaction_id"]=="t1"


def test_fallback_answers_data_question_grounded (db_session ):

    _txn (db_session ,"t1","Acme Corp",state =TransactionLifecycleState .RECOVERED )

    def boom (_p ):
        raise RuntimeError ("model down")

    out =interpret (db_session ,"how much have we recovered?",locale ="en",generate =boom )
    assert out ["action"]is None
    assert "84,000"in out ["reply"]or "84000"in out ["reply"]or "84"in out ["reply"]


def test_chat_endpoint_answers_offline (client ,db_session ):
    _txn (db_session ,"t1","Acme Corp",state =TransactionLifecycleState .RECOVERED )
    resp =client .post ("/api/v1/assistant/chat",json ={"message":"how much have we recovered?"})
    assert resp .status_code ==200
    body =resp .json ()
    assert body ["action"]is None
    assert body ["reply"]


def test_chat_endpoint_returns_run_action (client ,db_session ):
    _txn (db_session ,"t1","Acme Corp")
    resp =client .post ("/api/v1/assistant/chat",json ={"message":"recover Acme"})
    assert resp .status_code ==200
    action =resp .json ()["action"]
    assert action ["type"]=="run_recovery"
    assert action ["transaction_id"]=="t1"


def test_fallback_navigate_pending_filter (db_session ):
    def boom (_p ):
        raise RuntimeError ("model down")

    out =interpret (db_session ,"show pending failed payments",locale ="en",generate =boom )
    assert out ["action"]["type"]=="navigate"
    assert out ["action"]["route"]=="/mission-control/class/1"
    assert out ["action"]["status"]=="PENDING"


def test_fallback_navigate_plain_class_has_no_status (db_session ):

    def boom (_p ):
        raise RuntimeError ("model down")

    out =interpret (db_session ,"show failed payments",locale ="en",generate =boom )
    assert out ["action"]["type"]=="navigate"
    assert out ["action"]["route"]=="/mission-control/class/1"
    assert out ["action"]["status"]is None


def test_fallback_escalate_sets_status (db_session ):
    _txn (db_session ,"t1","Acme Corp")

    def boom (_p ):
        raise RuntimeError ("model down")

    out =interpret (db_session ,"escalate this",locale ="en",
    context ={"focused_transaction_id":"t1"},generate =boom )
    assert out ["action"]["type"]=="set_status"
    assert out ["action"]["status"]=="ESCALATED"
    assert out ["action"]["requires_confirmation"]is True
