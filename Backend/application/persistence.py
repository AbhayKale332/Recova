"""Database engine and session lifecycle for the recovery backend."""

from sqlalchemy import create_engine ,event
from sqlalchemy .orm import declarative_base ,sessionmaker

from application .settings import settings


# Keep one shared engine so all request handlers use the same database configuration.
engine =create_engine (
settings .database_url ,connect_args ={"check_same_thread":False }
)


@event .listens_for (engine ,"connect")
def _configure_sqlite (dbapi_connection ,_connection_record )->None :
    """Put SQLite in WAL mode so concurrent workers do not deadlock.

    The simulation runner drives many cases at once, one Session per worker
    thread, and every node in the recovery graph commits. SQLite's default
    ``delete`` journal takes an exclusive lock for each write, so those workers
    would serialise and then fail with "database is locked". WAL lets readers
    run alongside a writer, ``busy_timeout`` makes a blocked writer wait rather
    than raise, and ``synchronous=NORMAL`` is the usual companion to WAL - safe
    against process crashes, which is the failure mode that matters here.

    Guarded by a driver check so a future move to Postgres does not break.
    """
    if not settings .database_url .startswith ("sqlite"):
        return

    cursor =dbapi_connection .cursor ()
    try :
        cursor .execute ("PRAGMA journal_mode=WAL")
        cursor .execute ("PRAGMA busy_timeout=5000")
        cursor .execute ("PRAGMA synchronous=NORMAL")
    finally :
        cursor .close ()


SessionLocal =sessionmaker (autocommit =False ,autoflush =False ,bind =engine )

Base =declarative_base ()


def get_db ():
    db =SessionLocal ()
    try :
        yield db
    finally :
        db .close ()


def init_db ()->None :
    """Create tables for all registered models.

    Importing ``application.entities`` ensures every model is registered on ``Base``
    before ``create_all`` runs. This is called explicitly on startup rather
    than as an import side effect. NOTE: ``create_all`` only creates missing
    tables; once the schema stabilises, migrations (Alembic) should own it.
    """
    # Import every entity before create_all so SQLAlchemy sees the complete schema.
    import application .entities

    Base .metadata .create_all (bind =engine )
