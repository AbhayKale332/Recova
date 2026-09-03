import json

from application .constants import FailureClass ,Playbook
from application .operations .diagnosis_service import DiagnosisEngine


def _engine (generate ):
    return DiagnosisEngine (generate =generate )


def test_valid_llm_response_is_parsed ():
    payload ={
    "root_cause":"MONTH_END_LIQUIDITY_DIP",
    "recommended_playbook":"SALARY_CYCLE_SEQUENCER",
    "user_intent_detected":"PROMISE_TO_PAY",
    "extracted_p2p_date":"2026-09-02T09:00:00Z",
    "confidence":0.91 ,
    }
    engine =_engine (lambda prompt :json .dumps (payload ))

    diagnosis =engine .diagnose (
    failure_class =FailureClass .SUBSCRIPTION_MANDATE ,
    telemetry ={"error_code":"INSUFFICIENT_FUNDS","amount_minor":499900 },
    )

    assert diagnosis .root_cause =="MONTH_END_LIQUIDITY_DIP"
    assert diagnosis .recommended_playbook ==Playbook .SALARY_CYCLE_SEQUENCER
    assert diagnosis .extracted_p2p_date =="2026-09-02T09:00:00Z"
    assert diagnosis .confidence ==0.91


def test_malformed_json_falls_back_to_class_default ():
    engine =_engine (lambda prompt :"not json at all")

    diagnosis =engine .diagnose (
    failure_class =FailureClass .REALTIME_DEGRADATION ,
    telemetry ={"error_code":"ISSUER_DOWN"},
    )



    assert diagnosis .recommended_playbook ==Playbook .REROUTE_RAIL
    assert diagnosis .confidence ==0.0


def test_llm_exception_falls_back ():
    def boom (prompt ):
        raise TimeoutError ("model timed out")

    engine =_engine (boom )
    diagnosis =engine .diagnose (
    failure_class =FailureClass .CHECKOUT_ABANDONMENT ,
    telemetry ={"error_code":"AUTH_3DS_DROPPED"},
    )
    assert diagnosis .recommended_playbook ==Playbook .UPI_AUTOPAY_NUDGE
    assert diagnosis .confidence ==0.0


def test_unknown_playbook_is_replaced_with_class_default ():
    payload ={
    "root_cause":"SOME_CAUSE",
    "recommended_playbook":"MADE_UP_PLAYBOOK",
    "confidence":0.7 ,
    }
    engine =_engine (lambda prompt :json .dumps (payload ))

    diagnosis =engine .diagnose (
    failure_class =FailureClass .B2B_RECEIVABLES ,
    telemetry ={"event_type":"invoice.overdue"},
    )


    assert diagnosis .recommended_playbook ==Playbook .P2P_TRACKER
    assert diagnosis .root_cause =="SOME_CAUSE"


def test_prompt_includes_user_message_when_present ():
    seen ={}

    def capture (prompt ):
        seen ["prompt"]=prompt
        return json .dumps ({"root_cause":"X","recommended_playbook":"P2P_TRACKER"})

    engine =_engine (capture )
    engine .diagnose (
    failure_class =FailureClass .B2B_RECEIVABLES ,
    telemetry ={"event_type":"invoice.overdue"},
    user_message ="Will clear 50% next Friday",
    )

    assert "next Friday"in seen ["prompt"]
