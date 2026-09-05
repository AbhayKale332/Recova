"""Small, side-effect-free helpers shared across backend modules."""

from datetime import date ,datetime ,timedelta ,timezone


# IST is UTC+5:30 with no DST, so a fixed offset is exact. Mirrors IST_OFFSET_MINUTES
# in Frontend/src/lib/bounds.ts.
IST =timezone (timedelta (hours =5 ,minutes =30 ))


def utcnow ()->datetime :
    """Timezone-aware current UTC timestamp.

    Centralised so every model uses the same source. Paired with
    ``DateTime(timezone=True)`` columns to keep timestamps unambiguous even
    though SQLite stores them without an offset during local development.
    """
    return datetime .now (timezone .utc )


def now_ist ()->datetime :
    """Current IST wall-clock time.

    The compliance rules are written against Indian local time (TRAI quiet
    hours), so anything asking "may we contact this customer right now?" reads
    the clock through here.
    """
    return datetime .now (IST )


def resolve_clock_ist (hhmm :str |None ,*,reference :datetime |None =None )->datetime |None :
    """Combine an authored ``"HH:MM"`` time-of-day with a reference IST date.

    Lets an operator-authored case pin the wall clock a compliance gate reads
    (e.g. to demo TRAI quiet hours) by choosing a time of day rather than a raw
    datetime - the date always comes from ``reference`` (or the real "now"), so
    the same authored case still reads as "today" whenever it is actually run.
    Returns ``None`` for anything absent or unparseable, so callers can fall
    back to their own default clock without a special case.
    """
    if not hhmm :
        return None
    try :
        hour_str ,minute_str =hhmm .split (":",1 )
        hour ,minute =int (hour_str ),int (minute_str )
    except (ValueError ,AttributeError ):
        return None
    if not (0 <=hour <=23 and 0 <=minute <=59 ):
        return None
    base =(reference or now_ist ()).astimezone (IST )
    return base .replace (hour =hour ,minute =minute ,second =0 ,microsecond =0 )


def next_quiet_hours_end (moment :datetime )->datetime :
    """The next 09:00 IST at or after ``moment``.

    Quiet hours defer contact; they never cancel it. This is the instant the
    agent may act again, and it is what the bounds gauge renders as
    "next action". Mirrors ``nextQuietHoursEnd`` in Frontend/src/lib/bounds.ts.
    """
    from application .operations .compliance_rules import QUIET_HOURS_END

    ist =moment .astimezone (IST )if moment .tzinfo else moment .replace (tzinfo =IST )
    target =ist .replace (hour =QUIET_HOURS_END ,minute =0 ,second =0 ,microsecond =0 )
    if target <=ist :
        target +=timedelta (days =1 )
    return target


def next_salary_window (today :date )->str :
    """Return next universal salary-credit date (1st of applicable month)."""
    if today .day <=5 :
        return today .replace (day =1 ).isoformat ()
    year =today .year +(today .month ==12 )
    month =1 if today .month ==12 else today .month +1
    return date (year ,month ,1 ).isoformat ()
