"""Append-only audit record for every state transition and recovery action."""

from sqlalchemy import (
Column ,
DateTime ,
Enum ,
ForeignKey ,
Integer ,
JSON ,
String ,
event ,
)
from sqlalchemy .exc import InvalidRequestError

from application .persistence import Base
from application .constants import ActionType ,NodeName ,Outcome
from application .helpers import utcnow


class AuditTrail (Base ):
    """Append-only ledger for workflow decisions and state transitions.

    ORM guards prevent updates and deletes after insertion, preserving a reliable
    audit history for operators, tests, and downstream reporting.
    """

    __tablename__ ="audit_trails"

    id =Column (Integer ,primary_key =True ,index =True )
    event_id =Column (String (64 ),unique =True ,index =True ,nullable =False )
    transaction_id =Column (
    String (64 ),
    ForeignKey ("transaction_states.transaction_id"),
    index =True ,
    nullable =False ,
    )
    timestamp =Column (DateTime (timezone =True ),default =utcnow ,nullable =False )
    node_name =Column (Enum (NodeName ,validate_strings =True ),nullable =False )
    action_type =Column (Enum (ActionType ,validate_strings =True ),nullable =False )
    payload =Column (JSON ,nullable =False )
    outcome =Column (Enum (Outcome ,validate_strings =True ),nullable =False )


@event .listens_for (AuditTrail ,"before_update",propagate =True )
def _block_audit_update (mapper ,connection ,target ):
    raise InvalidRequestError ("AuditTrail rows are append-only and cannot be modified.")


@event .listens_for (AuditTrail ,"before_delete",propagate =True )
def _block_audit_delete (mapper ,connection ,target ):
    raise InvalidRequestError ("AuditTrail rows are append-only and cannot be deleted.")
