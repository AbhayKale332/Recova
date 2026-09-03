"""Persistence model used to make inbound webhook processing idempotent."""

from sqlalchemy import Column ,DateTime ,Integer ,String

from application .persistence import Base
from application .helpers import utcnow


class ProcessedEvent (Base ):
    """Idempotency ledger for inbound webhook ``event_id``s.

    Razorpay (like most gateways) retries webhook delivery, so the same
    ``event_id`` can arrive several times. A row here is the durable record that
    an id has been claimed; the unique constraint is what makes the claim atomic
    even under concurrent delivery.
    """

    __tablename__ ="processed_events"

    id =Column (Integer ,primary_key =True ,index =True )
    event_id =Column (String (64 ),unique =True ,index =True ,nullable =False )
    processed_at =Column (DateTime (timezone =True ),default =utcnow ,nullable =False )
