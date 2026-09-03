"""Persistence models for voice-recovery calls and their transcript turns."""

from sqlalchemy import (
Column ,
DateTime ,
Enum ,
ForeignKey ,
Integer ,
String ,
Text ,
)
from sqlalchemy .orm import relationship

from application .persistence import Base
from application .constants import CallSpeaker ,CallStatus
from application .helpers import utcnow


class CallSession (Base ):
    """A voice-recovery call for a transaction.

    ``provider`` is null while calls are simulated; a live provider (Vapi /
    ElevenLabs / LiveKit) stamps its name once wired. The transcript lives in
    ``CallTurn`` rows so the call interface can replay it turn by turn.
    """

    __tablename__ ="call_sessions"

    id =Column (Integer ,primary_key =True ,index =True )
    transaction_id =Column (
    String (64 ),
    ForeignKey ("transaction_states.transaction_id"),
    index =True ,
    nullable =False ,
    )
    status =Column (
    Enum (CallStatus ,validate_strings =True ),
    default =CallStatus .COMPLETED ,
    nullable =False ,
    )
    duration_sec =Column (Integer ,default =0 ,nullable =False )
    outcome =Column (String (64 ),nullable =True )
    provider =Column (String (32 ),nullable =True )
    started_at =Column (DateTime (timezone =True ),default =utcnow ,nullable =False )
    ended_at =Column (DateTime (timezone =True ),nullable =True )

    turns =relationship ("CallTurn",backref ="call_session",order_by ="CallTurn.seq")


class CallTurn (Base ):
    """One utterance in a call transcript."""

    __tablename__ ="call_turns"

    id =Column (Integer ,primary_key =True ,index =True )
    call_session_id =Column (
    Integer ,ForeignKey ("call_sessions.id"),index =True ,nullable =False
    )
    speaker =Column (Enum (CallSpeaker ,validate_strings =True ),nullable =False )
    text =Column (Text ,nullable =False )
    seq =Column (Integer ,nullable =False )
    at_offset_sec =Column (Integer ,default =0 ,nullable =False )
