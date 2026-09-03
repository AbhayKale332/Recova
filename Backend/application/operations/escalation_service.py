"""Service for creating and recording human-handoff queue entries."""

from sqlalchemy .orm import Session

from application .constants import StoppingRule
from application .entities import EscalationQueue


def enqueue_escalation (
db :Session ,
*,
transaction_id :str ,
reason :str ,
rule :StoppingRule |None =None ,
)->EscalationQueue :
    ticket =EscalationQueue (
    transaction_id =transaction_id ,
    reason =reason ,
    rule =rule ,
    )
    db .add (ticket )
    db .commit ()
    db .refresh (ticket )
    return ticket
