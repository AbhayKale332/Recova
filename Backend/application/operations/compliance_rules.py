"""Deterministic opt-out, dispute, retry, quiet-hours, and voice-attempt safeguards."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from application .constants import StoppingRule


RBI_MAX_RETRIES =3
VOICE_ATTEMPT_CAP =2
QUIET_HOURS_START =20
QUIET_HOURS_END =9

Disposition =Literal ["CONTINUE","TERMINATE","ESCALATE"]



_CANCEL_PHRASES =(
"cancel my plan",
"cancel the plan",
"cancel my subscription",
"cancel subscription",
"cancel karo",
"plan cancel",
)
_OPT_OUT_PHRASES =(
"stop",
"unsubscribe",
"opt out",
"opt-out",
"do not contact",
"don't contact",
"leave me alone",
"remove me",
"band karo",
"band kar do",
"mat bhejo",
"rok do",
)
_DISPUTE_PHRASES =(
"dispute",
"wrong invoice",
"wrong amount",
"incorrect invoice",
"incorrect line item",
"wrong line item",
"didn't order",
"did not order",
"not ordered",
"galat invoice",
)


@dataclass
class MessageVerdict :
    disposition :Disposition
    rule :StoppingRule |None
    reason :str


def screen_user_message (text :str )->MessageVerdict :
    """Classify an inbound user message for stopping intent.

    Precedence: an explicit cancel/opt-out wins over a dispute, because ceasing
    contact is the stronger, safer instruction to honour immediately.
    """
    haystack =(text or "").lower ()

    if any (phrase in haystack for phrase in _CANCEL_PHRASES ):
        return MessageVerdict ("TERMINATE",StoppingRule .EXPLICIT_CANCEL ,"User asked to cancel the plan.")

    if any (phrase in haystack for phrase in _OPT_OUT_PHRASES ):
        return MessageVerdict ("TERMINATE",StoppingRule .OPT_OUT ,"User opted out of further contact.")

    if any (phrase in haystack for phrase in _DISPUTE_PHRASES ):
        return MessageVerdict ("ESCALATE",StoppingRule .DISPUTE_FREEZE ,"User raised a dispute.")

    return MessageVerdict ("CONTINUE",None ,"No stopping intent detected.")


def retry_cap_exceeded (retry_count :int ,max_retries :int =RBI_MAX_RETRIES )->bool :
    """True once the RBI per-cycle auto-debit retry limit is reached."""
    return retry_count >=max_retries


def voice_attempts_exhausted (attempts :int ,cap :int =VOICE_ATTEMPT_CAP )->bool :
    """True once the voice-attempt cap for the rolling window is reached."""
    return attempts >=cap


def is_within_quiet_hours (dt_ist :datetime )->bool :
    """True if the given IST wall-clock time falls in the 20:00-09:00 quiet window.

    Outbound voice/messaging is prohibited in this window (TRAI). The caller is
    expected to pass IST local time; contact is deferred, not dropped.
    """
    hour =dt_ist .hour
    return hour >=QUIET_HOURS_START or hour <QUIET_HOURS_END
