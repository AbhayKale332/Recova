"""Serialized representation of an immutable audit record."""

from datetime import datetime
from typing import Any ,Dict

from pydantic import BaseModel ,ConfigDict

from application .constants import ActionType ,NodeName ,Outcome


class AuditTrailBase (BaseModel ):
    event_id :str
    transaction_id :str
    node_name :NodeName
    action_type :ActionType
    payload :Dict [str ,Any ]
    outcome :Outcome


class AuditTrailCreate (AuditTrailBase ):
    pass


class AuditTrailResponse (AuditTrailBase ):
    model_config =ConfigDict (from_attributes =True )

    id :int
    timestamp :datetime
