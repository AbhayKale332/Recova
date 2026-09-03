"""SSE demo-stream endpoint.

Uses the offline orchestrator override from conftest (fake diagnosis + simulated
dispatch), so these run without network or live credentials.
"""

from application .entities import TransactionState


def test_stream_emits_lifecycle_events (client ,db_session ):
    resp =client .get ("/api/v1/stream/demo/1")
    assert resp .status_code ==200
    assert "text/event-stream"in resp .headers ["content-type"]

    body =resp .text

    assert "event: start"in body
    assert "event: audit"in body
    assert "DIAGNOSE"in body
    assert "EXECUTE_INTERVENTION"in body
    assert "event: complete"in body
    assert "grrr"in body


def test_stream_persists_a_recovered_demo_transaction (client ,db_session ):
    client .get ("/api/v1/stream/demo/1")
    txns =db_session .query (TransactionState ).filter (
    TransactionState .transaction_id .like ("demo_1_%")
    ).all ()
    assert len (txns )==1

    assert txns [0 ].current_state .value =="RECOVERED"


def test_invalid_class_is_rejected (client ):
    resp =client .get ("/api/v1/stream/demo/9")
    assert resp .status_code ==404
