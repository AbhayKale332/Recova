"""Conversation endpoints: read the thread, send a message, AI-draft a message."""

import pytest

from application .constants import CallSpeaker ,CallStatus ,MessageDirection ,MessageSender
from application .entities import CallSession ,CallTurn ,Message ,TransactionState


@pytest .fixture ()
def seeded_txn (client ,db_session ):
    t =TransactionState (
    transaction_id ="api_1",
    razorpay_payment_id ="pay_api_1",
    failure_class =4 ,
    merchant_id ="m",
    customer_contact ="+919900000000",
    amount_minor =8400000 ,
    metadata_json ={"customer_name":"Aarav Mehta"},
    )
    db_session .add (t )
    db_session .add (Message (
    transaction_id ="api_1",direction =MessageDirection .OUTBOUND ,
    sender =MessageSender .AGENT ,body ="Invoice INV-2601 is overdue.",seq =0 ,
    ))
    cs =CallSession (transaction_id ="api_1",status =CallStatus .COMPLETED ,duration_sec =30 ,outcome ="p2p")
    db_session .add (cs )
    db_session .flush ()
    db_session .add (CallTurn (call_session_id =cs .id ,speaker =CallSpeaker .AGENT ,text ="Namaste",seq =0 ,at_offset_sec =0 ))
    db_session .commit ()
    return client


def test_get_conversation_returns_messages_and_call (seeded_txn ):
    resp =seeded_txn .get ("/api/v1/transactions/api_1/conversation")
    assert resp .status_code ==200
    body =resp .json ()
    assert len (body ["messages"])==1
    assert body ["messages"][0 ]["sender"]=="AGENT"
    assert body ["call"]["duration_sec"]==30
    assert body ["call"]["turns"][0 ]["speaker"]=="AGENT"


def test_get_conversation_404 (seeded_txn ):
    assert seeded_txn .get ("/api/v1/transactions/nope/conversation").status_code ==404


def test_send_message_appends (seeded_txn ):
    resp =seeded_txn .post (
    "/api/v1/transactions/api_1/messages",json ={"body":"Gentle reminder about your invoice."}
    )
    assert resp .status_code ==201
    assert resp .json ()["seq"]==1

    convo =seeded_txn .get ("/api/v1/transactions/api_1/conversation").json ()
    assert len (convo ["messages"])==2
    assert convo ["messages"][1 ]["body"].startswith ("Gentle reminder")


def test_draft_returns_text_offline (seeded_txn ):

    resp =seeded_txn .post (
    "/api/v1/transactions/api_1/messages/draft",json ={"prompt":"remind them to pay"}
    )
    assert resp .status_code ==200
    draft =resp .json ()["draft"]
    assert draft .strip ()
    assert "Aarav"in draft


def test_draft_404 (seeded_txn ):
    assert (
    seeded_txn .post ("/api/v1/transactions/nope/messages/draft",json ={"prompt":"hi"}).status_code
    ==404
    )
