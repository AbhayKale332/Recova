"""Shared test fixtures.

Each test gets an isolated in-memory SQLite database via a ``get_db`` override,
so tests never touch the real ``recovery_engine.db``.
"""

from datetime import datetime

import pytest
from fastapi .testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy .orm import sessionmaker
from sqlalchemy .pool import StaticPool

from application .helpers import IST
from application .persistence import Base ,get_db
from application .server import app
from application import entities as _models


# A fixed weekday mid-morning in IST. Pinned so the TRAI quiet-hours gate is not
# armed during the suite: a test asserting "policy blocks this discount" must not
# start failing at 20:00 because the engine correctly deferred contact instead.
# Tests that want the gate armed pass their own clock.
BUSINESS_HOURS_IST =datetime (2026 ,3 ,4 ,11 ,0 ,tzinfo =IST )


def fixed_clock (moment :datetime =BUSINESS_HOURS_IST ):
    """A ``deps.clock`` that always reports ``moment``."""
    return lambda :moment


class _FakeDiagnosis :
    """Offline diagnosis engine for tests: picks the deterministic per-class
    default playbook, so webhook orchestration never calls the live model."""

    def diagnose (self ,*,failure_class ,telemetry =None ,user_message =None ):
        from application .operations .diagnosis_service import Diagnosis ,_DEFAULT_PLAYBOOK

        return Diagnosis (root_cause ="TEST",recommended_playbook =_DEFAULT_PLAYBOOK [failure_class ])


# The per-day API cap is global state keyed on the real SQLite file; disable it
# for the whole suite so request-heavy test modules don't exhaust the quota.
@pytest .fixture (autouse =True )
def rate_limit_disabled ():
    from application .settings import settings

    original =settings .rate_limit_enabled
    settings .rate_limit_enabled =False
    try :
        yield
    finally :
        settings .rate_limit_enabled =original


# Tests use an isolated in-memory database so they never mutate the runtime SQLite file.
@pytest .fixture ()
def db_session ():


    engine =create_engine (
    "sqlite://",
    connect_args ={"check_same_thread":False },
    poolclass =StaticPool ,
    )
    Base .metadata .create_all (bind =engine )
    TestingSessionLocal =sessionmaker (autocommit =False ,autoflush =False ,bind =engine )
    session =TestingSessionLocal ()
    try :
        yield session
    finally :
        session .close ()
        Base .metadata .drop_all (bind =engine )


@pytest .fixture ()
def client (db_session ):
    def override_get_db ():
        try :
            yield db_session
        finally :
            pass

    def override_orchestrator_deps ():
        from application .integrations .routing_dispatcher import build_dispatcher
        from application .workflow .recovery_graph import OrchestratorDeps
        from application .operations .policy_guard import PolicySandbox

        return OrchestratorDeps (
        db =db_session ,
        diagnosis =_FakeDiagnosis (),
        sandbox =PolicySandbox .from_default_policy (),
        dispatch =build_dispatcher (db_session ,live_mode =False ),
        clock =fixed_clock (),
        )

    from application .workflow .workflow_factory import get_orchestrator_deps
    from application .endpoints .assistant_api import get_assistant_generate

    app .dependency_overrides [get_db ]=override_get_db
    app .dependency_overrides [get_orchestrator_deps ]=override_orchestrator_deps

    app .dependency_overrides [get_assistant_generate ]=lambda :None
    with TestClient (app )as test_client :
        yield test_client
    app .dependency_overrides .clear ()
