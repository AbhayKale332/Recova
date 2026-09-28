"""Advisory diagnosis service with schema validation and deterministic class fallbacks."""

import json
import logging
from dataclasses import dataclass
from typing import Any ,Callable

from pydantic import BaseModel ,ValidationError

from application .constants import FailureClass ,Playbook
from application .operations .model_router import ModelRouter
from application .operations .playbook_map import DEFAULT_PLAYBOOK ,PLAYBOOK_CRITERIA ,ROOT_CAUSES
from application .operations import jev_client
from application .operations .jev_client import DecisionUnavailable ,route_decision_for

logger =logging .getLogger (__name__ )



# Compatibility spelling for older callers; new code imports DEFAULT_PLAYBOOK
# from the neutral operations map.
_DEFAULT_PLAYBOOK = DEFAULT_PLAYBOOK

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


# Jev's playbook choice below this confidence is treated as no diagnosis: the
# class default playbook is the safer route. Probe (2026-09-28): the nine
# clear cases scored 0.94-1.00; "we never received half of these goods" on an
# overdue invoice (no playbook fits a dispute) scored 0.43.
DIAGNOSE_MIN_CONFIDENCE =0.5

_CLASS_SITUATION ={
FailureClass .REALTIME_DEGRADATION :"A payment failed at checkout with a gateway or bank error.",
FailureClass .CHECKOUT_ABANDONMENT :"A checkout was not completed.",
FailureClass .SUBSCRIPTION_MANDATE :"A recurring auto-debit (subscription mandate) failed.",
FailureClass .B2B_RECEIVABLES :"A business invoice is overdue; there is no gateway error code.",
}


def _jev_state (failure_class :FailureClass ,telemetry :dict [str ,Any ],user_message :str |None )->dict :
    # Only the fields the questions read. Amounts are a code-side concern.
    signals ={k :v for k ,v in telemetry .items ()if k not in ("amount_minor",)and v is not None }
    state :dict [str ,Any ]={"situation":_CLASS_SITUATION [failure_class ],"gateway_signals":signals }
    if user_message :
        state ["customer_message"]=user_message
    return state


class DiagnosisEngine :
    def __init__ (
    self ,
    generate :GenerateFn |None =None ,
    router :ModelRouter |None =None ,
    *,
    use_jev :bool =True ,
    jev :Callable [...,jev_client .Judgments ]|None =None ,
    ):
        self ._generate =generate
        self ._router =router
        self ._use_jev =use_jev
        self ._jev =jev
        self .last_route_decision =None
        self .last_judgment :dict |None =None

    def _diagnose_with_jev (
    self ,
    failure_class :FailureClass ,
    telemetry :dict [str ,Any ],
    user_message :str |None ,
    )->Diagnosis :
        """Jev picks the playbook and the root cause from closed sets."""
        causes =ROOT_CAUSES [failure_class ]
        questions ={
        "playbook":jev_client .choice (
        "Which recovery playbook fits this failed payment, given `gateway_signals` and any "
        "`customer_message`? The customer's own words outweigh the gateway code.",
        {p .value :PLAYBOOK_CRITERIA [p ]for p in Playbook },
        ),
        "root_cause":jev_client .choice (
        "What most likely caused this payment to fail, given `gateway_signals` and any `customer_message`?",
        causes ,
        ),
        }
        judgments =(self ._jev or jev_client .decide )(
        _jev_state (failure_class ,telemetry ,user_message ),questions
        )
        playbook =judgments .choice ("playbook")
        cause =judgments .choice ("root_cause")
        confidence =playbook .confidence if playbook .confidence is not None else 1.0
        if confidence <DIAGNOSE_MIN_CONFIDENCE :
            chosen =DEFAULT_PLAYBOOK [failure_class ]
            reason =f"Jev unsure on playbook (confidence {confidence :.2f}) → class default {chosen .value }"
        else :
            chosen =Playbook (playbook .choice )
            reason =f"Jev diagnosed {cause .choice } → {chosen .value } (confidence {confidence :.2f})"
        self .last_route_decision =route_decision_for ("DIAGNOSE",judgments ,reason )
        self .last_judgment =jev_client .summarise (judgments )
        return Diagnosis (
        root_cause =cause .choice if cause .choice !="UNKNOWN"else "UNDIAGNOSED",
        recommended_playbook =chosen ,
        confidence =round (confidence ,4 ),
        )

    def diagnose (
    self ,
    *,
    failure_class :FailureClass ,
    telemetry :dict [str ,Any ],
    user_message :str |None =None ,
    )->Diagnosis :
        self .last_route_decision =None
        self .last_judgment =None
        if self ._use_jev :
            try :
                return self ._diagnose_with_jev (failure_class ,telemetry ,user_message )
            except DecisionUnavailable as exc :
                logger .info ("Jev diagnosis unavailable (%s); using the LLM diagnosis.",exc )
        prompt =self ._build_prompt (failure_class ,telemetry ,user_message )
        # LLM output is advisory; invalid responses always fall back to the class-specific default.
        try :
            if self ._router is not None:
                amount_minor =telemetry .get ("amount_minor",0 )
                routed =self ._router .call (
                "DIAGNOSE" ,prompt ,amount_inr =float (amount_minor )/100
                )
                self .last_route_decision =routed .decision
                raw =routed .result
            elif self ._generate is not None:
                raw =self ._generate (prompt )
            else:
                raise RuntimeError ("No diagnosis generator configured")
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
            return DEFAULT_PLAYBOOK [failure_class ]

    def _fallback (self ,failure_class :FailureClass )->Diagnosis :
        return Diagnosis (
        root_cause ="UNDIAGNOSED",
        recommended_playbook =DEFAULT_PLAYBOOK [failure_class ],
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
