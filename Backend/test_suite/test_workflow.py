"""Integration tests for the LangGraph recovery orchestrator.

The DiagnosisEngine and the channel dispatcher are injected fakes (offline); the
PolicySandbox and stopping rules are the real deterministic implementations, so
these tests exercise the actual Bouncer inside the graph.
"""

from datetime import datetime

import pytest

from application .constants import (
ActionType ,
EscalationStatus ,
FailureClass ,
NodeName ,
Outcome ,
Playbook ,
StoppingRule ,
TransactionLifecycleState ,
)
from application .helpers import IST
from application .operations .audit_service import record_audit
from application .operations .compliance_rules import VOICE_ATTEMPT_CAP
from application .entities import AuditTrail ,EscalationQueue ,TransactionState
from application .workflow .recovery_graph import OrchestratorDeps ,build_recovery_graph
from application .operations .diagnosis_service import Diagnosis
from application .operations .policy_guard import PolicySandbox
from test_suite .test_fixtures import fixed_clock

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


def _deps (db ,diagnosis ,dispatcher ,clock =None ):
    return OrchestratorDeps (
    db =db ,
    diagnosis =FakeDiagnosis (diagnosis ),
    sandbox =PolicySandbox (POLICY ),
    dispatch =dispatcher ,
    clock =clock or fixed_clock (),
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


# ── The two compliance gates that live inside execute ────────────────────────
#
# Quiet hours and the voice cap are enumerated in StoppingRule and rendered by
# the client's bounds gauge, so the engine has to actually enforce them. The
# clock is injected in every case below: these assertions must not depend on the
# hour the suite happens to run.


def test_quiet_hours_defer_outbound_contact_without_cancelling (db_session ):
    _seed (db_session ,"txn_quiet",FailureClass .CHECKOUT_ABANDONMENT )
    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (
    db_session ,
    Diagnosis ("DROP_OFF",Playbook .UPI_AUTOPAY_NUDGE ),
    dispatcher ,
    clock =fixed_clock (datetime (2026 ,3 ,4 ,21 ,40 ,tzinfo =IST )),
    )
    )

    graph .invoke ({"transaction_id":"txn_quiet"})

    # Deferred, not cancelled — the customer keeps their case, they just do not
    # get messaged at 21:40.
    assert _txn (db_session ,"txn_quiet").current_state ==TransactionLifecycleState .WAITING
    assert dispatcher .calls ==[]

    audits =db_session .query (AuditTrail ).filter_by (transaction_id ="txn_quiet").all ()
    deferral =[a for a in audits if a .action_type ==ActionType .RETRY_SCHEDULED ]
    assert len (deferral )==1
    assert deferral [0 ].payload ["stopping_rule"]==StoppingRule .TRAI_QUIET_HOURS .value
    assert deferral [0 ].payload ["scheduled_for"].startswith ("2026-03-05T09:00")


def test_quiet_hours_do_not_gate_a_channelless_auto_debit_retry (db_session ):
    """An auto-debit retry is not outbound contact, so TRAI does not reach it."""
    _seed (db_session ,"txn_debit",FailureClass .SUBSCRIPTION_MANDATE )
    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (
    db_session ,
    Diagnosis ("MONTH_END_LIQUIDITY_DIP",Playbook .SALARY_CYCLE_SEQUENCER ),
    dispatcher ,
    clock =fixed_clock (datetime (2026 ,3 ,4 ,21 ,40 ,tzinfo =IST )),
    )
    )

    graph .invoke ({"transaction_id":"txn_debit","outcome_event":"payment.captured"})

    assert len (dispatcher .calls )==1
    assert _txn (db_session ,"txn_debit").current_state ==TransactionLifecycleState .RECOVERED


def test_voice_attempt_cap_stops_a_third_call (db_session ):
    _seed (db_session ,"txn_voice",FailureClass .SUBSCRIPTION_MANDATE )
    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (db_session ,Diagnosis ("MANDATE_BROKEN",Playbook .MANDATE_REFRESH ),dispatcher )
    )

    graph .invoke ({"transaction_id":"txn_voice","voice_attempts":VOICE_ATTEMPT_CAP })

    assert _txn (db_session ,"txn_voice").current_state ==TransactionLifecycleState .CANCELLED
    assert dispatcher .calls ==[]

    audits =db_session .query (AuditTrail ).filter_by (transaction_id ="txn_voice").all ()
    stopped =[a for a in audits if (a .payload or {}).get ("stopping_rule")]
    assert stopped [-1 ].payload ["stopping_rule"]==StoppingRule .VOICE_ATTEMPT_CAP .value


def test_voice_call_allowed_while_under_the_cap (db_session ):
    _seed (db_session ,"txn_voice_ok",FailureClass .SUBSCRIPTION_MANDATE )
    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (db_session ,Diagnosis ("MANDATE_BROKEN",Playbook .MANDATE_REFRESH ),dispatcher )
    )

    graph .invoke (
    {"transaction_id":"txn_voice_ok","voice_attempts":VOICE_ATTEMPT_CAP -1 ,
    "outcome_event":"payment.captured"}
    )

    assert len (dispatcher .calls )==1
    assert _txn (db_session ,"txn_voice_ok").current_state ==TransactionLifecycleState .RECOVERED


def test_voice_attempts_are_counted_from_the_audit_trail (db_session ):
    """With no hint on the state, prior dispatches are read back from the trail."""
    _seed (db_session ,"txn_voice_trail",FailureClass .SUBSCRIPTION_MANDATE )
    for _ in range (VOICE_ATTEMPT_CAP ):
        record_audit (
        db_session ,
        transaction_id ="txn_voice_trail",
        node_name =NodeName .EXECUTE_INTERVENTION ,
        action_type =ActionType .INTERVENTION_DISPATCH ,
        payload ={"action":"VOICE_CALL","channel":"VOICE","playbook":"MANDATE_REFRESH"},
        outcome =Outcome .SUCCESS ,
        )

    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (db_session ,Diagnosis ("MANDATE_BROKEN",Playbook .MANDATE_REFRESH ),dispatcher )
    )

    graph .invoke ({"transaction_id":"txn_voice_trail"})

    assert _txn (db_session ,"txn_voice_trail").current_state ==TransactionLifecycleState .CANCELLED
    assert dispatcher .calls ==[]


def test_quiet_hours_bind_before_the_voice_cap (db_session ):
    """Precedence must match armedRule() in Frontend/src/lib/bounds.ts."""
    _seed (db_session ,"txn_prec",FailureClass .SUBSCRIPTION_MANDATE )
    dispatcher =RecordingDispatcher ()
    graph =build_recovery_graph (
    _deps (
    db_session ,
    Diagnosis ("MANDATE_BROKEN",Playbook .MANDATE_REFRESH ),
    dispatcher ,
    clock =fixed_clock (datetime (2026 ,3 ,4 ,21 ,40 ,tzinfo =IST )),
    )
    )

    # Both gates are armed; quiet hours is the one that should be reported.
    graph .invoke ({"transaction_id":"txn_prec","voice_attempts":VOICE_ATTEMPT_CAP })

    assert _txn (db_session ,"txn_prec").current_state ==TransactionLifecycleState .WAITING
    audits =db_session .query (AuditTrail ).filter_by (transaction_id ="txn_prec").all ()
    stopped =[a for a in audits if (a .payload or {}).get ("stopping_rule")]
    assert stopped [-1 ].payload ["stopping_rule"]==StoppingRule .TRAI_QUIET_HOURS .value
