"""Small, side-effect-free helpers shared across backend modules."""

from datetime import date ,datetime ,timezone


def utcnow ()->datetime :
    """Timezone-aware current UTC timestamp.

    Centralised so every model uses the same source. Paired with
    ``DateTime(timezone=True)`` columns to keep timestamps unambiguous even
    though SQLite stores them without an offset during local development.
    """
    return datetime .now (timezone .utc )


def next_salary_window (today :date )->str :
    """Return next universal salary-credit date (1st of applicable month)."""
    if today .day <=5 :
        return today .replace (day =1 ).isoformat ()
    year =today .year +(today .month ==12 )
    month =1 if today .month ==12 else today .month +1
    return date (year ,month ,1 ).isoformat ()
