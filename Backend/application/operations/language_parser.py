"""Deterministic Hinglish Promise-to-Pay date extraction for the recovery loop."""

from __future__ import annotations

import re
from datetime import date ,timedelta

_MONTH_DAYS =30


def _nth_of_month (n :int ,today :date )->str :
    """The n-th day-of-month at or after today; rolls to next month if passed."""
    year ,month =today .year ,today .month
    if n <today .day :
        month +=1
        if month >12 :
            month ,year =1 ,year +1

    try :
        return date (year ,month ,n ).isoformat ()
    except ValueError :

        return (date (year ,month ,1 )+timedelta (days =_MONTH_DAYS )).replace (day =1 ).isoformat ()


def extract_p2p_date (text :str ,today :date |None =None )->str |None :
    """Resolve a Promise-to-Pay commitment in ``text`` to an ISO date, or None."""
    today =today or date .today ()
    t =(text or "").lower ()
    if not t .strip ():
        return None


    if "parso"in t or "parson"in t :
        return (today +timedelta (days =2 )).isoformat ()
    if "kal"in t :
        return (today +timedelta (days =1 )).isoformat ()
    if "agle hafte"in t or "next week"in t or "agle week"in t :
        return (today +timedelta (days =7 )).isoformat ()


    m =re .search (r"(\d{1,2})\s*(din|days|day)\b",t )
    if m :
        return (today +timedelta (days =int (m .group (1 )))).isoformat ()


    m =re .search (r"(\d{1,2})\s*(tarikh|tareekh|tarik)\b",t )
    if m :
        return _nth_of_month (int (m .group (1 )),today )


    m =re .search (r"\b(\d{1,2})[/-](\d{1,2})\b",t )
    if m :
        day ,month =int (m .group (1 )),int (m .group (2 ))
        year =today .year +(1 if month <today .month else 0 )
        try :
            return date (year ,month ,day ).isoformat ()
        except ValueError :
            return None

    return None
