"""Persistence model for inbound and outbound transaction conversation messages."""

from sqlalchemy import (
Column ,
DateTime ,
Enum ,
ForeignKey ,
Integer ,
JSON ,
String ,
Text ,
)

from application .persistence import Base
from application .constants import (
InterventionChannel ,
MessageDirection ,
MessageSender ,
MessageStatus ,
)
from application .helpers import utcnow


class Message (Base ):
    """One message in a transaction's WhatsApp thread.

    Both the seeded recovery history and any operator- or AI-composed messages
    land here, so the phone mockup renders the complete, ordered conversation.
    ``seq`` gives a stable order independent of timestamp granularity.
    """

    __tablename__ ="messages"

    id =Column (Integer ,primary_key =True ,index =True )
    transaction_id =Column (
    String (64 ),
    ForeignKey ("transaction_states.transaction_id"),
    index =True ,
    nullable =False ,
    )
    channel =Column (
    Enum (InterventionChannel ,validate_strings =True ),
    default =InterventionChannel .WHATSAPP ,
    nullable =False ,
    )
    direction =Column (Enum (MessageDirection ,validate_strings =True ),nullable =False )
    sender =Column (Enum (MessageSender ,validate_strings =True ),nullable =False )
    body =Column (Text ,nullable =False )
    status =Column (
    Enum (MessageStatus ,validate_strings =True ),
    default =MessageStatus .SENT ,
    nullable =False ,
    )
    seq =Column (Integer ,nullable =False )
    meta_json =Column (JSON ,nullable =True )
    created_at =Column (DateTime (timezone =True ),default =utcnow ,nullable =False )
