"""AI message drafting: Gemini writes a WhatsApp line from the conversation
context + the flagged problem; a template fallback keeps it working offline."""

import pytest

from application .constants import MessageDirection ,MessageSender
from application .entities import Message ,TransactionState
from application .operations .message_drafter import draft_message


def _txn (db ,tid ="draft_1",name ="Aarav Mehta",fc =4 ,amount =8400000 ):
    t =TransactionState (
    transaction_id =tid ,
    razorpay_payment_id =f"pay_{tid }",
    failure_class =fc ,
    merchant_id ="m",
    customer_contact ="+919900000000",
    amount_minor =amount ,
    metadata_json ={"customer_name":name ,"class_label":"B2B Receivables"},
    )
    db .add (t )
    db .add (Message (
    transaction_id =tid ,direction =MessageDirection .OUTBOUND ,sender =MessageSender .AGENT ,
    body ="Invoice INV-2601 is overdue.",seq =0 ,
    ))
    db .commit ()
    return t


def test_draft_uses_injected_generator (db_session ):
    _txn (db_session )
    out =draft_message (
    db_session ,"draft_1","remind them to pay the invoice",
    generate =lambda _p :"Gentle reminder about your overdue invoice — please pay when you can.",
    )
    assert "reminder"in out .lower ()


def test_draft_prompt_carries_context (db_session ):
    _txn (db_session ,name ="Diya Kapoor")
    captured ={}
    def fake (prompt :str )->str :
        captured ["p"]=prompt
        return "ok"
    draft_message (db_session ,"draft_1","ask for a payment date",generate =fake )

    assert "Diya"in captured ["p"]
    assert "invoice"in captured ["p"].lower ()or "overdue"in captured ["p"].lower ()


def test_draft_falls_back_to_template_on_failure (db_session ):
    _txn (db_session ,name ="Kabir Singh")
    def boom (_p :str )->str :
        raise RuntimeError ("model unavailable")
    out =draft_message (db_session ,"draft_1","remind to pay",generate =boom )
    assert out .strip ()
    assert "Kabir"in out


def test_explicit_none_keeps_batch_drafting_model_free (db_session ,monkeypatch ):
    _txn (db_session ,name ="Batch Customer")

    def must_not_build (*_args ,**_kwargs ):
        raise AssertionError ("batch drafting must not build a model")

    monkeypatch.setattr (
    "application.operations.message_drafter._default_generate",must_not_build
    )
    out =draft_message (db_session ,"draft_1","remind to pay",generate =None )
    assert "Batch"in out


def test_omitting_generate_still_builds_the_routed_generator (db_session ,monkeypatch ):
    _txn (db_session ,name ="Live Customer")
    captured ={}

    def routed (prompt :str )->str :
        captured ["prompt"] =prompt
        return "routed reply"

    monkeypatch.setattr (
    "application.operations.message_drafter._default_generate",lambda amount :routed
    )
    out =draft_message (db_session ,"draft_1","ask for a payment date")
    assert out =="routed reply"
    assert "Live Customer"in captured ["prompt"]


def _has_devanagari (s :str )->bool :
    return any ("ऀ"<=ch <="ॿ"for ch in s )


def test_draft_hindi_locale_instructs_the_model_in_hindi (db_session ):
    _txn (db_session ,name ="Diya Kapoor")
    captured ={}
    def fake (prompt :str )->str :
        captured ["p"]=prompt
        return "theek hai"
    draft_message (db_session ,"draft_1","ask for a payment date",generate =fake ,locale ="hi")
    assert "Hindi"in captured ["p"]or _has_devanagari (captured ["p"])


def test_draft_hindi_fallback_is_devanagari (db_session ):
    _txn (db_session ,name ="Kabir Singh")
    def boom (_p :str )->str :
        raise RuntimeError ("model unavailable")
    out =draft_message (db_session ,"draft_1","remind to pay",generate =boom ,locale ="hi")
    assert out .strip ()
    assert _has_devanagari (out )


def test_draft_unknown_transaction_raises (db_session ):
    with pytest .raises (ValueError ):
        draft_message (db_session ,"nope","hi",generate =lambda _p :"x")
