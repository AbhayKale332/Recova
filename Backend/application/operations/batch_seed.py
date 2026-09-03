"""Deterministic batch generator that exercises real recovery logic for demos and tests."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import date ,datetime ,timedelta
from typing import Literal

from application .constants import (
ActionType ,
FailureClass ,
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
from application .operations .escalation_service import enqueue_escalation
from application .operations .compliance_rules import (
is_within_quiet_hours ,
screen_user_message ,
voice_attempts_exhausted ,
)
from application .entities import (
AuditTrail ,
CallSession ,
CallTurn ,
EscalationQueue ,
Message ,
ProcessedEvent ,
TransactionState ,
)
from application .workflow .recovery_graph import OrchestratorDeps ,build_recovery_graph
from application .operations .audit_service import record_audit
from application .operations .conversation_service import build_thread ,persona_for
from application .operations .diagnosis_service import Diagnosis ,_DEFAULT_PLAYBOOK
from application .operations .language_parser import extract_p2p_date
from application .operations .policy_guard import PolicySandbox
from application .helpers import next_salary_window ,utcnow

# Seed profiles are deterministic so demos and tests can reproduce the same recovery outcomes.
CaseOutcome =Literal [
"recovered",
"inflight",
"escalated_dispute",
"cancelled_optout",
"cancelled_rbi",
"late_settlement",
"cross_device",
]

_RECOVERED_LIKE ={"recovered","late_settlement","cross_device"}



_CLASS_PROFILE :dict [FailureClass ,dict ]={
FailureClass .REALTIME_DEGRADATION :{
"label":"Issuer / Network Timeout",
"event_type":"payment.failed",
"error_code":"GATEWAY_TIMEOUT",
"root_cause":"ISSUER_LATENCY_SPIKE",
"confidence":0.93 ,
"base_amount":329900 ,
},
FailureClass .CHECKOUT_ABANDONMENT :{
"label":"Checkout Authentication Drop",
"event_type":"payment.failed",
"error_code":"CUSTOMER_AUTH_TIMEOUT",
"root_cause":"OTP_SESSION_EXPIRED",
"confidence":0.87 ,
"base_amount":119900 ,
},
FailureClass .SUBSCRIPTION_MANDATE :{
"label":"Recurring Mandate Failure",
"event_type":"payment.failed",
"error_code":"MANDATE_PAUSED",
"root_cause":"SALARY_CYCLE_MISMATCH",
"confidence":0.90 ,
"base_amount":129900 ,
},
FailureClass .B2B_RECEIVABLES :{
"label":"B2B Invoice Aging",
"event_type":"invoice.overdue",
"error_code":None ,
"root_cause":"BUYER_APPROVAL_DELAY",
"confidence":0.86 ,
"base_amount":12600000 ,
},
}



def class_profile (failure_class :FailureClass |int )->dict :
    """The demo's per-class vocabulary: label, telemetry, root cause, confidence.

    Exposed so the live recovery runner reads the same profile the batch was
    seeded from instead of keeping a second copy that can drift out of sync.
    """
    return _CLASS_PROFILE [FailureClass (failure_class )]


_CUSTOMERS =[
"Meera Iyer","Rohan Das","Kavya Bhat","Aditya Kulkarni","Nikhil Fernandes",
"Tara Bedi","Farhan Sheikh","Lakshmi Prasad","Soham Chatterjee","Aisha Rahman",
"Neil D'Souza","Pooja Krishnan","Dev Malhotra","Sneha Patil","Yusuf Ansari",
"Ira Banerjee","Manav Sethi","Ritu Menon","Arman Qureshi","Nandini Rao",
"Karan Oberoi","Shreya Nair","Vikram Hegde","Anushka Pillai","Omar Siddiqui",
"Maya Thomas","Harsh Vardhan","Simran Kaur","Aditi Bose","Rakesh Yadav",
]
_CONTACTS =[f"+9198{n :08d}"for n in range (len (_CUSTOMERS ))]


@dataclass
class ScenarioSpec :
    failure_class :FailureClass
    outcome :CaseOutcome
    count :int


@dataclass
class ArchetypeSpec :
    """Context rows that are shown for volume but are not recovery cases."""

    archetype :Literal ["HEALTHY","NON_RECOVERABLE"]
    failure_class :FailureClass
    count :int


@dataclass
class UnworkedSpec :
    """A freshly-flagged case the recovery agent has NOT worked yet (PENDING, empty thread).

    The operator runs the recovery agent on it live and watches the recovery happen. `run_outcome`
    scripts only the customer's side of that run; the decisions stay real code.
    """

    failure_class :FailureClass
    run_outcome :str
    count :int




DEFAULT_BATCH :list =[
ScenarioSpec (FailureClass .REALTIME_DEGRADATION ,"recovered",3 ),
ScenarioSpec (FailureClass .REALTIME_DEGRADATION ,"late_settlement",2 ),
ScenarioSpec (FailureClass .REALTIME_DEGRADATION ,"inflight",2 ),
ScenarioSpec (FailureClass .REALTIME_DEGRADATION ,"escalated_dispute",1 ),
ScenarioSpec (FailureClass .CHECKOUT_ABANDONMENT ,"recovered",4 ),
ScenarioSpec (FailureClass .CHECKOUT_ABANDONMENT ,"cross_device",2 ),
ScenarioSpec (FailureClass .CHECKOUT_ABANDONMENT ,"inflight",2 ),
ScenarioSpec (FailureClass .CHECKOUT_ABANDONMENT ,"cancelled_optout",1 ),
ScenarioSpec (FailureClass .SUBSCRIPTION_MANDATE ,"recovered",5 ),
ScenarioSpec (FailureClass .SUBSCRIPTION_MANDATE ,"inflight",1 ),
ScenarioSpec (FailureClass .SUBSCRIPTION_MANDATE ,"cancelled_rbi",2 ),
ScenarioSpec (FailureClass .B2B_RECEIVABLES ,"recovered",4 ),
ScenarioSpec (FailureClass .B2B_RECEIVABLES ,"inflight",2 ),
ScenarioSpec (FailureClass .B2B_RECEIVABLES ,"escalated_dispute",1 ),
ArchetypeSpec ("HEALTHY",FailureClass .CHECKOUT_ABANDONMENT ,12 ),
ArchetypeSpec ("NON_RECOVERABLE",FailureClass .REALTIME_DEGRADATION ,4 ),

UnworkedSpec (FailureClass .REALTIME_DEGRADATION ,"recovered",1 ),
UnworkedSpec (FailureClass .CHECKOUT_ABANDONMENT ,"recovered",1 ),
UnworkedSpec (FailureClass .CHECKOUT_ABANDONMENT ,"optout",1 ),
UnworkedSpec (FailureClass .SUBSCRIPTION_MANDATE ,"recovered",1 ),
UnworkedSpec (FailureClass .B2B_RECEIVABLES ,"p2p",1 ),
UnworkedSpec (FailureClass .B2B_RECEIVABLES ,"dispute",1 ),
]


@dataclass
class BatchResult :
    seeded :int
    by_state :dict [str ,int ]


class _OfflineDiagnosis :
    """Deterministic, network-free diagnosis for the seed.

    Mirrors the real engine's contract (``.diagnose`` → ``Diagnosis``) but returns
    a fixed, believable per-class root cause + confidence, and always the class's
    default playbook — the safe path the live engine falls back to anyway.
    """

    def diagnose (self ,*,failure_class ,telemetry =None ,user_message =None )->Diagnosis :
        profile =_CLASS_PROFILE [failure_class ]
        return Diagnosis (
        root_cause =profile ["root_cause"],
        recommended_playbook =_DEFAULT_PLAYBOOK [failure_class ],
        confidence =profile ["confidence"],
        )


def _offline_deps (db )->OrchestratorDeps :
    from application .integrations .routing_dispatcher import build_dispatcher

    return OrchestratorDeps (
    db =db ,
    diagnosis =_OfflineDiagnosis (),
    sandbox =PolicySandbox .from_default_policy (),
    dispatch =build_dispatcher (db ,live_mode =False ),
    )


def _amount_for (base :int ,index :int )->int :
    """Deterministic jitter so amounts vary without randomness."""
    return int (base *(0.85 +0.03 *(index %11 )))


def _clear (db )->None :

    db .query (CallTurn ).delete ()
    db .query (CallSession ).delete ()
    db .query (Message ).delete ()
    db .query (AuditTrail ).delete ()
    db .query (EscalationQueue ).delete ()
    db .query (ProcessedEvent ).delete ()
    db .query (TransactionState ).delete ()
    db .commit ()


def seed_batch (db ,*,spec :list |None =None ,now :datetime |None =None )->BatchResult :
    """Populate the DB with a mixed batch. Idempotent: clears first."""
    spec =spec if spec is not None else DEFAULT_BATCH
    now =now or utcnow ()
    _clear (db )

    graph =build_recovery_graph (_offline_deps (db ))
    index =0

    for item in spec :
        for _ in range (item .count ):
            if isinstance (item ,ArchetypeSpec ):
                _seed_context_row (db ,item ,index )
            elif isinstance (item ,UnworkedSpec ):
                _seed_unworked (db ,item .failure_class ,item .run_outcome ,index )
            else :
                _seed_case (db ,graph ,item ,index )
            index +=1

    # Keep the demo dense enough for the dashboard while preserving the same
    # state mix and recovery workflow for every class.
    _seed_bulk (db ,per_class =30 )
    _seed_compliance_stops (db ,now )
    _spread_timestamps (db ,now )
    _seed_trackers (db ,now )

    rows =db .query (TransactionState ).all ()
    by_state :dict [str ,int ]={}
    for t in rows :
        by_state [t .current_state .value ]=by_state .get (t .current_state .value ,0 )+1
    return BatchResult (seeded =len (rows ),by_state =by_state )




_BULK_MIX ={
TransactionLifecycleState .RECOVERED :12 ,
TransactionLifecycleState .PENDING :3 ,
TransactionLifecycleState .INTERVENING :2 ,
TransactionLifecycleState .ESCALATED :2 ,
TransactionLifecycleState .FAILED :1 ,
}
_BULK_STATES =[s for s ,n in _BULK_MIX .items ()for _ in range (n )]


def _bulk_state (k :int ,per_class :int )->TransactionLifecycleState :
    """Walk the fixed mix across ``per_class`` slots.

    Indexing by ``k % len(_BULK_STATES)`` would only hold the ratio when the batch
    size is a multiple of the mix, so any other size silently over-weights the
    states at the front of it (and inflates the dashboard's recovery rate).
    """
    return _BULK_STATES [k *len (_BULK_STATES )//per_class ]


_BULK_ACTION ={
FailureClass .REALTIME_DEGRADATION :(InterventionAction .GENERATE_PAYMENT_LINK ,InterventionChannel .PAYMENT_LINK ),
FailureClass .CHECKOUT_ABANDONMENT :(InterventionAction .SEND_WHATSAPP ,InterventionChannel .WHATSAPP ),
FailureClass .SUBSCRIPTION_MANDATE :(InterventionAction .RETRY_CHARGE ,InterventionChannel .PAYMENT_LINK ),
FailureClass .B2B_RECEIVABLES :(InterventionAction .SEND_WHATSAPP ,InterventionChannel .WHATSAPP ),
}
_BULK_OUTCOMES =["recovered","optout","dispute","p2p"]


def _bulk_audit (db ,txn :TransactionState ,fc :FailureClass ,state :TransactionLifecycleState )->None :
    """A short, state-consistent trail so a bulk case reads like a real one."""
    profile =_CLASS_PROFILE [fc ]
    playbook =_DEFAULT_PLAYBOOK [fc ].value
    record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .INGEST ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"event":"FLAGGED","class":profile ["label"]},outcome =Outcome .SUCCESS )
    record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .DIAGNOSE ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"root_cause":profile ["root_cause"],"recommended_playbook":playbook ,
    "confidence":profile ["confidence"]},outcome =Outcome .SUCCESS )
    if state in (TransactionLifecycleState .INTERVENING ,TransactionLifecycleState .RECOVERED ,
    TransactionLifecycleState .ESCALATED ):
        action ,channel =_BULK_ACTION [fc ]
        record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .EXECUTE_INTERVENTION ,
        action_type =ActionType .INTERVENTION_DISPATCH ,
        payload ={"action":action .value ,"channel":channel .value ,"playbook":playbook },
        outcome =Outcome .SUCCESS )
    if state ==TransactionLifecycleState .RECOVERED :
        record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .RECONCILE ,
        action_type =ActionType .STATE_TRANSITION ,
        payload ={"disposition":"RECOVERED"},outcome =Outcome .SUCCESS )
    if state ==TransactionLifecycleState .ESCALATED :
        enqueue_escalation (db ,transaction_id =txn .transaction_id ,
        reason ="Routed to a human for judgement.",rule =None )


def _seed_bulk (db ,*,per_class :int =20 )->None :
    index =10_000
    for fc in FailureClass :
        for k in range (per_class ):
            state =_bulk_state (k ,per_class )
            txn =_new_txn (
            fc ,index ,archetype =f"CLASS_{int (fc )}",is_at_risk =True ,state =state ,
            retry_count =(1 +k %2 )if state ==TransactionLifecycleState .INTERVENING else 0 ,
            )
            txn .metadata_json ["ai_tag"]="RECOVERY_CASE"
            if state ==TransactionLifecycleState .PENDING :
                txn .metadata_json .update ({"unworked":True ,"run_outcome":_BULK_OUTCOMES [k %4 ]})
            db .add (txn )
            db .commit ()
            db .refresh (txn )
            _bulk_audit (db ,txn ,fc ,state )
            index +=1
    db .commit ()


def _ingest_diagnose (db ,txn :TransactionState ,fc :FailureClass )->None :
    profile =_CLASS_PROFILE [fc ]
    record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .INGEST ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"event":"FLAGGED","class":profile ["label"]},outcome =Outcome .SUCCESS )
    record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .DIAGNOSE ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"root_cause":profile ["root_cause"],
    "recommended_playbook":_DEFAULT_PLAYBOOK [fc ].value ,
    "confidence":profile ["confidence"]},outcome =Outcome .SUCCESS )


def _seed_compliance_stops (db ,now :datetime )->None :
    """Exercise the two time/frequency stopping rules for real so they aren't
    catalog-only: TRAI quiet-hours (defer outbound at night) and the voice-attempt
    cap (block a 3rd call, switch channel). Each genuinely invokes the rule."""

    quiet_dt =now .replace (hour =21 ,minute =34 ,second =0 ,microsecond =0 )
    assert is_within_quiet_hours (quiet_dt )
    idx =30_000
    for fc in (FailureClass .B2B_RECEIVABLES ,FailureClass .SUBSCRIPTION_MANDATE ):
        txn =_new_txn (fc ,idx ,archetype =f"CLASS_{int (fc )}",is_at_risk =True ,
        state =TransactionLifecycleState .WAITING )
        txn .metadata_json ["ai_tag"]="RECOVERY_CASE"
        db .add (txn );db .commit ();db .refresh (txn )
        _ingest_diagnose (db ,txn ,fc )
        record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .WAIT ,
        action_type =ActionType .RETRY_SCHEDULED ,
        payload ={"stopping_rule":StoppingRule .TRAI_QUIET_HOURS .value ,
        "reason":f"Outbound deferred — {quiet_dt :%H:%M} IST is within "
        "TRAI quiet hours (20:00–09:00); will resume at 09:00.",
        "scheduled_for":"09:00 IST"},outcome =Outcome .SUCCESS )
        idx +=1


    assert voice_attempts_exhausted (2 )
    for fc in (FailureClass .SUBSCRIPTION_MANDATE ,FailureClass .REALTIME_DEGRADATION ):
        txn =_new_txn (fc ,idx ,archetype =f"CLASS_{int (fc )}",is_at_risk =True ,
        state =TransactionLifecycleState .RECOVERED ,retry_count =0 )
        txn .metadata_json ["ai_tag"]="RECOVERY_CASE"
        db .add (txn );db .commit ();db .refresh (txn )
        _ingest_diagnose (db ,txn ,fc )
        for _ in range (2 ):
            record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .EXECUTE_INTERVENTION ,
            action_type =ActionType .INTERVENTION_DISPATCH ,
            payload ={"action":InterventionAction .VOICE_CALL .value ,
            "channel":InterventionChannel .VOICE .value },outcome =Outcome .SUCCESS )
        _record_stop (db ,txn .transaction_id ,StoppingRule .VOICE_ATTEMPT_CAP ,
        "2 voice attempts in 72h reached — further calls blocked; switched to WhatsApp.")
        record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .EXECUTE_INTERVENTION ,
        action_type =ActionType .INTERVENTION_DISPATCH ,
        payload ={"action":InterventionAction .SEND_WHATSAPP .value ,
        "channel":InterventionChannel .WHATSAPP .value },outcome =Outcome .SUCCESS )
        record_audit (db ,transaction_id =txn .transaction_id ,node_name =NodeName .RECONCILE ,
        action_type =ActionType .STATE_TRANSITION ,
        payload ={"disposition":"RECOVERED"},outcome =Outcome .SUCCESS )
        idx +=1


    verdict =screen_user_message ("please cancel my subscription")
    assert verdict .rule is StoppingRule .EXPLICIT_CANCEL
    txn =_new_txn (FailureClass .SUBSCRIPTION_MANDATE ,idx ,archetype ="CLASS_3",
    is_at_risk =True ,state =TransactionLifecycleState .CANCELLED )
    txn .metadata_json ["ai_tag"]="RECOVERY_CASE"
    db .add (txn );db .commit ();db .refresh (txn )
    _ingest_diagnose (db ,txn ,FailureClass .SUBSCRIPTION_MANDATE )
    _record_stop (db ,txn .transaction_id ,StoppingRule .EXPLICIT_CANCEL ,verdict .reason )
    db .commit ()


def _tracker_txn (db ,fc :FailureClass ,name :str ,amount_inr :float ,
state :TransactionLifecycleState ,meta :dict )->None :
    db .add (TransactionState (
    transaction_id =f"txn_{int (fc )}_{uuid .uuid4 ().hex [:8 ]}",
    razorpay_payment_id =f"pay_{uuid .uuid4 ().hex [:10 ]}",
    failure_class =int (fc ),
    current_state =state ,
    merchant_id ="merch_rooh",
    customer_contact ="+919900000000",
    amount_minor =int (round (amount_inr *100 )),
    currency ="INR",
    metadata_json ={
    "customer_name":name ,"is_at_risk":True ,"ai_tag":"RECOVERY_CASE",
    "unworked":True ,"run_outcome":"recovered",
    "archetype":f"CLASS_{int (fc )}",**meta ,
    },
    ))


def _seed_trackers (db ,now :datetime )->None :
    """Create representative tracker rows for the Class-3 calendar and Class-4 board.

    These rows provide visible upcoming mandate states and invoices across aging
    buckets without invoking the recovery workflow."""
    today =now .date ()
    P ,W ,I ,R =(TransactionLifecycleState .PENDING ,TransactionLifecycleState .WAITING ,
    TransactionLifecycleState .INTERVENING ,TransactionLifecycleState .RECOVERED )

    subs =[
    ("Meera Iyer","Rooh Pro",799 ,-18 ,1 ,R ),
    ("Farhan Sheikh","Rooh Team",2499 ,-9 ,1 ,R ),
    ("Kavya Bhat","Rooh Studio",4999 ,-3 ,5 ,I ),
    ("Lakshmi Prasad","Rooh Plus",399 ,4 ,1 ,P ),
    ("Neil D'Souza","Rooh Pro",799 ,8 ,28 ,W ),
    ("Aisha Rahman","Rooh Team",2499 ,13 ,1 ,P ),
    ("Ira Banerjee","Rooh Starter",499 ,-25 ,15 ,R ),
    ("Vikram Hegde","Rooh Enterprise",8999 ,6 ,7 ,I ),
    ("Shreya Nair","Rooh Plus",399 ,19 ,28 ,W ),
    ("Omar Siddiqui","Rooh Studio",4999 ,31 ,1 ,P ),
    ]
    for name ,plan ,amt ,in_days ,salary_day ,state in subs :
        _tracker_txn (db ,FailureClass .SUBSCRIPTION_MANDATE ,name ,amt ,state ,{
        "subscription":True ,"plan":plan ,"cycle":"monthly",
        "next_debit_date":(today +timedelta (days =in_days )).isoformat (),
        "salary_day":salary_day ,
        })

    invoices =[
    ("Aurora Healthworks",128000 ,20 ,3 ,None ,P ),
    ("Cedarline Manufacturing",96000 ,10 ,-12 ,None ,P ),
    ("Vertex Learning Labs",210000 ,5 ,-44 ,"P2P",I ),
    ("BlueKite Logistics",74000 ,30 ,-72 ,None ,P ),
    ("Mosaic Foods Co.",156000 ,45 ,-110 ,None ,P ),
    ("Northstar Mobility",88000 ,15 ,-20 ,"P2P",W ),
    ("Riverbend Studios",342000 ,30 ,-181 ,None ,P ),
    ("Solstice Hardware",675000 ,60 ,-95 ,"P2P",I ),
    ("Cobalt Office Systems",54000 ,15 ,12 ,None ,P ),
    ("TerraBloom Organics",189000 ,30 ,-38 ,None ,W ),
    ]
    for buyer ,amt ,term_days ,due_offset ,p2p ,state in invoices :
        due =today +timedelta (days =due_offset )
        meta ={
        "invoice":True ,"invoice_no":f"INV-{2600 +abs (due_offset )}",
        "issue_date":(due -timedelta (days =term_days )).isoformat (),
        "due_date":due .isoformat (),"terms":f"NET{term_days }",
        }
        if p2p :
            meta ["p2p_date"]=(today +timedelta (days =5 )).isoformat ()
        _tracker_txn (db ,FailureClass .B2B_RECEIVABLES ,buyer ,amt ,state ,meta )

    db .commit ()


def _new_txn (fc :FailureClass ,index :int ,*,archetype :str ,is_at_risk :bool ,
state :TransactionLifecycleState ,retry_count :int =0 )->TransactionState :
    profile =_CLASS_PROFILE [fc ]
    who =index %len (_CUSTOMERS )
    return TransactionState (
    transaction_id =f"txn_{int (fc )}_{uuid .uuid4 ().hex [:8 ]}",
    razorpay_payment_id =f"pay_{uuid .uuid4 ().hex [:10 ]}",
    failure_class =int (fc ),
    current_state =state ,
    retry_count =retry_count ,
    merchant_id ="merch_rooh",
    customer_contact =_CONTACTS [who ],
    amount_minor =_amount_for (profile ["base_amount"],index ),
    currency ="INR",
    metadata_json ={
    "archetype":archetype ,
    "class_label":profile ["label"],
    "is_at_risk":is_at_risk ,
    "confidence":profile ["confidence"]if is_at_risk else None ,
    "event_type":profile ["event_type"]if is_at_risk else "payment.captured",
    "error_code":profile ["error_code"]if is_at_risk else None ,
    "customer_name":_CUSTOMERS [who ],
    },
    )


def _seed_context_row (db ,item :ArchetypeSpec ,index :int )->None :
    """Healthy / non-recoverable rows: persisted directly, no orchestration."""
    if item .archetype =="HEALTHY":
        txn =_new_txn (
        item .failure_class ,index ,archetype ="HEALTHY",is_at_risk =False ,
        state =TransactionLifecycleState .RECOVERED ,
        )
        txn .metadata_json ["ai_tag"]="HEALTHY"
    else :
        txn =_new_txn (
        item .failure_class ,index ,archetype ="NON_RECOVERABLE",is_at_risk =True ,
        state =TransactionLifecycleState .FAILED ,
        )
        txn .metadata_json .update ({"ai_tag":"NON_RECOVERABLE","error_code":"HARD_DECLINE"})
    db .add (txn )
    db .commit ()


def _seed_unworked (db ,fc :FailureClass ,run_outcome :str ,index :int )->TransactionState :
    """A flagged-but-unworked case: PENDING, no conversation. the recovery agent runs it live."""
    txn =_new_txn (
    fc ,index ,archetype =f"CLASS_{int (fc )}",is_at_risk =True ,
    state =TransactionLifecycleState .PENDING ,
    )
    txn .metadata_json .update ({"ai_tag":"RECOVERY_CASE","unworked":True ,"run_outcome":run_outcome })
    db .add (txn )
    db .commit ()
    return txn


def simulate_case (db ,failure_class :int |None =None )->TransactionState :
    """Inject one fresh, unworked failure on demand ('a payment just failed')."""
    fc =FailureClass (failure_class )if failure_class else random .choice (list (FailureClass ))
    run_outcome ={1 :"recovered",2 :"recovered",3 :"recovered",4 :"p2p"}[int (fc )]

    index =db .query (TransactionState ).count ()+random .randint (0 ,len (_CUSTOMERS )-1 )
    return _seed_unworked (db ,fc ,run_outcome ,index )


def _seed_case (db ,graph ,item :ScenarioSpec ,index :int )->None :
    fc =item .failure_class
    retry_count =3 if item .outcome =="cancelled_rbi"else 0
    txn =_new_txn (
    fc ,index ,archetype =f"CLASS_{int (fc )}",is_at_risk =True ,
    state =TransactionLifecycleState .PENDING ,retry_count =retry_count ,
    )
    txn .metadata_json ["ai_tag"]="RECOVERY_CASE"
    db .add (txn )
    db .commit ()

    profile =_CLASS_PROFILE [fc ]

    outcome_event =None
    if item .outcome in _RECOVERED_LIKE :
        outcome_event ="payment.authorized"if item .outcome =="late_settlement"else "payment.captured"
    state ={
    "transaction_id":txn .transaction_id ,
    "failure_class":int (fc ),
    "telemetry":{"event_type":profile ["event_type"],"error_code":profile ["error_code"]},
    "outcome_event":outcome_event ,
    }
    if item .outcome =="escalated_dispute":
        state ["user_message"]="I want to dispute this invoice, the amount is wrong."
    elif item .outcome =="cancelled_optout":
        state ["user_message"]="please stop contacting me, band karo."

    graph .invoke (state )



    if item .outcome =="late_settlement":
        _record_stop (
        db ,txn .transaction_id ,StoppingRule .NO_DOUBLE_CHARGE ,
        "Original payment settled late on the primary rail; fallback link voided.",
        )
    elif item .outcome =="cross_device":
        _record_stop (
        db ,txn .transaction_id ,StoppingRule .CROSS_DEVICE_COMPLETION ,
        "Customer completed payment on another device; outreach silenced.",
        )

    _seed_conversation (db ,txn ,int (fc ),item .outcome ,index )


def _record_stop (db ,transaction_id :str ,rule :StoppingRule ,reason :str )->None :
    record_audit (
    db ,
    transaction_id =transaction_id ,
    node_name =NodeName .RECONCILE ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={"stopping_rule":rule .value ,"reason":reason },
    outcome =Outcome .SUCCESS ,
    )


def _seed_conversation (db ,txn :TransactionState ,failure_class :int ,outcome :str ,index :int )->None :
    """Materialise the visible WhatsApp thread (+ call) for a recovery case.

    The customer's words are scripted, but the B2B Promise-to-Pay date is
    extracted from the reply by the real Hinglish resolver and written back onto
    the transaction — the reactive mechanic, driven by the actual reply text.
    """
    meta =txn .metadata_json or {}
    persona =persona_for (index )
    thread =build_thread (
    failure_class =failure_class ,
    outcome =outcome ,
    name =(meta .get ("customer_name")or "there").split ()[0 ],
    amount_inr =txn .amount_minor /100 ,
    persona =persona ,
    payment_link =f"rzp.io/i/{txn .transaction_id [-6 :]}",
    invoice_no =f"INV-{2600 +index }",
    salary_date =next_salary_window (date .today ()),
    )

    seq =0
    for beat in thread .messages :
        db .add (Message (
        transaction_id =txn .transaction_id ,
        direction =beat .direction ,
        sender =beat .sender ,
        body =beat .body ,
        status =beat .status ,
        seq =seq ,
        meta_json =beat .meta ,
        ))
        seq +=1



    if thread .p2p_phrase :
        p2p_date =extract_p2p_date (thread .p2p_phrase ,today =date .today ())
        if p2p_date :
            txn .metadata_json ={**meta ,"p2p_date":p2p_date }

            record_audit (
            db ,
            transaction_id =txn .transaction_id ,
            node_name =NodeName .WAIT ,
            action_type =ActionType .RETRY_SCHEDULED ,
            payload ={"reason":"WAITING_FOR_P2P","scheduled_for":p2p_date ,
            "extracted_from":thread .p2p_phrase },
            outcome =Outcome .SUCCESS ,
            )
            confirmations =[
            (MessageSender .AGENT ,f"Noted — we'll expect payment by {p2p_date }. Thank you! I'll hold reminders until then.",{"p2p_date":p2p_date }),
            (MessageSender .SYSTEM ,f"Dunning paused until {p2p_date } (WAITING_FOR_P2P).",None ),
            (MessageSender .SYSTEM ,f"Payment received on {p2p_date } ✓",None ),
            ]
            for sender ,body ,mj in confirmations :
                db .add (Message (
                transaction_id =txn .transaction_id ,
                direction =MessageDirection .OUTBOUND ,
                sender =sender ,
                body =body ,
                status =MessageStatus .READ ,
                seq =seq ,
                meta_json =mj ,
                ))
                seq +=1

    if thread .call :
        cb =thread .call
        session =CallSession (
        transaction_id =txn .transaction_id ,
        status =cb .status ,
        duration_sec =cb .duration_sec ,
        outcome =cb .outcome ,
        )
        db .add (session )
        db .flush ()
        for turn in cb .turns :
            db .add (CallTurn (
            call_session_id =session .id ,
            speaker =turn .speaker ,
            text =turn .text ,
            seq =turn .at_offset_sec ,
            at_offset_sec =turn .at_offset_sec ,
            ))

    db .commit ()


def _spread_timestamps (db ,now :datetime )->None :
    """Backdate rows across the trailing two weeks so the time-series has shape.

    Recovered rows get a realistic time-to-recovery gap; others resolve quickly.
    """
    rows =db .query (TransactionState ).order_by (TransactionState .id ).all ()
    span_days =14
    for i ,t in enumerate (rows ):
        offset =timedelta (
        days =(i *span_days )//max (len (rows ),1 ),
        hours =(i *7 )%24 ,
        minutes =(i *13 )%60 ,
        )
        created =now -timedelta (days =span_days )+offset
        if t .current_state ==TransactionLifecycleState .RECOVERED and (t .metadata_json or {}).get ("is_at_risk"):
            ttr =timedelta (seconds =45 +(i *37 )%600 )
        else :
            ttr =timedelta (seconds =8 +(i *5 )%40 )
        t .created_at =created
        t .updated_at =created +ttr
    db .commit ()
