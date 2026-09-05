"""Model-independent policy gate for validating every proposed recovery action."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from application .constants import InterventionAction ,InterventionChannel




# The amount ceiling applies only to actions that can move funds; reminders do not change balances.
_MONEY_MOVING_ACTIONS =frozenset (
{
InterventionAction .GENERATE_PAYMENT_LINK .value ,
InterventionAction .RETRY_CHARGE .value ,
InterventionAction .OFFER_FEE_WAIVER .value ,
}
)

_DEFAULT_POLICY_PATH =Path (__file__ ).resolve ().parent .parent /"configuration"/"merchant_rules.json"


@dataclass
class ProposedAction :
    """A recovery action awaiting approval.

    ``channel``/``action`` accept the enum or its string value so callers (and
    tests simulating a rogue LLM) can hand in an out-of-range value like "SMS"
    and have the sandbox reject it rather than crash.
    """

    action :InterventionAction |str
    channel :InterventionChannel |str |None =None
    discount_pct :float |None =None
    amount_minor :int |None =None

    @property
    def action_value (self )->str :
        return self .action .value if isinstance (self .action ,InterventionAction )else str (self .action )

    @property
    def channel_value (self )->str |None :
        if self .channel is None :
            return None
        return self .channel .value if isinstance (self .channel ,InterventionChannel )else str (self .channel )


@dataclass
class Decision :
    approved :bool
    reason :str


class PolicySandbox :
    def __init__ (self ,policy :dict [str ,Any ]):
        self ._max_discount_pct =policy .get ("max_discount_pct",0 )
        self ._max_amount_minor =policy .get ("max_intervention_amount_minor")
        self ._allowed_channels =set (policy .get ("allowed_channels",[]))
        self ._allowed_actions =set (policy .get ("allowed_actions",[]))

    @classmethod
    def from_default_policy (cls )->"PolicySandbox":
        with _DEFAULT_POLICY_PATH .open ()as fh :
            return cls (json .load (fh ))

    # Keep this gate deterministic and model-free: every outbound action must pass through it.
    def validate (self ,action :ProposedAction )->Decision :
        if action .action_value not in self ._allowed_actions :
            return Decision (False ,f"Action {action .action_value !r } is not permitted by policy.")

        if action .channel_value is not None and action .channel_value not in self ._allowed_channels :
            return Decision (False ,f"Channel {action .channel_value !r } is not permitted by policy.")

        if action .discount_pct is not None and action .discount_pct >self ._max_discount_pct :
            return Decision (
            False ,
            f"Discount {action .discount_pct }% exceeds the {self ._max_discount_pct }% policy cap.",
            )

        if (
        action .action_value in _MONEY_MOVING_ACTIONS
        and self ._max_amount_minor is not None
        and action .amount_minor is not None
        and action .amount_minor >self ._max_amount_minor
        ):
            return Decision (
            False ,
            f"Amount ₹{action .amount_minor /100 :,.0f} exceeds the ₹{self ._max_amount_minor /100 :,.0f} policy ceiling.",
            )

        return Decision (True ,"Action approved by the configured policy.")
