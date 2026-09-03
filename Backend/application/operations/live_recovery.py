"""Step-by-step recovery runner used by the live demonstration flow."""

from __future__ import annotations

import time
from typing import Callable ,Iterator

from sqlalchemy .orm import Session

from application .constants import (
ActionType ,
CallStatus ,
FailureClass ,
InterventionChannel ,
MessageDirection ,
MessageSender ,
MessageStatus ,
NodeName ,
Outcome ,
StoppingRule ,
TransactionLifecycleState ,
)
from application .entities import CallSession ,CallTurn ,Message ,TransactionState
from application .operations .audit_service import record_audit
from application .operations .batch_seed import class_profile
from application .operations .conversation_service import build_call ,persona_for
from application .operations .diagnosis_service import _DEFAULT_PLAYBOOK
from application .operations .message_drafter import draft_message
from application .operations .escalation_service import enqueue_escalation
from application .operations .language_parser import extract_p2p_date
from application .operations .reconciliation_service import compute_metrics
from application .operations .compliance_rules import screen_user_message

Event =tuple [str ,dict ]




def _diag (fc :int )->tuple [str ,str ,float ]:
    """Root cause, playbook and confidence for a live run.

    Read from the seeded batch's class profile so a case worked live and the
    cases already on the dashboard never tell two different stories.
    """
    profile =class_profile (fc )
    return (
    profile ["root_cause"],
    _DEFAULT_PLAYBOOK [FailureClass (fc )].value ,
    profile ["confidence"],
    )

_LABEL ={1 :"Failed Payment",2 :"Abandoned Checkout",3 :"Failed Subscription",4 :"Overdue Invoice"}

_FIRST_MSG_PROMPT ={
1 :"Write the first WhatsApp message: a brief technical glitch on our side caused this payment to fail — reassure it's not their fault and offer a secure 1-tap link, no OTP needed.",
2 :"Write the first WhatsApp message: their checkout dropped at the OTP/3DS step; offer a 1-tap UPI Autopay link to finish instantly.",
3 :"Write the first WhatsApp message: their subscription auto-debit failed due to a low balance before salary; reassure you'll retry around their salary date.",
4 :"Write the first WhatsApp message: their B2B invoice is overdue; politely ask when you can expect the payment.",
}


def _customer_reply (run_outcome :str ,persona :dict )->str :
    if run_outcome =="optout":
        return "please stop messaging me, band karo"
    if run_outcome =="dispute":
        return "yeh galat invoice hai, humne itna order nahi kiya tha"
    if run_outcome =="p2p":
        return persona ["p2p"]
    return persona ["ok"]


def _ser_msg (m :Message )->dict :
    return {
    "id":m .id ,
    "channel":m .channel .value ,
    "direction":m .direction .value ,
    "sender":m .sender .value ,
    "body":m .body ,
    "status":m .status .value ,
    "seq":m .seq ,
    "meta":m .meta_json ,
    "created_at":m .created_at .isoformat (),
    }


def run_recovery (
db :Session ,
transaction_id :str ,
*,
pause :Callable [[float ],None ]=time .sleep ,
drafter :Callable [[Session ,str ,str ],str ]|None =None ,
locale :str ="en",
)->Iterator [Event ]:


    if drafter is None :
        drafter =lambda d ,t ,p :draft_message (d ,t ,p ,locale =locale )
    txn =db .query (TransactionState ).filter_by (transaction_id =transaction_id ).one_or_none ()
    if txn is None :
        raise ValueError (f"Unknown transaction: {transaction_id !r }")

    fc =int (txn .failure_class )
    meta =dict (txn .metadata_json or {})
    persona =persona_for (txn .id or 0 )
    run_outcome =meta .get ("run_outcome","recovered")
    name =str (meta .get ("customer_name")or "there")
    first =name .split ()[0 ]
    rupees =f"₹{int (txn .amount_minor /100 ):,}"

    last =(
    db .query (Message )
    .filter_by (transaction_id =transaction_id )
    .order_by (Message .seq .desc ())
    .first ()
    )
    seq =(last .seq +1 )if last else 0

    def add_msg (direction ,sender ,body ,mj =None )->Message :
        nonlocal seq
        m =Message (
        transaction_id =transaction_id ,channel =InterventionChannel .WHATSAPP ,
        direction =direction ,sender =sender ,body =body ,status =MessageStatus .READ ,
        seq =seq ,meta_json =mj ,
        )
        db .add (m )
        db .commit ()
        db .refresh (m )
        seq +=1
        return m

    yield "start",{
    "transaction_id":transaction_id ,
    "failure_class":fc ,
    "amount_inr":round (txn .amount_minor /100 ,2 ),
    "customer_name":name ,
    }
    pause (0.5 )


    txn .current_state =TransactionLifecycleState .DIAGNOSING
    db .commit ()
    record_audit (db ,transaction_id =transaction_id ,node_name =NodeName .INGEST ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"event":"FLAGGED","class":_LABEL [fc ]},outcome =Outcome .SUCCESS )
    yield "step",{"phase":"flagged","label":f"Flagged: {_LABEL [fc ]} · {rupees }"}
    pause (0.8 )


    root ,playbook ,conf =_diag (fc )
    record_audit (db ,transaction_id =transaction_id ,node_name =NodeName .DIAGNOSE ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"root_cause":root ,"recommended_playbook":playbook ,"confidence":conf },
    outcome =Outcome .SUCCESS )
    yield "diagnosis",{"root_cause":root ,"playbook":playbook ,"confidence":conf }
    pause (1.0 )


    yield "typing",{"who":"agent"}
    pause (1.1 )
    body =drafter (db ,transaction_id ,_FIRST_MSG_PROMPT [fc ])
    m =add_msg (MessageDirection .OUTBOUND ,MessageSender .AGENT ,body ,{"ai_drafted":True })
    txn .current_state =TransactionLifecycleState .INTERVENING
    db .commit ()
    record_audit (db ,transaction_id =transaction_id ,node_name =NodeName .EXECUTE_INTERVENTION ,
    action_type =ActionType .INTERVENTION_DISPATCH ,
    payload ={"action":"SEND_WHATSAPP","channel":"WHATSAPP","playbook":playbook },
    outcome =Outcome .SUCCESS )
    yield "message",_ser_msg (m )
    pause (1.2 )


    yield "typing",{"who":"customer"}
    pause (1.4 )
    reply =_customer_reply (run_outcome ,persona )
    yield "message",_ser_msg (add_msg (MessageDirection .INBOUND ,MessageSender .CUSTOMER ,reply ))
    pause (0.8 )


    terminal :str |None =None
    verdict =screen_user_message (reply )
    if verdict .disposition =="TERMINATE":
        terminal ="CANCELLED"
        _stop (db ,transaction_id ,verdict .rule ,verdict .reason )
        add_msg (MessageDirection .OUTBOUND ,MessageSender .SYSTEM ,
        f"Opt-out honoured — all contact stopped ({verdict .rule .value }).")
        yield "step",{"phase":"stopped","rule":verdict .rule .value }
    elif verdict .disposition =="ESCALATE":
        terminal ="ESCALATED"
        enqueue_escalation (db ,transaction_id =transaction_id ,reason =verdict .reason ,rule =verdict .rule )
        _stop (db ,transaction_id ,verdict .rule ,verdict .reason )
        add_msg (MessageDirection .OUTBOUND ,MessageSender .SYSTEM ,
        f"Dispute raised — automation frozen, escalated to a human ({verdict .rule .value }).")
        yield "step",{"phase":"escalated","rule":verdict .rule .value }
    elif fc ==4 and run_outcome =="p2p":
        p2p =extract_p2p_date (reply )
        if p2p :
            meta ["p2p_date"]=p2p
            record_audit (db ,transaction_id =transaction_id ,node_name =NodeName .WAIT ,
            action_type =ActionType .RETRY_SCHEDULED ,
            payload ={"reason":"WAITING_FOR_P2P","scheduled_for":p2p ,"extracted_from":reply },
            outcome =Outcome .SUCCESS )
            yield "message",_ser_msg (add_msg (
            MessageDirection .OUTBOUND ,MessageSender .AGENT ,
            f"Noted — we'll expect payment by {p2p }. I'll hold reminders until then. Thank you!",
            {"p2p_date":p2p }))
            yield "step",{"phase":"waiting","p2p_date":p2p }
    pause (1.0 )


    if fc ==3 and terminal is None :
        yield "step",{"phase":"calling"}
        pause (0.8 )
        cb =build_call (failure_class =fc ,name =name ,amount_inr =txn .amount_minor /100 ,persona =persona )
        session =CallSession (transaction_id =transaction_id ,status =CallStatus .COMPLETED ,
        duration_sec =cb .duration_sec ,outcome =cb .outcome ,provider ="simulated")
        db .add (session )
        db .flush ()
        for t in cb .turns :
            db .add (CallTurn (call_session_id =session .id ,speaker =t .speaker ,text =t .text ,
            seq =t .at_offset_sec ,at_offset_sec =t .at_offset_sec ))
        db .commit ()
        yield "call",{"id":session .id ,"duration_sec":cb .duration_sec ,"turns":len (cb .turns )}
        pause (1.0 )


    if terminal is None :
        txn .current_state =TransactionLifecycleState .RECOVERED
        record_audit (db ,transaction_id =transaction_id ,node_name =NodeName .RECONCILE ,
        action_type =ActionType .STATE_TRANSITION ,
        payload ={"outcome_event":"payment.captured","disposition":"RECOVERED"},
        outcome =Outcome .SUCCESS )
        add_msg (MessageDirection .OUTBOUND ,MessageSender .SYSTEM ,f"Payment of {rupees } received ✓")
        final ="RECOVERED"
    else :
        txn .current_state =TransactionLifecycleState (terminal )
        final =terminal

    meta ["unworked"]=False
    txn .metadata_json =meta
    db .commit ()

    yield "status",{"final_state":final }
    yield "complete",{"final_state":final ,"metrics":compute_metrics (db )}


def _stop (db :Session ,transaction_id :str ,rule :StoppingRule ,reason :str )->None :
    record_audit (db ,transaction_id =transaction_id ,node_name =NodeName .RECONCILE ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"stopping_rule":rule .value ,"reason":reason },outcome =Outcome .SUCCESS )
