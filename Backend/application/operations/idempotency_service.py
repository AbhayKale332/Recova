"""Database-backed claim operation that prevents duplicate webhook processing."""

from sqlalchemy .exc import IntegrityError
from sqlalchemy .orm import Session

from application .entities .handled_event import ProcessedEvent


def claim_event (db :Session ,event_id :str )->bool :
    """Atomically claim an ``event_id``.

    Returns ``True`` if this call is the first to claim the id (caller should
    process the event), ``False`` if it was already claimed (a duplicate/retry
    that must be ignored). The unique constraint does the arbitration, so the
    check-and-set is race-free rather than a read-then-write.
    """
    # The unique database constraint arbitrates concurrent webhook retries without a read-then-write race.
    db .add (ProcessedEvent (event_id =event_id ))
    try :
        db .commit ()
    except IntegrityError :
        db .rollback ()
        return False
    return True
