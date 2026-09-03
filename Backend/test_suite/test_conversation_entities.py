"""Conversation persistence: the WhatsApp thread + call transcript per transaction."""

from application .constants import (
CallSpeaker ,
CallStatus ,
MessageDirection ,
MessageSender ,
MessageStatus ,
)
from application .entities import CallSession ,CallTurn ,Message ,TransactionState


def _txn (db ,tid ="conv_1"):
    t =TransactionState (
    transaction_id =tid ,
    razorpay_payment_id =f"pay_{tid }",
    failure_class =4 ,
    merchant_id ="m",
    customer_contact ="+919900000000",
    amount_minor =8400000 ,
    )
    db .add (t )
    db .commit ()
    return t


def test_message_thread_persists_and_orders (db_session ):
    _txn (db_session )
    for i ,(direction ,sender ,body )in enumerate (
    [
    (MessageDirection .OUTBOUND ,MessageSender .AGENT ,"Namaste, your invoice is overdue."),
    (MessageDirection .INBOUND ,MessageSender .CUSTOMER ,"5 tarikh ko kar denge."),
    ]
    ):
        db_session .add (
        Message (
        transaction_id ="conv_1",
        direction =direction ,
        sender =sender ,
        body =body ,
        status =MessageStatus .DELIVERED ,
        seq =i ,
        )
        )
    db_session .commit ()

    rows =(
    db_session .query (Message )
    .filter_by (transaction_id ="conv_1")
    .order_by (Message .seq )
    .all ()
    )
    assert [m .direction for m in rows ]==[MessageDirection .OUTBOUND ,MessageDirection .INBOUND ]
    assert rows [1 ].sender ==MessageSender .CUSTOMER
    assert "tarikh"in rows [1 ].body


def test_message_meta_json_roundtrips (db_session ):
    _txn (db_session )
    db_session .add (
    Message (
    transaction_id ="conv_1",
    direction =MessageDirection .OUTBOUND ,
    sender =MessageSender .AGENT ,
    body ="Here is your link.",
    status =MessageStatus .SENT ,
    seq =0 ,
    meta_json ={"payment_link":"https://rzp.io/x","ai_drafted":True },
    )
    )
    db_session .commit ()
    m =db_session .query (Message ).filter_by (transaction_id ="conv_1").one ()
    assert m .meta_json ["payment_link"].startswith ("https://")
    assert m .meta_json ["ai_drafted"]is True


def test_call_session_with_turns (db_session ):
    _txn (db_session )
    session =CallSession (
    transaction_id ="conv_1",
    status =CallStatus .COMPLETED ,
    duration_sec =42 ,
    outcome ="promise_to_pay",
    )
    db_session .add (session )
    db_session .commit ()

    db_session .add_all (
    [
    CallTurn (call_session_id =session .id ,speaker =CallSpeaker .AGENT ,text ="Namaste ji",seq =0 ,at_offset_sec =0 ),
    CallTurn (call_session_id =session .id ,speaker =CallSpeaker .CUSTOMER ,text ="Haan boliye",seq =1 ,at_offset_sec =3 ),
    ]
    )
    db_session .commit ()

    turns =db_session .query (CallTurn ).filter_by (call_session_id =session .id ).order_by (CallTurn .seq ).all ()
    assert len (turns )==2
    assert turns [0 ].speaker ==CallSpeaker .AGENT
    assert turns [1 ].at_offset_sec ==3
