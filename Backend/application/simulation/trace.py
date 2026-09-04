"""Turn a case's audit trail into an ordered, readable account of why.

The audit trail is the receipt, but it is written for machines: node names,
action types, and structured payloads. This module renders the same rows as the
sequence of decisions a person can read, without inventing anything - every line
is derived from a row that was actually written, and reasons produced by the
policy sandbox and the compliance rules are surfaced verbatim rather than
rephrased.

Voice follows Frontend-Vision.md section 5: name the rule, the number, and the
reason. "Stopped by policy" is weak; "Stopped - RBI retry cap reached (3 of 3
attempts used)" is the product.
"""

from __future__ import annotations

from dataclasses import asdict ,dataclass ,field

from application .constants import ActionType ,NodeName ,StoppingRule
from application .entities import AuditTrail
from application .operations .compliance_rules import RBI_MAX_RETRIES ,VOICE_ATTEMPT_CAP

_PLAYBOOK_LABEL ={
"REROUTE_RAIL":"re-route to a healthy rail",
"PREAUTH_LINK":"send a pre-authorised link",
"UPI_AUTOPAY_NUDGE":"send a 1-tap UPI Autopay link",
"NEGOTIATION":"negotiate a settlement",
"SALARY_CYCLE_SEQUENCER":"defer the retry to the salary window",
"MANDATE_REFRESH":"refresh the mandate by voice",
"P2P_TRACKER":"extract a promise-to-pay date",
}

_ACTION_LABEL ={
"SEND_WHATSAPP":"WhatsApp message",
"VOICE_CALL":"voice call",
"OFFER_FEE_WAIVER":"fee waiver offer",
"GENERATE_PAYMENT_LINK":"payment link",
"RETRY_CHARGE":"auto-debit retry",
"CANCEL_SUBSCRIPTION":"subscription cancellation",
}


@dataclass
class Budgets :
    """What the agent still had left when a step ran.

    The same four facts the bounds gauge shows, carried on every step so a
    reader can see the budget shrink rather than only its final value.
    """

    retries_used :int =0
    retries_cap :int =RBI_MAX_RETRIES
    voice_used :int =0
    voice_cap :int =VOICE_ATTEMPT_CAP
    channels_used :list [str ]=field (default_factory =list )
    dispatches :int =0


@dataclass
class TraceStep :
    step :int
    node :str
    decision :str
    reason :str
    rule :str |None
    outcome :str
    at :str
    allowed_at_this_moment :Budgets


def _diagnosis_line (payload :dict )->tuple [str ,str ]:
    root =payload .get ("root_cause")or "UNDIAGNOSED"
    playbook =payload .get ("recommended_playbook")or ""
    confidence =payload .get ("confidence")
    plan =_PLAYBOOK_LABEL .get (playbook ,playbook .replace ("_"," ").lower ())

    decision =f"Diagnosed {root .replace ('_',' ').lower ()}"
    reason =f"Chose to {plan }"
    if isinstance (confidence ,(int ,float ))and confidence :
        reason +=f" — {round (float (confidence )*100 )}% confidence"
    return decision ,reason +"."


def _stop_line (rule :str ,payload :dict ,budgets :Budgets )->tuple [str ,str ]:
    """Human copy for a rule that fired.

    A reason written by the engine wins: ``PolicySandbox.validate`` and
    ``screen_user_message`` already phrase these well, and rewriting them here
    would let the two drift.
    """
    engine_reason =payload .get ("reason")

    if rule ==StoppingRule .RBI_MAX_RETRIES .value :
        return (
        "Stopped",
        engine_reason
        or f"RBI retry cap reached ({budgets .retries_cap } of {budgets .retries_cap } attempts used).",
        )
    if rule ==StoppingRule .VOICE_ATTEMPT_CAP .value :
        return (
        "Stopped",
        engine_reason
        or f"Voice attempt cap reached ({budgets .voice_cap } of {budgets .voice_cap } calls in 72 hours).",
        )
    if rule ==StoppingRule .TRAI_QUIET_HOURS .value :
        scheduled =payload .get ("scheduled_for","")
        when =scheduled [11 :16 ]if len (scheduled )>=16 else "09:00"
        return "Deferred",engine_reason or f"TRAI quiet hours — no contact until {when } IST."
    if rule ==StoppingRule .OPT_OUT .value :
        return "Stopped",engine_reason or "The customer opted out of contact."
    if rule ==StoppingRule .EXPLICIT_CANCEL .value :
        return "Stopped",engine_reason or "The customer asked to cancel the plan."
    if rule ==StoppingRule .DISPUTE_FREEZE .value :
        return "Handed to a human",engine_reason or "A dispute is on file — automation frozen."
    if rule ==StoppingRule .NO_DOUBLE_CHARGE .value :
        return "Stopped",engine_reason or "The payment settled late; we will not charge twice."
    if rule ==StoppingRule .CROSS_DEVICE_COMPLETION .value :
        return "Stopped",engine_reason or "The customer already completed this elsewhere."

    return "Stopped",engine_reason or f"Halted by {rule }."


def _render (row :AuditTrail ,budgets :Budgets )->tuple [str ,str ,str |None ]:
    """(decision, reason, rule) for one audit row."""
    payload =row .payload or {}
    rule =payload .get ("stopping_rule")

    if rule :
        decision ,reason =_stop_line (rule ,payload ,budgets )
        return decision ,reason ,rule

    if payload .get ("policy_block"):
        action =_ACTION_LABEL .get (payload .get ("action",""),payload .get ("action",""))
        # The sandbox's own wording, unedited - it names the number and the cap.
        return "Handed to a human",f"Blocked the {action }: {payload ['policy_block']}",None

    if row .node_name ==NodeName .DIAGNOSE :
        decision ,reason =_diagnosis_line (payload )
        return decision ,reason ,None

    if row .action_type ==ActionType .INTERVENTION_DISPATCH :
        action =_ACTION_LABEL .get (payload .get ("action",""),payload .get ("action",""))
        channel =payload .get ("channel")
        playbook =payload .get ("playbook","")
        via =f" over {channel .replace ('_',' ').lower ()}"if channel else ""
        plan =_PLAYBOOK_LABEL .get (playbook ,"")
        return (
        f"Sent a {action }{via }",
        f"Playbook: {plan }."if plan else "Intervention dispatched.",
        None ,
        )

    if row .action_type ==ActionType .RETRY_SCHEDULED :
        scheduled =payload .get ("scheduled_for","")
        if payload .get ("reason")=="SALARY_CYCLE_DEFERRAL":
            return (
            "Waiting",
            f"Held the retry until the salary-credit window on {scheduled }.",
            None ,
            )
        return "Waiting",f"Retry scheduled for {scheduled }.",None

    if payload .get ("disposition")=="RECOVERED":
        return "Recovered",f"Settlement confirmed by {payload .get ('outcome_event')}.",None

    if payload .get ("event")=="AWAITING_OUTCOME":
        return (
        "Still open",
        "No settlement event yet — the case stays open rather than being counted.",
        None ,
        )

    if payload .get ("event")=="ORCHESTRATION_STARTED":
        return "Flagged","Case picked up and moved to diagnosis.",None

    event =payload .get ("event","State change")
    return str (event ).replace ("_"," ").capitalize (),"",None


def build (rows :list [AuditTrail ])->list [TraceStep ]:
    """Render a case's audit rows as an ordered decision trace."""
    budgets =Budgets ()
    steps :list [TraceStep ]=[]

    for index ,row in enumerate (sorted (rows ,key =lambda r :r .id ),start =1 ):
        payload =row .payload or {}

        # Budgets are advanced *before* rendering the row that spent them, so a
        # step reads as "this is what was left when I decided this".
        if row .action_type ==ActionType .INTERVENTION_DISPATCH :
            budgets .dispatches +=1
            channel =payload .get ("channel")
            if channel and channel not in budgets .channels_used :
                budgets .channels_used =[*budgets .channels_used ,channel ]
            if channel =="VOICE":
                budgets .voice_used +=1
            if payload .get ("action")=="RETRY_CHARGE":
                budgets .retries_used +=1
        elif row .action_type ==ActionType .RETRY_SCHEDULED and not payload .get ("stopping_rule"):
            budgets .retries_used +=1

        decision ,reason ,rule =_render (row ,budgets )
        steps .append (
        TraceStep (
        step =index ,
        node =row .node_name .value ,
        decision =decision ,
        reason =reason ,
        rule =rule ,
        outcome =row .outcome .value ,
        at =row .timestamp .isoformat (),
        allowed_at_this_moment =Budgets (
        retries_used =budgets .retries_used ,
        voice_used =budgets .voice_used ,
        channels_used =list (budgets .channels_used ),
        dispatches =budgets .dispatches ,
        ),
        )
        )

    return steps


def serialize (steps :list [TraceStep ])->list [dict ]:
    return [asdict (step )for step in steps ]
