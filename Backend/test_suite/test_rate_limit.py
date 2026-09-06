"""The global per-day API request cap enforced by the server middleware."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy .orm import sessionmaker
from sqlalchemy .pool import StaticPool

from application import persistence
from application .persistence import Base
from application .settings import settings


@pytest .fixture ()
def rate_limited (monkeypatch ):
    """Re-arm the cap (the suite disables it) against an isolated counter DB."""
    engine =create_engine (
    "sqlite://",
    connect_args ={"check_same_thread":False },
    poolclass =StaticPool ,
    )
    Base .metadata .create_all (bind =engine )
    monkeypatch .setattr (
    persistence ,"SessionLocal",sessionmaker (bind =engine ,autoflush =False )
    )
    monkeypatch .setattr (settings ,"rate_limit_enabled",True )
    monkeypatch .setattr (settings ,"daily_request_limit",2 )


def test_billable_calls_are_capped_then_429 (client ,rate_limited ):
    assert client .get ("/api/v1/metrics").status_code ==200
    assert client .get ("/api/v1/metrics").status_code ==200

    blocked =client .get ("/api/v1/metrics")
    assert blocked .status_code ==429
    assert "limit" in blocked .json ()["detail"].lower ()
    assert blocked .headers ["X-RateLimit-Remaining"]=="0"
    assert int (blocked .headers ["Retry-After"])>0


def test_health_and_webhooks_are_exempt (client ,rate_limited ):
    for _ in range (5 ):
        assert client .get ("/api/v1/health").status_code ==200

    # The billable budget is still intact after the exempt calls.
    assert client .get ("/api/v1/metrics").status_code ==200
