"""Transaction, audit, conversation, payment-link, and operator-action endpoints."""

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter ,Depends ,HTTPException ,Query ,status
from fastapi .responses import StreamingResponse
from pydantic import BaseModel ,Field
from sqlalchemy .orm import Session

from application .persistence import get_db
from application .constants import (
ActionType ,
InterventionAction ,
InterventionChannel ,
MessageDirection ,
MessageSender ,
MessageStatus ,
NodeName ,
Outcome ,
StoppingRule ,
TransactionLifecycleState ,
)
from application .entities import AuditTrail ,CallSession ,CallTurn ,Message ,TransactionState
from application .operations .audit_service import record_audit
from application .operations .conversation_service import build_call ,persona_for
from application .operations .message_drafter import draft_message
from application .operations .escalation_service import enqueue_escalation
from application .operations .live_recovery import run_recovery
from application .operations .compliance_rules import (
VOICE_ATTEMPT_CAP ,
is_within_quiet_hours ,
retry_cap_exceeded ,
voice_attempts_exhausted ,
)
from application .operations .voice_attempts import voice_attempt_count
from application .operations .policy_guard import ProposedAction
from application .operations import policy_repository
from application .helpers import next_quiet_hours_end ,now_ist ,resolve_clock_ist ,utcnow

_SSE_HEADERS ={"Cache-Control":"no-cache","Connection":"keep-alive","X-Accel-Buffering":"no"}


def _sse (event :str ,data :dict [str ,Any ])->str :
    return f"event: {event }\ndata: {json .dumps (data ,default =str )}\n\n"

router =APIRouter (tags =["transactions"])


def _mask (contact :str )->str :
    """Keep the last four digits; mask the rest (never expose PII in the clear)."""
    if not contact :
        return "****"
    tail =contact [-4 :]
    return "*"*max (4 ,len (contact )-4 )+tail


def _audits_by_txn (db :Session ,txn_ids :list [str ])->dict [str ,list [AuditTrail ]]:
    if not txn_ids :
        return {}
    rows =(
    db .query (AuditTrail )
    .filter (AuditTrail .transaction_id .in_ (txn_ids ))
    .order_by (AuditTrail .id )
    .all ()
    )
    grouped :dict [str ,list [AuditTrail ]]=defaultdict (list )
    for r in rows :
        grouped [r .transaction_id ].append (r )
    return grouped


def _derive (trail :list [AuditTrail ])->dict :
    """Pull the outcome-defining facts out of a transaction's audit trail."""
    playbook =channel =stopping_rule =None
    for a in trail :
        payload =a .payload if isinstance (a .payload ,dict )else {}
        if a .action_type ==ActionType .INTERVENTION_DISPATCH :
            playbook =payload .get ("playbook",playbook )
            channel =payload .get ("channel",channel )
        if payload .get ("stopping_rule"):
            stopping_rule =payload ["stopping_rule"]
    return {"playbook":playbook ,"channel":channel ,"stopping_rule":stopping_rule }


def _row (txn :TransactionState ,trail :list [AuditTrail ])->dict :
    meta =txn .metadata_json or {}
    recovered =txn .current_state .value =="RECOVERED"
    at_risk =bool (meta .get ("is_at_risk",True ))
    ttr =(
    round ((txn .updated_at -txn .created_at ).total_seconds (),2 )
    if recovered and at_risk
    else None
    )
    return {
    "serial":txn .id ,
    "transaction_id":txn .transaction_id ,
    "razorpay_payment_id":txn .razorpay_payment_id ,
    "failure_class":int (txn .failure_class ),
    "class_label":meta .get ("class_label"),
    "archetype":meta .get ("archetype"),
    "ai_tag":meta .get ("ai_tag"),
    "is_at_risk":at_risk ,
    "confidence":meta .get ("confidence"),
    "event_type":meta .get ("event_type"),
    "error_code":meta .get ("error_code"),
    "status":txn .current_state .value ,
    "amount_inr":round (txn .amount_minor /100 ,2 ),
    "currency":txn .currency ,
    "customer_name":meta .get ("customer_name"),
    "customer_contact_masked":_mask (txn .customer_contact ),
    "time_to_recovery_seconds":ttr ,
    "created_at":txn .created_at .isoformat (),
    "updated_at":txn .updated_at .isoformat (),
    **_derive (trail ),
    }


@router .get ("/transactions")
def list_transactions (
db :Session =Depends (get_db ),
failure_class :int |None =Query (None ,ge =1 ,le =4 ),
status_ :str |None =Query (None ,alias ="status"),
archetype :str |None =None ,
q :str |None =None ,
simulation_run_id :str |None =None ,
limit :int =Query (200 ,ge =1 ,le =500 ),
offset :int =Query (0 ,ge =0 ),
)->dict :
    """List cases, newest first.

    ``simulation_run_id`` scopes the list to one what-if run; without it the
    real book is listed and simulated rows are hidden, which mirrors how
    ``compute_metrics`` scopes the same rows. It filters in Python rather than
    SQL because the run id is a ``metadata_json`` key, not a column.
    """
    query =db .query (TransactionState )
    if failure_class is not None :
        query =query .filter (TransactionState .failure_class ==failure_class )
    if status_ :
        query =query .filter (TransactionState .current_state ==status_ )

    rows =query .order_by (TransactionState .created_at .desc ()).all ()




    if failure_class is not None :
        rows =[t for t in rows if (t .metadata_json or {}).get ("archetype")!="HEALTHY"]



    rows =[
    t
    for t in rows
    if (t .metadata_json or {}).get ("simulation_run_id")==simulation_run_id
    ]

    if archetype :
        rows =[t for t in rows if (t .metadata_json or {}).get ("archetype")==archetype ]
    if q :
        needle =q .lower ()
        rows =[
        t
        for t in rows
        if needle in t .transaction_id .lower ()
        or needle in str ((t .metadata_json or {}).get ("customer_name","")).lower ()
        ]

    total =len (rows )
    page =rows [offset :offset +limit ]
    trails =_audits_by_txn (db ,[t .transaction_id for t in page ])
    items =[_row (t ,trails .get (t .transaction_id ,[]))for t in page ]
    return {"total":total ,"items":items }


@router .get ("/transactions/{transaction_id}")
def get_transaction (transaction_id :str ,db :Session =Depends (get_db ))->dict :
    txn =(
    db .query (TransactionState )
    .filter_by (transaction_id =transaction_id )
    .one_or_none ()
    )
    if txn is None :
        raise HTTPException (status_code =status .HTTP_404_NOT_FOUND ,detail ="Transaction not found")

    trail =_audits_by_txn (db ,[transaction_id ]).get (transaction_id ,[])
    diagnosis ={}
    for a in trail :
        if a .node_name ==NodeName .DIAGNOSE and isinstance (a .payload ,dict ):
            diagnosis ={
            "root_cause":a .payload .get ("root_cause"),
            "recommended_playbook":a .payload .get ("recommended_playbook"),
            "confidence":a .payload .get ("confidence"),
            }
            break

    return {
    **_row (txn ,trail ),
    "diagnosis":diagnosis ,
    "audit_trail":[
    {
    "id":a .id ,
    "node_name":a .node_name .value ,
    "action_type":a .action_type .value ,
    "payload":a .payload ,
    "outcome":a .outcome .value ,
    "timestamp":a .timestamp .isoformat (),
    }
    for a in trail
    ],
    }


def _serialize_message (m :Message )->dict :
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


def _require_txn (db :Session ,transaction_id :str )->TransactionState :
    txn =db .query (TransactionState ).filter_by (transaction_id =transaction_id ).one_or_none ()
    if txn is None :
        raise HTTPException (status_code =status .HTTP_404_NOT_FOUND ,detail ="Transaction not found")
    return txn


@router .get ("/transactions/{transaction_id}/conversation")
def get_conversation (transaction_id :str ,db :Session =Depends (get_db ))->dict :
    _require_txn (db ,transaction_id )
    messages =(
    db .query (Message ).filter_by (transaction_id =transaction_id ).order_by (Message .seq ).all ()
    )
    session =(
    db .query (CallSession )
    .filter_by (transaction_id =transaction_id )
    .order_by (CallSession .id .desc ())
    .first ()
    )
    return {
    "messages":[_serialize_message (m )for m in messages ],
    "call":_serialize_call (db ,session )if session else None ,
    }


def _serialize_call (db :Session ,session :CallSession )->dict :
    turns =db .query (CallTurn ).filter_by (call_session_id =session .id ).order_by (CallTurn .seq ).all ()
    return {
    "id":session .id ,
    "status":session .status .value ,
    "duration_sec":session .duration_sec ,
    "outcome":session .outcome ,
    "provider":session .provider ,
    "started_at":session .started_at .isoformat (),
    "turns":[
    {"speaker":t .speaker .value ,"text":t .text ,"seq":t .seq ,"at_offset_sec":t .at_offset_sec }
    for t in turns
    ],
    }


@router .get ("/transactions/{transaction_id}/calls")
def list_calls (transaction_id :str ,db :Session =Depends (get_db ))->dict :
    """The call log for a transaction — every call, newest first, with transcript."""
    _require_txn (db ,transaction_id )
    sessions =(
    db .query (CallSession )
    .filter_by (transaction_id =transaction_id )
    .order_by (CallSession .id .desc ())
    .all ()
    )
    return {"calls":[_serialize_call (db ,s )for s in sessions ]}


def _call_clock ()->Callable [[],datetime ]:
    """FastAPI dependency for the IST wall clock the call-gating checks read.

    Mirrors ``OrchestratorDeps.clock`` in ``workflow/recovery_graph.py``: injected
    so a test can pin a moment via ``app.dependency_overrides``, never accepted
    as a request input. A previous version took a ``clock_ist`` query parameter,
    which let any caller supply their own clock and bypass the TRAI quiet-hours
    gate this endpoint exists to enforce.
    """
    return now_ist


@router .post ("/transactions/{transaction_id}/call/start",status_code =status .HTTP_201_CREATED )
def start_call (
transaction_id :str ,
db :Session =Depends (get_db ),
clock :Callable [[],datetime ]=Depends (_call_clock ),
)->dict :
    """Start a voice-recovery call for a transaction.

    Gated by compliance rules (quiet hours -> retry cap -> voice cap) and PolicySandbox.
    """
    txn =_require_txn (db ,transaction_id )
    clock =clock ()
    # An authored case may pin its own time of day (e.g. to demo TRAI quiet
    # hours deliberately) via CustomCase.clock_ist - set once at authoring time
    # by whoever built the case, not by this request. See live_session.py.
    authored =resolve_clock_ist ((txn .metadata_json or {}).get ("clock_ist"),reference =clock )
    if authored is not None :
        clock =authored

    # Gate 1: TRAI quiet hours
    if is_within_quiet_hours (clock ):
        resume_at =next_quiet_hours_end (clock )
        reason =f"Contact prohibited during TRAI quiet hours ({StoppingRule .TRAI_QUIET_HOURS .value }). Resume at {resume_at .strftime ('%H:%M')} IST."
        record_audit (
        db ,
        transaction_id =transaction_id ,
        node_name =NodeName .EXECUTE_INTERVENTION ,
        action_type =ActionType .RETRY_SCHEDULED ,
        payload ={
        "stopping_rule":StoppingRule .TRAI_QUIET_HOURS .value ,
        "reason":reason ,
        "scheduled_for":resume_at .isoformat (),
        "deferred_action":InterventionAction .VOICE_CALL .value ,
        },
        outcome =Outcome .SUCCESS ,
        )
        db .commit ()
        raise HTTPException (status_code =status .HTTP_409_CONFLICT ,detail =reason )

    # Gate 2: RBI retry cap
    if retry_cap_exceeded (int (txn .retry_count ),int (txn .max_retries or 3 )):
        reason =f"RBI retry cap reached ({txn .retry_count } of {txn .max_retries } retries) ({StoppingRule .RBI_MAX_RETRIES .value })."
        record_audit (
        db ,
        transaction_id =transaction_id ,
        node_name =NodeName .EXECUTE_INTERVENTION ,
        action_type =ActionType .STATE_TRANSITION ,
        payload ={
        "stopping_rule":StoppingRule .RBI_MAX_RETRIES .value ,
        "reason":reason ,
        },
        outcome =Outcome .FAILURE ,
        )
        db .commit ()
        raise HTTPException (status_code =status .HTTP_409_CONFLICT ,detail =reason )

    # Gate 3: Voice attempt cap
    attempts =voice_attempt_count (db ,transaction_id )
    if voice_attempts_exhausted (attempts ):
        reason =f"Voice attempt cap reached ({attempts } of {VOICE_ATTEMPT_CAP } calls in 72 hours) ({StoppingRule .VOICE_ATTEMPT_CAP .value })."
        record_audit (
        db ,
        transaction_id =transaction_id ,
        node_name =NodeName .EXECUTE_INTERVENTION ,
        action_type =ActionType .STATE_TRANSITION ,
        payload ={
        "stopping_rule":StoppingRule .VOICE_ATTEMPT_CAP .value ,
        "reason":reason ,
        },
        outcome =Outcome .FAILURE ,
        )
        db .commit ()
        raise HTTPException (status_code =status .HTTP_409_CONFLICT ,detail =reason )

    # Gate 4: PolicySandbox validate
    action =ProposedAction (
    action =InterventionAction .VOICE_CALL ,
    channel =InterventionChannel .VOICE ,
    amount_minor =txn .amount_minor ,
    )
    decision =policy_repository .sandbox_for (db ).validate (action )
    if not decision .approved :
        enqueue_escalation (db ,transaction_id =transaction_id ,reason =decision .reason )
        record_audit (
        db ,
        transaction_id =transaction_id ,
        node_name =NodeName .EXECUTE_INTERVENTION ,
        action_type =ActionType .ESCALATION ,
        payload ={
        "policy_block":decision .reason ,
        "action":action .action_value ,
        "channel":action .channel_value ,
        },
        outcome =Outcome .ESCALATED ,
        )
        db .commit ()
        raise HTTPException (status_code =status .HTTP_409_CONFLICT ,detail =decision .reason )

    # Approved: record intervention dispatch audit
    record_audit (
    db ,
    transaction_id =transaction_id ,
    node_name =NodeName .EXECUTE_INTERVENTION ,
    action_type =ActionType .INTERVENTION_DISPATCH ,
    payload ={
    "action":action .action_value ,
    "channel":action .channel_value ,
    },
    outcome =Outcome .SUCCESS ,
    )

    meta =txn .metadata_json or {}
    beat =build_call (
    failure_class =int (txn .failure_class ),
    name =meta .get ("customer_name")or "there",
    amount_inr =txn .amount_minor /100 ,
    persona =persona_for (txn .id or 0 ),
    )
    session =CallSession (
    transaction_id =transaction_id ,
    status =beat .status ,
    duration_sec =beat .duration_sec ,
    outcome =beat .outcome ,
    provider ="simulated",
    )
    db .add (session )
    db .flush ()
    for turn in beat .turns :
        db .add (CallTurn (
        call_session_id =session .id ,
        speaker =turn .speaker ,
        text =turn .text ,
        seq =turn .at_offset_sec ,
        at_offset_sec =turn .at_offset_sec ,
        ))
    db .commit ()
    db .refresh (session )
    return _serialize_call (db ,session )


class SendMessageBody (BaseModel ):
    body :str =Field (min_length =1 ,max_length =2000 )
    ai_drafted :bool =False


@router .post ("/transactions/{transaction_id}/messages",status_code =status .HTTP_201_CREATED )
def send_message (
transaction_id :str ,payload :SendMessageBody ,db :Session =Depends (get_db )
)->dict :
    _require_txn (db ,transaction_id )
    last =(
    db .query (Message )
    .filter_by (transaction_id =transaction_id )
    .order_by (Message .seq .desc ())
    .first ()
    )
    next_seq =(last .seq +1 )if last else 0
    msg =Message (
    transaction_id =transaction_id ,
    direction =MessageDirection .OUTBOUND ,
    sender =MessageSender .AGENT ,
    body =payload .body ,
    status =MessageStatus .SENT ,
    seq =next_seq ,
    meta_json ={"manual":True ,"ai_drafted":payload .ai_drafted },
    )
    db .add (msg )
    db .commit ()
    db .refresh (msg )
    return _serialize_message (msg )


@router .post ("/transactions/{transaction_id}/payment-link",status_code =status .HTTP_201_CREATED )
def create_payment_link_route (transaction_id :str ,db :Session =Depends (get_db ))->dict :
    """Mint a real (test-mode) Razorpay payment link and post it to the WhatsApp
    thread as a clickable message."""
    from application .operations .payment_link_service import create_payment_link

    try :
        result =create_payment_link (db ,transaction_id )
    except ValueError :
        raise HTTPException (status_code =status .HTTP_404_NOT_FOUND ,detail ="Transaction not found")
    return {
    "url":result ["url"],
    "razorpay_id":result ["razorpay_id"],
    "simulated":result ["simulated"],
    "detail":result ["detail"],
    "message":_serialize_message (result ["message"]),
    }


@router .get ("/transactions/{transaction_id}/payment-link/status")
def payment_link_status_route (transaction_id :str ,db :Session =Depends (get_db ))->dict :
    """Poll Razorpay for the link's payment status. When paid, the transaction is
    closed to RECOVERED (idempotent) and a system beat lands in the thread."""
    from application .operations .payment_link_service import payment_link_status

    try :
        return payment_link_status (db ,transaction_id )
    except ValueError :
        raise HTTPException (status_code =status .HTTP_404_NOT_FOUND ,detail ="Transaction not found")


class DraftBody (BaseModel ):
    prompt :str =Field (min_length =1 ,max_length =500 )


@router .post ("/transactions/{transaction_id}/messages/draft")
def draft (transaction_id :str ,payload :DraftBody ,db :Session =Depends (get_db ))->dict :
    try :
        text =draft_message (db ,transaction_id ,payload .prompt )
    except ValueError :
        raise HTTPException (status_code =status .HTTP_404_NOT_FOUND ,detail ="Transaction not found")
    return {"draft":text }


@router .post ("/transactions/simulate",status_code =status .HTTP_201_CREATED )
def simulate (failure_class :int |None =Query (None ,ge =1 ,le =4 ),db :Session =Depends (get_db ))->dict :
    """Inject a fresh, unworked failed transaction the operator can run a recovery on."""
    from application .operations .batch_seed import simulate_case

    txn =simulate_case (db ,failure_class )
    return _row (txn ,[])


@router .get ("/transactions/{transaction_id}/run")
def run_live (transaction_id :str ,locale :str ="en",db :Session =Depends (get_db )):
    """Stream a live recovery run for this case (SSE) — diagnose → message → reply →
    (call) → reconcile — so the viewer watches the agent recover it. ``locale``
    (en|hi) drives the language used for outreach."""
    _require_txn (db ,transaction_id )
    loc ="hi"if locale =="hi"else "en"

    def event_stream ():
        for event ,data in run_recovery (db ,transaction_id ,locale =loc ):
            yield _sse (event ,data )

    return StreamingResponse (event_stream (),media_type ="text/event-stream",headers =_SSE_HEADERS )


class RecoverBatchBody (BaseModel ):
    transaction_ids :list [str ]=Field (min_length =1 ,max_length =50 )
    locale :str ="en"


@router .post ("/transactions/recover-batch")
def recover_batch (payload :RecoverBatchBody ,db :Session =Depends (get_db ))->dict :
    """Recover several cases at once (the 'recover all' choice). Each runs through
    the real recovery loop offline — template drafting, no live model — so a whole
    queue clears in one call and the recovery agent can report the tally."""
    loc ="hi"if payload .locale =="hi"else "en"
    drafter =lambda d ,t ,p :draft_message (d ,t ,p ,generate =None ,locale =loc )
    results =[]
    for tid in payload .transaction_ids :
        if db .query (TransactionState ).filter_by (transaction_id =tid ).one_or_none ()is None :
            continue
        final =None
        for event ,data in run_recovery (db ,tid ,pause =lambda _s :None ,drafter =drafter ):
            if event =="complete":
                final =data .get ("final_state")
        results .append ({"transaction_id":tid ,"final_state":final })
    recovered =sum (1 for r in results if r ["final_state"]=="RECOVERED")
    return {"total":len (results ),"recovered":recovered ,"results":results }


class StatusBody (BaseModel ):
    status :TransactionLifecycleState
    note :str |None =Field (default =None ,max_length =1000 )


@router .post ("/transactions/{transaction_id}/status")
def set_status (transaction_id :str ,payload :StatusBody ,db :Session =Depends (get_db ))->dict :
    """An operator sets a transaction's outcome by hand. Audited, and (because the
    metrics are derived) reflected in GRRR/funnel/counts immediately."""
    txn =_require_txn (db ,transaction_id )
    old =txn .current_state .value
    new =payload .status
    txn .current_state =new
    txn .updated_at =utcnow ()
    db .commit ()


    if new ==TransactionLifecycleState .ESCALATED :
        enqueue_escalation (
        db ,transaction_id =transaction_id ,reason =payload .note or "Escalated by operator"
        )

    record_audit (
    db ,
    transaction_id =transaction_id ,
    node_name =NodeName .OPERATOR ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"event":"OPERATOR_STATUS_CHANGE","from":old ,"to":new .value ,
    **({"note":payload .note }if payload .note else {})},
    outcome =Outcome .ESCALATED if new ==TransactionLifecycleState .ESCALATED else Outcome .SUCCESS ,
    )
    trail =_audits_by_txn (db ,[transaction_id ]).get (transaction_id ,[])
    return _row (txn ,trail )


class NoteBody (BaseModel ):
    note :str =Field (min_length =1 ,max_length =1000 )


@router .post ("/transactions/{transaction_id}/note",status_code =status .HTTP_201_CREATED )
def add_note (transaction_id :str ,payload :NoteBody ,db :Session =Depends (get_db ))->dict :
    _require_txn (db ,transaction_id )
    entry =record_audit (
    db ,
    transaction_id =transaction_id ,
    node_name =NodeName .OPERATOR ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"event":"OPERATOR_NOTE","note":payload .note },
    outcome =Outcome .SUCCESS ,
    )
    return {"id":entry .id ,"note":payload .note ,"timestamp":entry .timestamp .isoformat ()}


@router .get ("/audit")
def list_audit (
db :Session =Depends (get_db ),
transaction_id :str |None =None ,
limit :int =Query (200 ,ge =1 ,le =1000 ),
offset :int =Query (0 ,ge =0 ),
)->dict :
    query =db .query (AuditTrail )
    if transaction_id :
        query =query .filter (AuditTrail .transaction_id ==transaction_id )
    total =query .count ()
    rows =query .order_by (AuditTrail .id .desc ()).offset (offset ).limit (limit ).all ()
    return {
    "total":total ,
    "items":[
    {
    "id":a .id ,
    "transaction_id":a .transaction_id ,
    "node_name":a .node_name .value ,
    "action_type":a .action_type .value ,
    "payload":a .payload ,
    "outcome":a .outcome .value ,
    "timestamp":a .timestamp .isoformat (),
    }
    for a in rows
    ],
    }
