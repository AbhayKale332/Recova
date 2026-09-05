"""Inspectable and editable policy endpoints backed by deterministic compliance validation."""

from fastapi import APIRouter ,Depends ,HTTPException
from pydantic import BaseModel ,Field
from sqlalchemy .orm import Session

from application .persistence import get_db
from application .constants import StoppingRule
from application .operations .policy_guard import ProposedAction ,_MONEY_MOVING_ACTIONS
from application .operations .policy_repository import (
PolicyValidationError ,
get_policy ,
sandbox_for ,
update_policy ,
)
from application .operations .compliance_rules import screen_user_message

router =APIRouter (tags =["policy"])


_RULE_DESCRIPTIONS :dict [StoppingRule ,str ]={
StoppingRule .NO_DOUBLE_CHARGE :"A late settlement kills any in-flight fallback so the customer is never charged twice.",
StoppingRule .CROSS_DEVICE_COMPLETION :"If the customer completes payment on another device, outreach goes silent.",
StoppingRule .RBI_MAX_RETRIES :"RBI permits at most 3 auto-debit retries per cycle; the engine never exceeds it.",
StoppingRule .EXPLICIT_CANCEL :"An explicit cancel request stops the workflow immediately.",
StoppingRule .OPT_OUT :"Any opt-out (incl. Hinglish) halts all further contact, honoured even inside a prompt injection.",
StoppingRule .DISPUTE_FREEZE :"A dispute freezes automation and routes the case to a human.",
StoppingRule .TRAI_QUIET_HOURS :"No outbound voice/messaging between 20:00–09:00 IST (TRAI); contact is deferred.",
StoppingRule .VOICE_ATTEMPT_CAP :"At most 2 voice attempts per rolling 72-hour window.",
}


def _payload (policy :dict )->dict :
    return {
    "policy":policy ,
    "money_moving_actions":sorted (_MONEY_MOVING_ACTIONS ),
    "stopping_rules":[
    {"name":rule .value ,"description":desc }
    for rule ,desc in _RULE_DESCRIPTIONS .items ()
    ],
    }


@router .get ("/policy")
def get_policy_endpoint (db :Session =Depends (get_db ))->dict :
    return _payload (get_policy (db ))


class PolicyPatch (BaseModel ):
    max_discount_pct :int |None =Field (default =None ,ge =0 ,le =100 )
    max_intervention_amount_minor :int |None =Field (default =None ,ge =0 )
    allow_partial_payment :bool |None =None
    min_partial_payment_pct :int |None =Field (default =None ,ge =0 ,le =100 )
    allowed_actions :list [str ]|None =None
    allowed_channels :list [str ]|None =None


@router .patch ("/policy")
def edit_policy (patch :PolicyPatch ,db :Session =Depends (get_db ))->dict :
    """An operator tunes the guardrails. Rejected if an edit is out of range or
    names an action/channel the engine doesn't know."""
    try :
        updated =update_policy (db ,patch .model_dump (exclude_none =True ))
    except PolicyValidationError as exc :
        raise HTTPException (status_code =422 ,detail =str (exc ))
    return _payload (updated )


class ValidateBody (BaseModel ):
    action :str
    channel :str |None =None
    discount_pct :float |None =None
    amount_inr :float |None =None


@router .post ("/policy/validate")
def validate_action (body :ValidateBody ,db :Session =Depends (get_db ))->dict :
    """Run a proposed action through the real PolicySandbox and report the verdict
    — the same gate every recovery action must clear."""
    proposed =ProposedAction (
    action =body .action ,
    channel =body .channel ,
    discount_pct =body .discount_pct ,
    amount_minor =int (body .amount_inr *100 )if body .amount_inr is not None else None ,
    )
    decision =sandbox_for (db ).validate (proposed )
    return {"approved":decision .approved ,"reason":decision .reason }


class ScreenBody (BaseModel ):
    message :str =Field (min_length =1 ,max_length =2000 )


@router .post ("/policy/screen")
def screen_message (body :ScreenBody )->dict :
    """Run a customer message through the deterministic stopping-rule screener —
    the adversarial defence that honours an opt-out even inside a prompt injection."""
    verdict =screen_user_message (body .message )
    return {
    "disposition":verdict .disposition ,
    "rule":verdict .rule .value if verdict .rule else None ,
    "reason":verdict .reason ,
    }
