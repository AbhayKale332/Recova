"""Persistence model for the per-day API request counter (global rate limit)."""

from sqlalchemy import Column ,Integer ,String

from application .persistence import Base


class DailyApiUsage (Base ):
    """One row per IST calendar day holding the count of billable API calls.

    The rate-limit middleware increments ``request_count`` with an atomic
    conditional ``UPDATE`` (``WHERE request_count < limit``), so the cap holds
    even under concurrent requests without a read-then-write race. Kept in the
    database rather than in memory so the count survives a process restart
    within a deployment; a new deploy wipes the ephemeral SQLite file and the
    day starts fresh, which is acceptable.
    """

    __tablename__ ="daily_api_usage"

    usage_date =Column (String (10 ),primary_key =True )  # ISO date, IST
    request_count =Column (Integer ,nullable =False ,default =0 )
