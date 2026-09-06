"""Global per-day API request cap, enforced with an atomic database counter."""

from sqlalchemy import select ,update
from sqlalchemy .exc import IntegrityError
from sqlalchemy .orm import Session

from application .entities .usage_counter import DailyApiUsage
from application .helpers import now_ist


class RateLimitResult :
    """Outcome of one rate-limit check."""

    __slots__ =("allowed","count","limit")

    def __init__ (self ,allowed :bool ,count :int ,limit :int )->None :
        self .allowed =allowed
        self .count =count
        self .limit =limit

    @property
    def remaining (self )->int :
        return max (0 ,self .limit -self .count )


def _today_key ()->str :
    """The IST calendar date the counter is bucketed by."""
    return now_ist ().date ().isoformat ()


def check_and_increment (db :Session ,limit :int )->RateLimitResult :
    """Count one billable request against today's bucket.

    Returns ``allowed=False`` (without incrementing) once the bucket has reached
    ``limit``. The increment is a single conditional ``UPDATE`` so the cap is
    exact even when requests race. A brand-new day inserts a fresh zeroed row;
    the unique primary key arbitrates a concurrent insert.
    """
    today =_today_key ()

    if db .get (DailyApiUsage ,today )is None :
        try :
            db .add (DailyApiUsage (usage_date =today ,request_count =0 ))
            db .commit ()
        except IntegrityError :
            db .rollback ()

    result =db .execute (
    update (DailyApiUsage )
    .where (DailyApiUsage .usage_date ==today ,DailyApiUsage .request_count <limit )
    .values (request_count =DailyApiUsage .request_count +1 )
    )
    db .commit ()

    current =db .execute (
    select (DailyApiUsage .request_count ).where (DailyApiUsage .usage_date ==today )
    ).scalar_one_or_none ()or 0

    if result .rowcount ==0 :
        return RateLimitResult (allowed =False ,count =current ,limit =limit )
    return RateLimitResult (allowed =True ,count =current ,limit =limit )
