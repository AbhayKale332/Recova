"""Database-backed repository for the operator-editable merchant policy."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy .orm import Session

from application .constants import InterventionAction ,InterventionChannel
from application .entities import MerchantPolicy
from application .operations .policy_guard import PolicySandbox

_DEFAULTS_PATH =Path (__file__ ).resolve ().parent .parent /"configuration"/"merchant_rules.json"

_ALLOWED_ACTIONS ={a .value for a in InterventionAction }
_ALLOWED_CHANNELS ={c .value for c in InterventionChannel }


class PolicyValidationError (ValueError ):
    """A proposed policy edit is out of range or references an unknown value."""


def _defaults ()->dict :
    with _DEFAULTS_PATH .open ()as fh :
        policy =json .load (fh )
    policy .pop ("_comment",None )
    return policy


def _row (db :Session )->MerchantPolicy :
    row =db .get (MerchantPolicy ,1 )
    if row is None :
        d =_defaults ()
        row =MerchantPolicy (
        id =1 ,
        max_discount_pct =d ["max_discount_pct"],
        max_intervention_amount_minor =d ["max_intervention_amount_minor"],
        allowed_actions =d ["allowed_actions"],
        allowed_channels =d ["allowed_channels"],
        )
        db .add (row )
        db .commit ()
        db .refresh (row )
    return row


def get_policy (db :Session )->dict :
    return _row (db ).as_dict ()


def sandbox_for (db :Session )->PolicySandbox :
    """A PolicySandbox built from the current (possibly edited) policy."""
    return PolicySandbox (get_policy (db ))


def update_policy (db :Session ,patch :dict )->dict :
    row =_row (db )

    if (v :=patch .get ("max_discount_pct"))is not None :
        if not (0 <=int (v )<=100 ):
            raise PolicyValidationError ("max_discount_pct must be between 0 and 100.")
        row .max_discount_pct =int (v )

    if (v :=patch .get ("max_intervention_amount_minor"))is not None :
        if int (v )<0 :
            raise PolicyValidationError ("max_intervention_amount_minor must be >= 0.")
        row .max_intervention_amount_minor =int (v )

    if (v :=patch .get ("allowed_actions"))is not None :
        unknown =set (v )-_ALLOWED_ACTIONS
        if unknown :
            raise PolicyValidationError (f"Unknown actions: {sorted (unknown )}.")
        row .allowed_actions =list (v )

    if (v :=patch .get ("allowed_channels"))is not None :
        unknown =set (v )-_ALLOWED_CHANNELS
        if unknown :
            raise PolicyValidationError (f"Unknown channels: {sorted (unknown )}.")
        row .allowed_channels =list (v )

    db .commit ()
    db .refresh (row )
    return row .as_dict ()
