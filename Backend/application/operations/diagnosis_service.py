"""Advisory diagnosis service with schema validation and deterministic class fallbacks."""

import json
import logging
from dataclasses import dataclass
from typing import Any ,Callable

from pydantic import BaseModel ,ValidationError

from application .constants import FailureClass ,Playbook

logger =logging .getLogger (__name__ )



_DEFAULT_PLAYBOOK :dict [FailureClass ,Playbook ]={
FailureClass .REALTIME_DEGRADATION :Playbook .REROUTE_RAIL ,
FailureClass .CHECKOUT_ABANDONMENT :Playbook .UPI_AUTOPAY_NUDGE ,
FailureClass .SUBSCRIPTION_MANDATE :Playbook .SALARY_CYCLE_SEQUENCER ,
FailureClass .B2B_RECEIVABLES :Playbook .P2P_TRACKER ,
}

GenerateFn =Callable [[str ],str ]


@dataclass
class Diagnosis :
    root_cause :str
    recommended_playbook :Playbook
    user_intent_detected :str |None =None
    extracted_p2p_date :str |None =None
    confidence :float =0.0


    proposed_discount_pct :float |None =None


class _DiagnosisPayload (BaseModel ):
    """Shape we require back from the model."""

    root_cause :str
    recommended_playbook :str
    user_intent_detected :str |None =None
    extracted_p2p_date :str |None =None
    confidence :float =0.0
    proposed_discount_pct :float |None =None


class DiagnosisEngine :
    def __init__ (self ,generate :GenerateFn ):
        self ._generate =generate

    def diagnose (
    self ,
    *,
    failure_class :FailureClass ,
    telemetry :dict [str ,Any ],
    user_message :str |None =None ,
    )->Diagnosis :
        prompt =self ._build_prompt (failure_class ,telemetry ,user_message )
        # LLM output is advisory; invalid responses always fall back to the class-specific default.
        try :
            raw =self ._generate (prompt )
            payload =_DiagnosisPayload .model_validate_json (raw )
        except (ValidationError ,ValueError ,json .JSONDecodeError )as exc :
            logger .warning ("Diagnosis response parsing failed (%s); applying the deterministic class default.",exc )
            return self ._fallback (failure_class )
        except Exception as exc :
            logger .warning ("Diagnosis provider call failed (%s); applying the deterministic class default.",exc )
            return self ._fallback (failure_class )

        return Diagnosis (
        root_cause =payload .root_cause ,
        recommended_playbook =self ._coerce_playbook (payload .recommended_playbook ,failure_class ),
        user_intent_detected =payload .user_intent_detected ,
        extracted_p2p_date =payload .extracted_p2p_date ,
        confidence =payload .confidence ,
        proposed_discount_pct =payload .proposed_discount_pct ,
        )

    def _coerce_playbook (self ,value :str ,failure_class :FailureClass )->Playbook :
        try :
            return Playbook (value )
        except ValueError :


            logger .warning ("The model returned unsupported playbook %r; applying the deterministic class default.",value )
            return _DEFAULT_PLAYBOOK [failure_class ]

    def _fallback (self ,failure_class :FailureClass )->Diagnosis :
        return Diagnosis (
        root_cause ="UNDIAGNOSED",
        recommended_playbook =_DEFAULT_PLAYBOOK [failure_class ],
        confidence =0.0 ,
        )

    def _build_prompt (
    self ,
    failure_class :FailureClass ,
    telemetry :dict [str ,Any ],
    user_message :str |None ,
    )->str :
        allowed =", ".join (p .value for p in Playbook )
        parts =[
        "You are the diagnostic layer of a payment-recovery engine.",
        f"The failure has already been classified as {failure_class .name }.",
        "Given the telemetry (and any customer message), return STRICT JSON with keys: "
        "root_cause, recommended_playbook, user_intent_detected, extracted_p2p_date, confidence.",
        f"recommended_playbook MUST be one of: {allowed }.",
        "For any Promise-to-Pay commitment, resolve it to an ISO-8601 UTC timestamp "
        "in extracted_p2p_date; otherwise use null.",
        f"Telemetry: {json .dumps (telemetry )}",
        ]
        if user_message :
            parts .append (f"Customer message: {user_message }")
        return "\n".join (parts )
