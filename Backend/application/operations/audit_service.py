"""Single writer for append-only audit records."""

import uuid
from typing import Any

from sqlalchemy .orm import Session

from application .constants import ActionType ,NodeName ,Outcome
from application .entities import AuditTrail


def record_audit (
db :Session ,
*,
transaction_id :str ,
node_name :NodeName ,
action_type :ActionType ,
payload :dict [str ,Any ],
outcome :Outcome ,
event_id :str |None =None ,
)->AuditTrail :
    """Append one entry to the audit trail and return it.

    ``event_id`` is unique per audit row. It defaults to a generated UUID so
    callers don't have to invent one for every transition; a caller may still
    pass an explicit id (e.g. to tie an entry to a specific webhook delivery).
    """
    entry =AuditTrail (
    event_id =event_id or f"aud_{uuid .uuid4 ().hex }",
    transaction_id =transaction_id ,
    node_name =node_name ,
    action_type =action_type ,
    payload =payload ,
    outcome =outcome ,
    )
    db .add (entry )
    db .commit ()
    db .refresh (entry )
    return entry
