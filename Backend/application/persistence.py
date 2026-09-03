"""Database engine and session lifecycle for the recovery backend."""

from sqlalchemy import create_engine
from sqlalchemy .orm import declarative_base ,sessionmaker

from application .settings import settings


# Keep one shared engine so all request handlers use the same database configuration.
engine =create_engine (
settings .database_url ,connect_args ={"check_same_thread":False }
)
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
