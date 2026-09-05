"""Payment-link creation and status reconciliation for Razorpay transactions."""

from __future__ import annotations

from sqlalchemy .orm import Session

from application .integrations .razorpay_mcp import default_client ,mcp_dispatch_enabled
from application .settings import settings
from application .constants import (
ActionType ,
MessageDirection ,
MessageSender ,
MessageStatus ,
NodeName ,
Outcome ,
TransactionLifecycleState ,
)
from application .entities import Message ,TransactionState
from application .operations .audit_service import record_audit


def _build_client ():
    """Construct a real Razorpay client from the configured (test) keys.

    Isolated so tests can monkeypatch it and never touch the network.
    """
    import razorpay

    return razorpay .Client (auth =(settings .razorpay_key_id ,settings .razorpay_key_secret ))


def _create_link (txn :TransactionState ,client )->tuple [str |None ,str |None ]:
    link =client .payment_link .create (
    {
    "amount":int (txn .amount_minor ),
    "currency":txn .currency or "INR",
    "description":f"Payment recovery for {txn .transaction_id }",
    "customer":{"contact":txn .customer_contact },
    "notify":{"sms":False ,"email":False },
    "reminder_enable":False ,


    "notes":{"transaction_id":txn .transaction_id ,"merchant_id":txn .merchant_id },
    }
    )
    return link .get ("short_url"),link .get ("id")


def _remember_link_id (txn :TransactionState ,ref :str |None )->None :
    meta =dict (txn .metadata_json or {})
    meta ["payment_link_id"]=ref
    txn .metadata_json =meta


def _mcp_link (txn :TransactionState )->tuple [str |None ,str |None ]|None :
    if not mcp_dispatch_enabled ():
        return None
    try :
        result =default_client ().create_payment_link (
        amount_minor =int (txn .amount_minor ),currency =txn .currency or "INR",
        contact =txn .customer_contact ,description =f"Payment recovery for {txn .transaction_id }",
        transaction_id =txn .transaction_id ,merchant_id =txn .merchant_id ,failure_class =int (txn .failure_class ),
        )
    except Exception :
        return None
    if not result or not result .get ("id"):
        return None
    url =result .get ("short_url")or result .get ("image_url")or result .get ("qr_code")or result .get ("url")
    if not url:
        return None
    return str (url ),str (result ["id"])


def create_payment_link (db :Session ,transaction_id :str ,*,client =None )->dict :
    txn =db .query (TransactionState ).filter_by (transaction_id =transaction_id ).first ()
    if txn is None :
        raise ValueError ("transaction not found")

    url :str |None =None
    ref :str |None =None
    detail ="simulated"
    have_keys =bool (settings .razorpay_key_id and settings .razorpay_key_secret )
    if client is None :
        try :
            mcp_result =_mcp_link (txn )
        except Exception :
            mcp_result =None
        if mcp_result is not None :
            url ,ref =mcp_result
            detail ="mcp"
    if client is None and not url and have_keys :
        try :
            client =_build_client ()
        except Exception :
            client =None
    if client is not None :
        try :
            url ,ref =_create_link (txn ,client )
            detail ="sdk"
        except Exception :
            url ,ref =None ,None
            detail ="simulated"

    simulated =not url
    if simulated :
        detail ="simulated"
        url =f"https://rzp.io/i/{transaction_id [-6 :]}"
        ref =f"sim_{transaction_id [-6 :]}"

    _remember_link_id (txn ,None if simulated else ref )

    last =(
    db .query (Message )
    .filter_by (transaction_id =transaction_id )
    .order_by (Message .seq .desc ())
    .first ()
    )
    next_seq =(last .seq +1 )if last else 0
    rupees =f"₹{txn .amount_minor /100 :,.0f}"
    body =(
    f"Yeh raha aapka secure payment link — {rupees }, sirf 1 tap, "
    f"koi OTP nahi chahiye: {url }"
    )
    msg =Message (
    transaction_id =transaction_id ,
    direction =MessageDirection .OUTBOUND ,
    sender =MessageSender .AGENT ,
    body =body ,
    status =MessageStatus .SENT ,
    seq =next_seq ,
    meta_json ={"payment_link":url ,"razorpay_id":ref ,"simulated":simulated ,"manual":True ,"detail":detail },
    )
    db .add (msg )
    db .commit ()
    db .refresh (msg )
    return {"url":url ,"razorpay_id":ref ,"simulated":simulated ,"detail":detail ,"message":msg }


def _add_system_beat (db :Session ,transaction_id :str ,text :str )->None :
    last =(
    db .query (Message )
    .filter_by (transaction_id =transaction_id )
    .order_by (Message .seq .desc ())
    .first ()
    )
    next_seq =(last .seq +1 )if last else 0
    db .add (
    Message (
    transaction_id =transaction_id ,
    direction =MessageDirection .INBOUND ,
    sender =MessageSender .SYSTEM ,
    body =text ,
    status =MessageStatus .SENT ,
    seq =next_seq ,
    meta_json ={"payment_captured":True },
    )
    )


def payment_link_status (db :Session ,transaction_id :str ,*,client =None )->dict :
    """Poll Razorpay for the link's status; when it's paid, close the loop by
    marking the transaction RECOVERED (idempotent) and dropping a system beat
    into the thread. Reliable locally, where inbound webhooks can't reach us."""
    txn =db .query (TransactionState ).filter_by (transaction_id =transaction_id ).first ()
    if txn is None :
        raise ValueError ("transaction not found")

    already =txn .current_state ==TransactionLifecycleState .RECOVERED
    link_id =(txn .metadata_json or {}).get ("payment_link_id")
    if not link_id :
        return {"paid":already ,"status":"recovered"if already else "no_link",
        "current_state":txn .current_state .value }

    status_str ="unknown"
    mcp_handled =False
    if client is None and mcp_dispatch_enabled ():
        try :
            mcp_status =default_client ().fetch_payment_link (link_id )
        except Exception :
            mcp_status =None
        if mcp_status is not None :
            status_str =str (mcp_status .get ("status","unknown"))
            mcp_handled =True

    if client is None and not mcp_handled and settings .razorpay_key_id and settings .razorpay_key_secret :
        try :
            client =_build_client ()
        except Exception :
            client =None
    if client is not None :
        try :
            status_str =(client .payment_link .fetch (link_id )or {}).get ("status","unknown")
        except Exception :
            status_str ="unknown"

    paid =status_str =="paid"
    if paid and not already :
        txn .current_state =TransactionLifecycleState .RECOVERED
        record_audit (
        db ,
        transaction_id =transaction_id ,
        node_name =NodeName .RECONCILE ,
        action_type =ActionType .STATE_TRANSITION ,
        payload ={"event":"PAYMENT_LINK_PAID","razorpay_id":link_id },
        outcome =Outcome .SUCCESS ,
        )
        _add_system_beat (db ,transaction_id ,"✅ Payment received — recovery complete.")
        db .commit ()
        db .refresh (txn )

    return {"paid":paid or already ,"status":status_str ,
    "current_state":txn .current_state .value }
