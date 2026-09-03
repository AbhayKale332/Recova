"""Integration tests for the LangGraph recovery orchestrator.

The DiagnosisEngine and the channel dispatcher are injected fakes (offline); the
PolicySandbox and stopping rules are the real deterministic implementations, so
these tests exercise the actual Bouncer inside the graph.
"""

import pytest

from application .constants import (
EscalationStatus ,
FailureClass ,
NodeName ,
Playbook ,
TransactionLifecycleState ,
)
from application .entities import AuditTrail ,EscalationQueue ,TransactionState
from application .workflow .recovery_graph import OrchestratorDeps ,build_recovery_graph
from application .operations .diagnosis_service import Diagnosis
from application .operations .policy_guard import PolicySandbox

POLICY ={
"max_discount_pct":15 ,
"max_intervention_amount_minor":1_000_000 ,
"allowed_channels":["WHATSAPP","VOICE","PAYMENT_LINK"],
"allowed_actions":[
"SEND_WHATSAPP",
"VOICE_CALL",
"OFFER_FEE_WAIVER",
"GENERATE_PAYMENT_LINK",
"RETRY_CHARGE",
"CANCEL_SUBSCRIPTION",
],
}


class FakeDiagnosis :
    """Stands in for the Gemini-backed engine with a fixed diagnosis."""

    def __init__ (self ,diagnosis :Diagnosis ):
        self ._diagnosis =diagnosis

    def diagnose (self ,**kwargs )->Diagnosis :
        return self ._diagnosis


class RecordingDispatcher :
    def __init__ (self ):
        self .calls =[]

    def __call__ (self ,action ,state ):
        self .calls .append (action )
        return {"delivered":True }


def _seed (db ,transaction_id ,failure_class ,amount_minor =150000 ):
    db .add (
    TransactionState (
    transaction_id =transaction_id ,
    razorpay_payment_id ="pay_"+transaction_id ,
    failure_class =failure_class ,
    current_state =TransactionLifecycleState .PENDING ,
    merchant_id ="merch_1",
    customer_contact ="+919999999999",
    amount_minor =amount_minor ,
    )
    )
    db .commit ()


def _deps (db ,diagnosis ,dispatcher ):
    return OrchestratorDeps (
    db =db ,
    diagnosis =FakeDiagnosis (diagnosis ),
    sandbox =PolicySandbox (POLICY ),
    dispatch =dispatcher ,
    )


def _txn (db ,transaction_id ):
    return db .query (TransactionState ).filter_by (transaction_id =transaction_id ).one ()


def test_class1_intervenes_and_recovers (db_session ):
    _seed (db_session ,"txn_c1",FailureClass .REALTIME_DEGRADATION )
    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (db_session ,Diagnosis ("ISSUER_DOWN",Playbook .REROUTE_RAIL ),dispatcher )
    )

    graph .invoke (
    {"transaction_id":"txn_c1","outcome_event":"payment.captured"}
    )

    assert _txn (db_session ,"txn_c1").current_state ==TransactionLifecycleState .RECOVERED
    assert len (dispatcher .calls )==1


def test_class3_routes_through_wait_state (db_session ):
    _seed (db_session ,"txn_c3",FailureClass .SUBSCRIPTION_MANDATE )
    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (
    db_session ,
    Diagnosis ("MONTH_END_LIQUIDITY_DIP",Playbook .SALARY_CYCLE_SEQUENCER ),
    dispatcher ,
    )
    )

    graph .invoke ({"transaction_id":"txn_c3","outcome_event":"payment.captured"})

    audits =db_session .query (AuditTrail ).filter_by (transaction_id ="txn_c3").all ()
    assert any (a .node_name ==NodeName .WAIT for a in audits )
    assert _txn (db_session ,"txn_c3").current_state ==TransactionLifecycleState .RECOVERED


def test_optout_message_cancels_without_dispatch (db_session ):
    _seed (db_session ,"txn_opt",FailureClass .CHECKOUT_ABANDONMENT )
    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (db_session ,Diagnosis ("DROP_OFF",Playbook .UPI_AUTOPAY_NUDGE ),dispatcher )
    )

    graph .invoke ({"transaction_id":"txn_opt","user_message":"please STOP messaging me"})

    assert _txn (db_session ,"txn_opt").current_state ==TransactionLifecycleState .CANCELLED

    assert dispatcher .calls ==[]


def test_dispute_message_escalates (db_session ):
    _seed (db_session ,"txn_disp",FailureClass .B2B_RECEIVABLES ,amount_minor =500000 )
    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (db_session ,Diagnosis ("OVERDUE",Playbook .P2P_TRACKER ),dispatcher )
    )

    graph .invoke (
    {"transaction_id":"txn_disp","user_message":"this invoice is wrong, I dispute it"}
    )

    assert _txn (db_session ,"txn_disp").current_state ==TransactionLifecycleState .ESCALATED
    tickets =db_session .query (EscalationQueue ).filter_by (transaction_id ="txn_disp").all ()
    assert len (tickets )==1
    assert tickets [0 ].status ==EscalationStatus .OPEN
    assert dispatcher .calls ==[]


def test_policy_blocked_discount_escalates_without_dispatch (db_session ):
    _seed (db_session ,"txn_block",FailureClass .CHECKOUT_ABANDONMENT )
    dispatcher =RecordingDispatcher ()

    diagnosis =Diagnosis (
    "PRICE_OBJECTION",Playbook .NEGOTIATION ,proposed_discount_pct =100
    )
    graph =build_recovery_graph (_deps (db_session ,diagnosis ,dispatcher ))

    graph .invoke ({"transaction_id":"txn_block"})

    assert _txn (db_session ,"txn_block").current_state ==TransactionLifecycleState .ESCALATED
    assert dispatcher .calls ==[]
