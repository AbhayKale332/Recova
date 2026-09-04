"""Recovery workflow nodes that persist state transitions and audit every decision."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING ,Any ,Callable

from langgraph .graph import END

from application .constants import (
ActionType ,
FailureClass ,
InterventionAction ,
InterventionChannel ,
NodeName ,
Outcome ,
Playbook ,
TransactionLifecycleState ,
)
from application .entities import TransactionState
from application .workflow .workflow_state import RecoveryState
from application .operations .audit_service import record_audit
from application .operations .escalation_service import enqueue_escalation
from application .operations .policy_guard import ProposedAction
from application .operations .compliance_rules import (
VOICE_ATTEMPT_CAP ,
is_within_quiet_hours ,
retry_cap_exceeded ,
screen_user_message ,
voice_attempts_exhausted ,
)
from application .constants import StoppingRule
from application .entities import AuditTrail
from application .helpers import next_quiet_hours_end ,next_salary_window

if TYPE_CHECKING :
    from application .workflow .recovery_graph import OrchestratorDeps

_RECOVERY_OUTCOMES ={"payment.captured","payment.authorized"}



# This translation is policy-neutral; the PolicySandbox validates the resulting action before dispatch.
_PLAYBOOK_ACTION :dict [Playbook ,tuple [InterventionAction ,InterventionChannel |None ]]={
Playbook .REROUTE_RAIL :(InterventionAction .GENERATE_PAYMENT_LINK ,InterventionChannel .PAYMENT_LINK ),
Playbook .PREAUTH_LINK :(InterventionAction .GENERATE_PAYMENT_LINK ,InterventionChannel .PAYMENT_LINK ),
Playbook .UPI_AUTOPAY_NUDGE :(InterventionAction .SEND_WHATSAPP ,InterventionChannel .WHATSAPP ),
Playbook .NEGOTIATION :(InterventionAction .OFFER_FEE_WAIVER ,InterventionChannel .WHATSAPP ),
Playbook .SALARY_CYCLE_SEQUENCER :(InterventionAction .RETRY_CHARGE ,None ),
Playbook .MANDATE_REFRESH :(InterventionAction .VOICE_CALL ,InterventionChannel .VOICE ),
Playbook .P2P_TRACKER :(InterventionAction .SEND_WHATSAPP ,InterventionChannel .WHATSAPP ),
}


def _txn (deps :"OrchestratorDeps",transaction_id :str )->TransactionState :
    return deps .db .query (TransactionState ).filter_by (transaction_id =transaction_id ).one ()


def _voice_attempts (deps :"OrchestratorDeps",transaction_id :str ,state :RecoveryState )->int :
    """How many voice calls this case has already placed.

    Read from the audit trail rather than a column so the count survives a
    restart and matches exactly what the bounds gauge derives on the client
    (see ``computeBounds`` in Frontend/src/lib/bounds.ts). A caller that already
    knows the number - a simulated scenario starting a case mid-history - may
    pass it in ``state`` instead.
    """
    seeded =state .get ("voice_attempts")
    if seeded is not None :
        return int (seeded )

    rows =(
    deps .db .query (AuditTrail )
    .filter (
    AuditTrail .transaction_id ==transaction_id ,
    AuditTrail .action_type ==ActionType .INTERVENTION_DISPATCH ,
    )
    .all ()
    )
    return sum (1 for row in rows if (row .payload or {}).get ("channel")==InterventionChannel .VOICE .value )


def _finalize (deps ,transaction_id ,disposition ,node_name ,payload ,outcome )->None :
    """Write the terminal lifecycle state and its audit entry."""
    txn =_txn (deps ,transaction_id )
    txn .current_state =TransactionLifecycleState (disposition )
    deps .db .commit ()
    record_audit (
    deps .db ,
    transaction_id =transaction_id ,
    node_name =node_name ,
    action_type =ActionType .STATE_TRANSITION ,
    payload =payload ,
    outcome =outcome ,
    )


def build_nodes (deps :"OrchestratorDeps")->dict [str ,Callable [[RecoveryState ],dict [str ,Any ]]]:
    def ingest (state :RecoveryState )->dict [str ,Any ]:
        transaction_id =state ["transaction_id"]
        txn =_txn (deps ,transaction_id )
        txn .current_state =TransactionLifecycleState .DIAGNOSING
        deps .db .commit ()
        record_audit (
        deps .db ,
        transaction_id =transaction_id ,
        node_name =NodeName .INGEST ,
        action_type =ActionType .STATE_TRANSITION ,
        payload ={"event":"ORCHESTRATION_STARTED","to":"DIAGNOSING"},
        outcome =Outcome .SUCCESS ,
        )



        # Screen customer intent before model diagnosis so opt-outs and disputes cannot be overridden.
        message =state .get ("user_message")
        if message :
            verdict =screen_user_message (message )
            if verdict .disposition =="TERMINATE":
                _finalize (
                deps ,transaction_id ,"CANCELLED",NodeName .INGEST ,
                {"stopping_rule":verdict .rule .value ,"reason":verdict .reason },
                Outcome .SUCCESS ,
                )
                return {"disposition":"CANCELLED","stopping_rule":verdict .rule .value }
            if verdict .disposition =="ESCALATE":
                enqueue_escalation (
                deps .db ,transaction_id =transaction_id ,reason =verdict .reason ,rule =verdict .rule
                )
                _finalize (
                deps ,transaction_id ,"ESCALATED",NodeName .INGEST ,
                {"stopping_rule":verdict .rule .value ,"reason":verdict .reason },
                Outcome .ESCALATED ,
                )
                return {"disposition":"ESCALATED","stopping_rule":verdict .rule .value }

        return {
        "failure_class":int (txn .failure_class ),
        "retry_count":txn .retry_count ,
        "lifecycle":TransactionLifecycleState .DIAGNOSING .value ,
        }

    def diagnose (state :RecoveryState )->dict [str ,Any ]:
        transaction_id =state ["transaction_id"]
        diagnosis =deps .diagnosis .diagnose (
        failure_class =FailureClass (state ["failure_class"]),
        telemetry =state .get ("telemetry",{}),
        user_message =state .get ("user_message"),
        )
        # A custom scenario may pin the playbook while keeping diagnosis advisory.
        # The override is scoped to this graph invocation and never touches policy.
        override =state .get ("playbook")
        if override :
            try :
                diagnosis.recommended_playbook =Playbook (override )
            except ValueError :
                pass
        record_audit (
        deps .db ,
        transaction_id =transaction_id ,
        node_name =NodeName .DIAGNOSE ,
        action_type =ActionType .STATE_TRANSITION ,
        payload ={
        "root_cause":diagnosis .root_cause ,
        "recommended_playbook":diagnosis .recommended_playbook .value ,
        "confidence":diagnosis .confidence ,
        },
        outcome =Outcome .SUCCESS ,
        )
        return {
        "playbook":diagnosis .recommended_playbook .value ,
        "root_cause":diagnosis .root_cause ,
        "proposed_discount_pct":diagnosis .proposed_discount_pct ,
        }

    def wait (state :RecoveryState )->dict [str ,Any ]:
        transaction_id =state ["transaction_id"]
        txn =_txn (deps ,transaction_id )
        txn .current_state =TransactionLifecycleState .WAITING
        deps .db .commit ()
        scheduled_for =next_salary_window (date .today ())
        record_audit (
        deps .db ,
        transaction_id =transaction_id ,
        node_name =NodeName .WAIT ,
        action_type =ActionType .RETRY_SCHEDULED ,
        payload ={"reason":"SALARY_CYCLE_DEFERRAL","scheduled_for":scheduled_for },
        outcome =Outcome .SUCCESS ,
        )
        return {"lifecycle":TransactionLifecycleState .WAITING .value }

    def execute (state :RecoveryState )->dict [str ,Any ]:
        transaction_id =state ["transaction_id"]
        txn =_txn (deps ,transaction_id )
        playbook =Playbook (state ["playbook"])
        action_type ,channel =_PLAYBOOK_ACTION [playbook ]

        # Precedence below is quiet hours -> retry cap -> voice cap, and must stay
        # identical to armedRule() in Frontend/src/lib/bounds.ts. Quiet hours bind
        # first because they gate every outbound channel.

        # TRAI quiet hours govern outbound *contact*, so a channel-less auto-debit
        # retry is exempt. This defers the case; it never cancels it.
        clock =state .get ("now_ist")or deps .clock ()
        if channel is not None and is_within_quiet_hours (clock ):
            resume_at =next_quiet_hours_end (clock )
            txn .current_state =TransactionLifecycleState .WAITING
            deps .db .commit ()
            record_audit (
            deps .db ,
            transaction_id =transaction_id ,
            node_name =NodeName .EXECUTE_INTERVENTION ,
            action_type =ActionType .RETRY_SCHEDULED ,
            payload ={
            "stopping_rule":StoppingRule .TRAI_QUIET_HOURS .value ,
            "reason":f"TRAI quiet hours - no contact until {resume_at .strftime ('%H:%M')} IST.",
            "scheduled_for":resume_at .isoformat (),
            "deferred_action":action_type .value ,
            },
            outcome =Outcome .SUCCESS ,
            )
            return {
            "disposition":"WAITING",
            "stopping_rule":StoppingRule .TRAI_QUIET_HOURS .value ,
            "lifecycle":TransactionLifecycleState .WAITING .value ,
            }

        if action_type ==InterventionAction .RETRY_CHARGE and retry_cap_exceeded (
        state .get ("retry_count",0 )
        ):
            _finalize (
            deps ,transaction_id ,"CANCELLED",NodeName .EXECUTE_INTERVENTION ,
            {"stopping_rule":"RBI_MAX_RETRIES"},Outcome .SUCCESS ,
            )
            return {"disposition":"CANCELLED","stopping_rule":"RBI_MAX_RETRIES"}

        if channel ==InterventionChannel .VOICE :
            attempts =_voice_attempts (deps ,transaction_id ,state )
            if voice_attempts_exhausted (attempts ):
                _finalize (
                deps ,transaction_id ,"CANCELLED",NodeName .EXECUTE_INTERVENTION ,
                {
                "stopping_rule":StoppingRule .VOICE_ATTEMPT_CAP .value ,
                "reason":f"Voice attempt cap reached ({attempts } of {VOICE_ATTEMPT_CAP } calls in 72 hours).",
                },
                Outcome .SUCCESS ,
                )
                return {
                "disposition":"CANCELLED",
                "stopping_rule":StoppingRule .VOICE_ATTEMPT_CAP .value ,
                }

        # Build the action from persisted transaction data, then validate it before any external call.
        action =ProposedAction (
        action =action_type ,
        channel =channel ,
        discount_pct =state .get ("proposed_discount_pct"),
        amount_minor =txn .amount_minor ,
        )
        decision =deps .sandbox .validate (action )
        if not decision .approved :
            enqueue_escalation (deps .db ,transaction_id =transaction_id ,reason =decision .reason )
            _finalize (
            deps ,transaction_id ,"ESCALATED",NodeName .EXECUTE_INTERVENTION ,
            {"policy_block":decision .reason ,"action":action .action_value },
            Outcome .ESCALATED ,
            )
            return {"disposition":"ESCALATED"}

        txn .current_state =TransactionLifecycleState .INTERVENING
        deps .db .commit ()
        deps .dispatch (action ,state )
        record_audit (
        deps .db ,
        transaction_id =transaction_id ,
        node_name =NodeName .EXECUTE_INTERVENTION ,
        action_type =ActionType .INTERVENTION_DISPATCH ,
        payload ={
        "action":action .action_value ,
        "channel":action .channel_value ,
        "playbook":playbook .value ,
        },
        outcome =Outcome .SUCCESS ,
        )
        return {"lifecycle":TransactionLifecycleState .INTERVENING .value }

    def reconcile (state :RecoveryState )->dict [str ,Any ]:
        transaction_id =state ["transaction_id"]
        # Only recognized settlement events close a case; all other outcomes remain auditable and open.
        outcome_event =state .get ("outcome_event")
        if outcome_event in _RECOVERY_OUTCOMES :
            _finalize (
            deps ,transaction_id ,"RECOVERED",NodeName .RECONCILE ,
            {"outcome_event":outcome_event ,"disposition":"RECOVERED"},
            Outcome .SUCCESS ,
            )
            return {"disposition":"RECOVERED"}




        record_audit (
        deps .db ,
        transaction_id =transaction_id ,
        node_name =NodeName .RECONCILE ,
        action_type =ActionType .STATE_TRANSITION ,
        payload ={"event":"AWAITING_OUTCOME","outcome_event":outcome_event },
        outcome =Outcome .SUCCESS ,
        )
        return {"disposition":None }

    return {"ingest":ingest ,"diagnose":diagnose ,"wait":wait ,"execute":execute ,"reconcile":reconcile }




def route_after_ingest (state :RecoveryState )->str :
    return END if state .get ("disposition")else "diagnose"


def route_after_diagnose (state :RecoveryState )->str :
    return "wait"if state .get ("playbook")==Playbook .SALARY_CYCLE_SEQUENCER .value else "execute"


def route_after_execute (state :RecoveryState )->str :
    return END if state .get ("disposition")else "reconcile"
