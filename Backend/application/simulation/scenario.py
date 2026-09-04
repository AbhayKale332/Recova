"""The scenario a user submits to the simulator, and the cases it expands into.

A scenario is a *question*: "across 200 cases weighted like this, at 21:40, with
the discount cap at 0%, what does the engine do and what does it recover?" It is
never persisted as policy - the policy overrides here build a scenario-scoped
PolicySandbox and the merchant's own ``merchant_policy`` row is left untouched.

Case vocabulary (names, telemetry, root causes, amounts) is borrowed from
``batch_seed.class_profile`` so a simulated case and a seeded case never tell two
different stories about the same failure class.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel ,Field ,model_validator

from application .constants import (
FailureClass ,
InterventionChannel ,
TransactionLifecycleState ,
)
from application .entities import TransactionState
from application .helpers import IST
from application .operations .batch_seed import _CONTACTS ,_CUSTOMERS ,class_profile
from application .operations .compliance_rules import (
RBI_MAX_RETRIES ,
VOICE_ATTEMPT_CAP ,
is_within_quiet_hours ,
retry_cap_exceeded ,
screen_user_message ,
voice_attempts_exhausted ,
)
from application .simulation import probability

# What the customer does when the agent reaches out. These are the levers that
# make the guardrails visibly fire, so they are first-class scenario inputs
# rather than something the seeder decides.
ReplyKind =Literal ["cooperative","opt_out","dispute","p2p","silent"]

_REPLY_TEXT :dict [ReplyKind ,str |None ]={
"cooperative":None ,
"opt_out":"please stop contacting me, band karo.",
"dispute":"I want to dispute this invoice, the amount is wrong.",
"p2p":"5 tarikh ko kar denge, thoda time chahiye.",
"silent":None ,
}


class CustomCase (BaseModel ):
    """One case authored by the operator rather than generated from weights."""

    customer_name :str =Field (min_length =1 ,max_length =80 )
    # Scenario inputs use rupees. The planning boundary converts this once to paise.
    amount_inr :float =Field (gt =0 ,le =100_000_000 )
    failure_class :int =Field (ge =1 ,le =4 )
    reply_text :str |None =Field (None ,max_length =280 )
    reply :ReplyKind |None =None
    retries_used :int =Field (0 ,ge =0 ,le =5 )
    voice_attempts :int =Field (0 ,ge =0 ,le =5 )
    days_overdue :int =Field (0 ,ge =0 ,le =365 )
    outcome_event :str |None =Field (None ,max_length =64 )
    playbook :str |None =Field (None ,max_length =64 )


class CaseShape (BaseModel ):
    """How much revenue is at risk, and what kind."""

    count :int =Field (200 ,ge =0 ,le =500 )
    # Relative weights over failure classes 1-4. Normalised, so {1: 3, 3: 1} is
    # a book that is three-quarters rail failures.
    class_mix :dict [int ,float ]=Field (default_factory =lambda :{1 :1.0 ,2 :1.0 ,3 :1.0 ,4 :1.0 })
    # Multiplier on each class's own base amount, so a scenario can ask "what if
    # our average ticket doubled" without hardcoding rupee values per class.
    amount_scale :float =Field (1.0 ,gt =0 ,le =20 )
    # Deterministic spread around that amount, as a fraction. 0 makes every case
    # in a class identical, which is useful for isolating one variable.
    amount_spread :float =Field (0.35 ,ge =0 ,le =0.9 )
    amount_min_inr :float |None =Field (None ,gt =0 ,le =100_000_000 )
    amount_max_inr :float |None =Field (None ,gt =0 ,le =100_000_000 )

    @model_validator (mode ="after")
    def _check_mix (self )->"CaseShape":
        cleaned ={int (k ):float (v )for k ,v in self .class_mix .items ()if float (v )>0 }
        if not cleaned and self .count >0 :
            raise ValueError ("class_mix must give positive weight to at least one class")
        unknown =set (cleaned )-{1 ,2 ,3 ,4 }
        if unknown :
            raise ValueError (f"class_mix has unknown failure classes: {sorted (unknown )}")
        if (
            self .amount_min_inr is not None
            and self .amount_max_inr is not None
            and self .amount_min_inr > self .amount_max_inr
        ):
            raise ValueError ("amount_min_inr cannot exceed amount_max_inr")
        self .class_mix =cleaned
        return self


class EdgeCases (BaseModel ):
    """The conditions that make stopping rules fire."""

    reply_mix :dict [ReplyKind ,float ]=Field (
    default_factory =lambda :{"cooperative":7.0 ,"p2p":1.0 ,"opt_out":1.0 ,"dispute":1.0 }
    )
    reply_texts :dict [ReplyKind ,str ]=Field (default_factory =dict)
    retries_already_used :int =Field (0 ,ge =0 ,le =5 )
    voice_attempts_used :int =Field (0 ,ge =0 ,le =5 )
    # IST wall clock the run is evaluated at. 21:40 arms TRAI quiet hours.
    clock_ist :datetime |None =None
    # Share of cases where the original payment settles late (NO_DOUBLE_CHARGE)
    # or the customer already paid elsewhere (CROSS_DEVICE_COMPLETION).
    late_settlement_pct :float =Field (0.0 ,ge =0 ,le =100 )
    cross_device_pct :float =Field (0.0 ,ge =0 ,le =100 )
    days_overdue :int =Field (35 ,ge =0 ,le =365 )

    @model_validator (mode ="after")
    def _check_replies (self )->"EdgeCases":
        cleaned ={k :float (v )for k ,v in self .reply_mix .items ()if float (v )>0 }
        if not cleaned :
            raise ValueError ("reply_mix must give positive weight to at least one reply")
        self .reply_mix =cleaned
        self .reply_texts ={key :value for key ,value in self .reply_texts .items ()if value.strip ()}
        if self .late_settlement_pct +self .cross_device_pct >100 :
            raise ValueError ("late_settlement_pct + cross_device_pct cannot exceed 100")
        return self

    def clock (self )->datetime :
        return self .clock_ist or datetime .now (IST )


class PolicyOverrides (BaseModel ):
    """Scenario-scoped policy. Never written to the merchant_policy table."""

    max_discount_pct :float |None =Field (None ,ge =0 ,le =100 )
    max_intervention_amount_minor :int |None =Field (None ,ge =0 )
    allowed_channels :list [str ]|None =None
    allowed_actions :list [str ]|None =None

    def applied_to (self ,base :dict )->dict :
        merged =dict (base )
        for key ,value in self .model_dump (exclude_none =True ).items ():
            merged [key ]=value
        return merged


class Scenario (BaseModel ):
    name :str =Field ("Custom scenario",max_length =80 )
    description :str =Field ("",max_length =240 )
    cases :CaseShape =Field (default_factory =CaseShape )
    edge_cases :EdgeCases =Field (default_factory =EdgeCases )
    policy :PolicyOverrides =Field (default_factory =PolicyOverrides )
    locale :Literal ["en","hi"]="en"
    custom_cases :list [CustomCase ]=Field (default_factory =list ,max_length =500 )
    live_diagnosis :bool =False

    @model_validator (mode ="after")
    def _check_total (self )->"Scenario":
        total =len (self .custom_cases )+self .cases .count
        if not 1 <=total <=500 :
            raise ValueError ("custom_cases + cases.count must contain between 1 and 500 cases")
        if self .live_diagnosis and total >25 :
            raise ValueError ("live_diagnosis is limited to 25 cases")
        return self


@dataclass
class PlannedCase :
    """One case the scenario expands into, before the engine has seen it."""

    transaction_id :str
    failure_class :int
    amount_minor :int
    customer_name :str
    reply :ReplyKind |None
    reply_text :str |None
    retries_used :int
    voice_attempts :int
    outcome_event :str |None
    days_overdue :int
    probability :probability .CaseProbability
    playbook :str |None =None

    @property
    def amount_inr (self )->float :
        return round (self .amount_minor /100 ,2 )

    @property
    def user_message (self )->str |None :
        if self .reply_text is not None :
            return self .reply_text
        return _REPLY_TEXT .get (self .reply )


def _weighted_cycle (weights :dict ,count :int )->list :
    """Deterministically expand weights into ``count`` picks.

    Deterministic on purpose: the same scenario must produce the same book every
    time, or a judge cannot compare two runs and the numbers stop meaning
    anything. Largest-remainder apportionment, then interleaved so the classes
    are not delivered in blocks.
    """
    if count <=0 :
        return []
    total =sum (weights .values ())
    exact ={key :count *weight /total for key ,weight in weights .items ()}
    allocation ={key :int (value )for key ,value in exact .items ()}

    remainder =count -sum (allocation .values ())
    if remainder :
        by_fraction =sorted (
        exact ,key =lambda k :(exact [k ]-allocation [k ],str (k )),reverse =True
        )
        for key in by_fraction [:remainder ]:
            allocation [key ]+=1

    pools =[[key ]*n for key ,n in sorted (allocation .items (),key =lambda kv :str (kv [0 ]))if n ]
    out =[]
    while pools :
        for pool in pools :
            out .append (pool .pop ())
        pools =[p for p in pools if p ]
    return out [:count ]


def _amount_for (
base :int ,scale :float ,spread :float ,index :int ,minimum :float |None =None ,maximum :float |None =None
)->int :
    """Deterministic jitter around a class's base amount.

    Mirrors ``batch_seed._amount_for``: a fixed cycle rather than randomness, so
    a rerun of the same scenario prices the same book.
    """
    jitter =1.0 +spread *((index %11 )/10.0 -0.5 )*2.0
    amount =base *scale *jitter
    if minimum is not None :
        amount =max (amount ,minimum *100 )
    if maximum is not None :
        amount =min (amount ,maximum *100 )
    return max (100 ,int (amount ))


def _draw (scenario :Scenario ,index :int )->float :
    """A stable uniform draw in [0, 1) for case ``index``.

    Hashed from the scenario's own shape rather than the run id, so re-running
    the same scenario realises the same book and two runs can be compared. It is
    a draw, not a coin flip at request time - reproducibility is the point.
    """
    seed =f"{scenario .model_dump_json ()}|{index }"
    digest =hashlib .sha256 (seed .encode ()).digest ()
    return int .from_bytes (digest [:8 ],"big")/float (1 <<64 )


def _probability_of (
scenario :Scenario ,failure_class :int ,amount_inr :float ,days_overdue :int ,playbook_override :str |None =None
)->probability .CaseProbability :
    playbook ,channel =probability .features_for_class (failure_class )
    if playbook_override :
        from application .constants import Playbook
        from application .workflow .workflow_nodes import _PLAYBOOK_ACTION

        try :
            selected =Playbook (playbook_override )
            _action ,selected_channel =_PLAYBOOK_ACTION [selected]
            playbook =selected .value
            channel =selected_channel .value if selected_channel else None
        except (ValueError ,KeyError ):
            pass
    edges =scenario .edge_cases

    # Ask the same rule functions the engine will ask. If a bound is already
    # spent the case is not merely less likely, it is not going to be worked.
    blocked =None
    if channel is None and retry_cap_exceeded (edges .retries_already_used ):
        blocked =f"RBI retry cap ({RBI_MAX_RETRIES } of {RBI_MAX_RETRIES } used)"
    elif channel =="VOICE"and voice_attempts_exhausted (edges .voice_attempts_used ):
        blocked =f"Voice attempt cap ({VOICE_ATTEMPT_CAP } of {VOICE_ATTEMPT_CAP } used)"

    return probability .estimate (
    probability .CaseFeatures (
    failure_class =failure_class ,
    playbook =playbook ,
    channel =channel ,
    amount_inr =amount_inr ,
    in_quiet_hours =channel is not None and is_within_quiet_hours (edges .clock ()),
    retries_used =edges .retries_already_used ,
    days_overdue =days_overdue ,
    channel_retried =edges .voice_attempts_used >0 ,
    blocked_by =blocked ,
    )
    )


def plan (scenario :Scenario ,run_id :str )->list [PlannedCase ]:
    """Expand a scenario into the concrete cases the run will execute.

    Whether a customer actually pays is *drawn against the model*, not implied by
    what they said. A cooperative reply raises the odds; it does not guarantee
    settlement. If the reply decided the outcome, the recovered figure would be
    something the scenario asserted rather than something the run produced -
    which is the pre-computed number this whole screen exists to get away from.
    """
    shape =scenario .cases
    edges =scenario .edge_cases

    classes =_weighted_cycle (shape .class_mix ,shape .count )
    replies =_weighted_cycle (edges .reply_mix ,shape .count )

    total_count =len (scenario .custom_cases )+shape .count
    late_cutoff =total_count *edges .late_settlement_pct /100
    cross_cutoff =late_cutoff +total_count *edges .cross_device_pct /100

    planned =[]
    for index ,custom in enumerate (scenario .custom_cases ):
        failure_class =custom .failure_class
        profile =class_profile (failure_class )
        amount_minor =int (round (custom .amount_inr *100 ))
        days_overdue =custom .days_overdue
        reply =custom .reply
        reply_text =custom .reply_text
        effective_playbook =custom .playbook
        estimate =_probability_of (
        scenario ,failure_class ,round (amount_minor /100 ,2 ),days_overdue ,effective_playbook
        )
        message =reply_text if reply_text is not None else edges .reply_texts .get (reply ) or _REPLY_TEXT .get (reply )
        stops_early =bool (message and screen_user_message (message ).disposition )
        outcome_event =custom .outcome_event
        if outcome_event is None and not stops_early :
            outcome_event ="payment.captured"if _draw (scenario ,index )<estimate .p else None
        if custom .outcome_event is None and index <late_cutoff :
            outcome_event ="payment.authorized"
        elif custom .outcome_event is None and index <cross_cutoff :
            outcome_event ="payment.captured"
        planned .append (
        PlannedCase (
        transaction_id =f"sim_{run_id [:8 ]}_custom_{index :04d}",
        failure_class =failure_class ,
        amount_minor =amount_minor ,
        customer_name =custom .customer_name ,
        reply =reply ,
        reply_text =reply_text ,
        retries_used =custom .retries_used ,
        voice_attempts =custom .voice_attempts ,
        outcome_event =outcome_event ,
        days_overdue =days_overdue ,
        probability =estimate ,
        playbook =effective_playbook ,
        )
        )

    for generated_index ,(failure_class ,reply )in enumerate (zip (classes ,replies )):
        index =len (scenario .custom_cases )+generated_index
        failure_class =int (failure_class)
        profile =class_profile (failure_class )
        amount_minor =_amount_for (
        profile ["base_amount"],shape .amount_scale ,shape .amount_spread ,generated_index ,
        shape .amount_min_inr ,shape .amount_max_inr ,
        )
        days_overdue =edges .days_overdue if failure_class ==4 else 0
        reply_text =edges .reply_texts .get (reply )
        estimate =_probability_of (
        scenario ,failure_class ,round (amount_minor /100 ,2 ),days_overdue
        )
        message =reply_text if reply_text is not None else _REPLY_TEXT .get (reply )
        stops_early =bool (message and screen_user_message (message ).disposition )
        if index <late_cutoff :
            outcome_event ="payment.authorized"
        elif index <cross_cutoff :
            outcome_event ="payment.captured"
        elif stops_early :
            outcome_event =None
        else :
            outcome_event ="payment.captured"if _draw (scenario ,index )<estimate .p else None
        planned .append (
        PlannedCase (
        transaction_id =f"sim_{run_id [:8 ]}_generated_{generated_index :04d}",
        failure_class =failure_class ,
        amount_minor =amount_minor ,
        customer_name =_CUSTOMERS [generated_index %len (_CUSTOMERS )],
        reply =reply ,
        reply_text =reply_text ,
        retries_used =edges .retries_already_used ,
        voice_attempts =edges .voice_attempts_used ,
        outcome_event =outcome_event ,
        days_overdue =days_overdue ,
        probability =estimate ,
        )
        )
    return planned


def to_transaction (case :PlannedCase ,run_id :str )->TransactionState :
    """The persisted row for a planned case.

    ``simulation_run_id`` in the metadata is what keeps this out of the
    merchant's real numbers - see ``compute_metrics`` and ``list_transactions``.
    """
    profile =class_profile (case .failure_class )
    if case .customer_name in _CUSTOMERS :
        who =_CUSTOMERS .index (case .customer_name )
    else :
        digest =hashlib .sha256 (case .customer_name .encode ()).digest ()
        who =int .from_bytes (digest [:4 ],"big")%len (_CONTACTS )

    return TransactionState (
    transaction_id =case .transaction_id ,
    razorpay_payment_id =f"pay_sim_{hashlib .sha256 (case .transaction_id .encode ()).hexdigest ()[:10 ]}",
    failure_class =case .failure_class ,
    current_state =TransactionLifecycleState .PENDING ,
    retry_count =case .retries_used ,
    merchant_id ="merch_sim",
    customer_contact =_CONTACTS [who ],
    amount_minor =case .amount_minor ,
    currency ="INR",
    metadata_json ={
    "simulation_run_id":run_id ,
    "archetype":f"CLASS_{case .failure_class }",
    "class_label":profile ["label"],
    "is_at_risk":True ,
    "confidence":profile ["confidence"],
    "event_type":profile ["event_type"],
    "error_code":profile ["error_code"],
    "customer_name":case .customer_name ,
    "ai_tag":"SIMULATED_CASE",
    "reply_kind":case .reply ,
    "days_overdue":case .days_overdue ,
    },
    )


def initial_state (case :PlannedCase ,clock :datetime )->dict :
    """The RecoveryState the graph is invoked with."""
    profile =class_profile (case .failure_class )
    return {
    "transaction_id":case .transaction_id ,
    "failure_class":case .failure_class ,
    "telemetry":{
    "event_type":profile ["event_type"],
    "error_code":profile ["error_code"],
    },
    "user_message":case .user_message ,
    "retry_count":case .retries_used ,
    "voice_attempts":case .voice_attempts ,
    "outcome_event":case .outcome_event ,
    "playbook":case .playbook ,
    "now_ist":clock ,
    }


def _quiet_evening (day :int =4 )->datetime :
    return datetime (2026 ,3 ,day ,21 ,40 ,tzinfo =IST )


def _business_hours (day :int =4 )->datetime :
    return datetime (2026 ,3 ,day ,11 ,0 ,tzinfo =IST )


# One-click demo scenarios. Each one is chosen to make a *different* guardrail
# visible, so clicking through them tells the whole compliance story without
# anyone having to fill in a form.
SAMPLE_SCENARIOS :dict [str ,Scenario ]={
"month_end_crunch":Scenario (
name ="Month-end mandate crunch",
description =(
"Subscription auto-debits failing on month-end low balance, worked at "
"21:40 IST. Watch TRAI quiet hours defer every outbound channel while "
"the salary-window retry still goes ahead."
),
cases =CaseShape (count =200 ,class_mix ={3 :6.0 ,1 :2.0 ,2 :2.0 },amount_scale =1.0 ),
edge_cases =EdgeCases (
reply_mix ={"cooperative":6.0 ,"silent":3.0 ,"opt_out":1.0 },
retries_already_used =1 ,
clock_ist =_quiet_evening (),
),
),
"receivables_chase":Scenario (
name ="Receivables chase",
description =(
"An aged B2B book chased for promise-to-pay dates. Disputes freeze "
"automation and hand the case to a human, which is the guardrail working."
),
cases =CaseShape (count =150 ,class_mix ={4 :8.0 ,2 :1.0 },amount_scale =1.0 ),
edge_cases =EdgeCases (
reply_mix ={"p2p":5.0 ,"dispute":3.0 ,"silent":2.0 },
clock_ist =_business_hours (),
days_overdue =62 ,
),
),
"tight_policy":Scenario (
name ="Mixed book, tight policy",
description =(
"A full mix of failures with the discount cap dropped to zero and voice "
"switched off. Every action the engine wants to take that the policy "
"forbids escalates to a human instead of going out."
),
cases =CaseShape (count =200 ,class_mix ={1 :1.0 ,2 :1.0 ,3 :1.0 ,4 :1.0 }),
edge_cases =EdgeCases (
reply_mix ={"cooperative":6.0 ,"p2p":2.0 ,"opt_out":1.0 ,"dispute":1.0 },
clock_ist =_business_hours (),
),
policy =PolicyOverrides (
max_discount_pct =0 ,
allowed_channels =[
InterventionChannel .WHATSAPP .value ,
InterventionChannel .PAYMENT_LINK .value ,
],
),
),
"retry_exhausted":Scenario (
name ="Retry budget exhausted",
description =(
"Mandates that have already used all three RBI-permitted auto-debit "
"retries. The engine stops itself rather than attempting a fourth."
),
cases =CaseShape (count =120 ,class_mix ={3 :9.0 ,1 :1.0 }),
edge_cases =EdgeCases (
reply_mix ={"cooperative":5.0 ,"silent":5.0 },
retries_already_used =3 ,
clock_ist =_business_hours (),
),
),
}
