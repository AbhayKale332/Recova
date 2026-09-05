"""Interactive live-session API contract tests."""

import json
import threading
import time

from application.operations import agent_tools
from application.operations.model_router import RoutedResult, explain_route
from application.operations.live_session import get_session


def _case(name="Asha Rao"):
    # Kept under the merchant policy's ₹10,000 intervention ceiling so the
    # opening's GENERATE_PAYMENT_LINK is not refused — these tests exercise
    # reply-time behaviour (opt-out, dispute, converse), not the ceiling
    # refusal itself (that is test_policy_guard's job, at ₹48,000).
    return {
        "customer_name": name,
        "amount_inr": 4_000,
        "failure_class": 1,
    }


def _events_from_sse(body):
    events = []
    for block in body.split("\n\n"):
        lines = block.splitlines()
        name = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if name and data:
            events.append((name, json.loads(data)))
    return events


def test_custom_session_is_simulated_and_does_not_change_metrics(client):
    before = client.get("/api/v1/metrics").json()
    response = client.post("/api/v1/live/sessions", json={"custom_case": _case()})
    assert response.status_code == 201
    transaction_id = response.json()["transaction_id"]

    txn = client.get(f"/api/v1/transactions/{transaction_id}").json()
    assert txn["amount_inr"] == 4_000
    assert txn["archetype"] == "CLASS_1"
    assert txn["class_label"] == "Issuer / Network Timeout"
    assert txn["status"] == "PENDING"
    assert client.get("/api/v1/metrics").json() == before


def test_custom_case_clock_ist_pins_the_session_quiet_hours_state(client):
    # Frozen for the whole session so a demo can deliberately show TRAI quiet
    # hours instead of depending on when the suite happens to run.
    case = _case()
    case["clock_ist"] = "21:40"
    created = client.post("/api/v1/live/sessions", json={"custom_case": case}).json()
    client.post(
        f"/api/v1/live/sessions/{created['session_id']}/reply",
        json={"text": "band karo"},
    )
    stream = client.get(f"/api/v1/live/sessions/{created['session_id']}/stream")
    events = _events_from_sse(stream.text)
    bounds = next(data for name, data in events if name == "bounds")
    assert bounds["inQuietHours"] is True
    assert bounds["armedRule"] == "TRAI_QUIET_HOURS"


def test_opt_out_is_screened_before_any_model_call(client, monkeypatch):
    calls = []

    def must_not_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("the model must not see an opt-out")

    monkeypatch.setattr(agent_tools.router, "call", must_not_call)
    created = client.post("/api/v1/live/sessions", json={"custom_case": _case()}).json()
    response = client.post(
        f"/api/v1/live/sessions/{created['session_id']}/reply",
        json={"text": "band karo"},
    )
    assert response.status_code == 200
    assert response.json()["final_state"] == "CANCELLED"
    assert calls == []

    # The durable audit payload is exposed by the transaction endpoint.
    detail = client.get(f"/api/v1/transactions/{created['transaction_id']}").json()
    assert any(a["payload"].get("stopping_rule") == "OPT_OUT" for a in detail["audit_trail"])


def test_dispute_is_escalated_without_model(client, monkeypatch):
    monkeypatch.setattr(agent_tools.router, "call", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no model")))
    created = client.post("/api/v1/live/sessions", json={"custom_case": _case()}).json()
    response = client.post(
        f"/api/v1/live/sessions/{created['session_id']}/reply",
        json={"text": "this is a wrong invoice"},
    )
    assert response.json()["final_state"] == "ESCALATED"
    detail = client.get(f"/api/v1/transactions/{created['transaction_id']}").json()
    assert any(a["payload"].get("stopping_rule") == "DISPUTE_FREEZE" for a in detail["audit_trail"])


def test_continue_has_converse_route_then_one_decision(client, monkeypatch):
    class FakeRouter:
        def __init__(self):
            self.calls = []

        def call(self, task, prompt, **kwargs):
            self.calls.append(task)
            route = explain_route(task, **kwargs)
            if task == "CONVERSE":
                return RoutedResult("Thanks, I can help with that.", route)
            return RoutedResult(json.dumps({"tool": "SEND_WHATSAPP", "reason": "Continue on WhatsApp."}), route)

    fake = FakeRouter()
    monkeypatch.setattr(agent_tools, "router", fake)
    created = client.post("/api/v1/live/sessions", json={"custom_case": _case()}).json()
    response = client.post(
        f"/api/v1/live/sessions/{created['session_id']}/reply",
        json={"text": "I will check this payment"},
    )
    assert response.status_code == 200
    assert fake.calls == ["CONVERSE", "DECIDE"]
    session = get_session(created["session_id"])
    queued = []
    while not session.queue.empty():
        item = session.queue.get_nowait()
        if item is not None:
            queued.append(item)
    continue_routes = [data["task"] for event, data in queued if event == "route"]
    assert "CONVERSE" in continue_routes
    assert any(event == "decision" and data["tool"] == "SEND_WHATSAPP" for event, data in queued)


def test_sse_event_names_are_ordered_and_delete_closes_session(client):
    created = client.post("/api/v1/live/sessions", json={"custom_case": _case()}).json()
    client.post(
        f"/api/v1/live/sessions/{created['session_id']}/reply",
        json={"text": "band karo"},
    )
    stream = client.get(f"/api/v1/live/sessions/{created['session_id']}/stream")
    events = _events_from_sse(stream.text)
    names = [name for name, _data in events]
    assert names[0] == "start"
    assert names.index("diagnosis") < names.index("decision") < names.index("complete")
    assert {"step", "typing", "message", "bounds", "status", "complete"}.issubset(names)
    # The seeded opening is not a provider call, so it must not claim a route.
    assert "route" not in names

    deleted = client.delete(f"/api/v1/live/sessions/{created['session_id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/live/sessions/{created['session_id']}/stream").status_code == 404


def test_delete_signals_an_open_sse_stream(client):
    created = client.post("/api/v1/live/sessions", json={"custom_case": _case()}).json()
    result = {}

    def consume():
        with client.stream("GET", f"/api/v1/live/sessions/{created['session_id']}/stream") as response:
            result["status"] = response.status_code
            result["body"] = response.read()

    thread = threading.Thread(target=consume)
    thread.start()
    time.sleep(0.1)
    assert client.delete(f"/api/v1/live/sessions/{created['session_id']}").status_code == 200
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert result["status"] == 200
    transaction_id = created["transaction_id"]
    assert client.get(f"/api/v1/transactions/{transaction_id}").json()["audit_trail"]


def test_deleted_session_audit_trail_still_readable(client):
    # DELETE ends the in-process session only; it must never bulk-delete the
    # AuditTrail rows that are the theatre's evidence (live_session.close()).
    # `reply()` calls `start()` itself, so this needs no open SSE stream.
    created = client.post("/api/v1/live/sessions", json={"custom_case": _case()}).json()
    client.post(f"/api/v1/live/sessions/{created['session_id']}/reply", json={"text": "band karo"})

    before = client.get(f"/api/v1/transactions/{created['transaction_id']}").json()
    assert before["audit_trail"]

    assert client.delete(f"/api/v1/live/sessions/{created['session_id']}").status_code == 200

    after = client.get(f"/api/v1/transactions/{created['transaction_id']}").json()
    assert after["audit_trail"]
    assert len(after["audit_trail"]) == len(before["audit_trail"])


def test_unknown_transaction_cannot_start_live_session(client):
    response = client.post("/api/v1/live/sessions", json={"transaction_id": "missing-txn"})
    assert response.status_code == 404
