"""Model-router floors, raisers, failover, escalation, and pure explanations."""

import json

from application.constants import FailureClass
from application.operations.diagnosis_service import DiagnosisEngine
from application.operations.model_router import ModelRouter, explain_route


def test_each_task_uses_documented_floor(monkeypatch):
    monkeypatch.setattr("application.settings.settings.llm_provider", "openai")
    assert explain_route("CLASSIFY").tier == "nano"
    assert explain_route("DRAFT").tier == "nano"
    assert explain_route("DRAFT", live=True).tier == "mini"
    assert explain_route("DIAGNOSE").tier == "mini"
    assert explain_route("CONVERSE").tier == "mini"
    assert explain_route("DECIDE").tier == "full"


def test_stakes_raise_only_above_threshold(monkeypatch):
    monkeypatch.setattr("application.settings.settings.llm_provider", "openai")
    assert explain_route("CLASSIFY", amount_inr=500).tier == "nano"
    raised = explain_route("CLASSIFY", amount_inr=50_000)
    assert raised.tier == "mini"
    assert raised.raised_by == ["stakes"]
    assert "₹50,000 at stake" in raised.reason


def test_last_retry_raises_tier():
    decision = explain_route("CLASSIFY", retries_used=2)
    assert decision.tier == "mini"
    assert decision.raised_by == ["guardrail_proximity"]
    assert "last retry available" in decision.reason


def test_raisers_stack_but_cap_at_full():
    decision = explain_route(
        "DRAFT",
        amount_inr=50_000,
        retries_used=2,
        voice_attempts=1,
        discount_pct=14,
    )
    assert decision.tier == "full"
    assert decision.raised_by == ["stakes", "guardrail_proximity"]


def test_malformed_json_escalates_exactly_once(monkeypatch):
    calls = []

    def fake_openai(prompt, model, *, json_mode):
        calls.append((model, json_mode))
        if len(calls) == 1:
            return "not json", 1
        return json.dumps({"confidence": 0.9, "answer": "ok"}), 2

    monkeypatch.setattr("application.settings.settings.llm_provider", "openai")
    monkeypatch.setattr("application.settings.settings.openai_api_key", "test")
    monkeypatch.setitem(
        __import__("application.operations.model_router", fromlist=["_PROVIDER_REQUESTS"])._PROVIDER_REQUESTS,
        "openai",
        fake_openai,
    )
    result = ModelRouter().call("DIAGNOSE", "prompt")
    assert len(calls) == 2
    assert result.decision.escalated_from == "mini"
    assert result.decision.tier == "full"


def test_openai_429_falls_through_to_gemini(monkeypatch):
    def rate_limited(*_args, **_kwargs):
        raise RuntimeError("429 rate limit")

    def gemini(*_args, **_kwargs):
        return json.dumps({"confidence": 0.9, "answer": "ok"}), 7

    monkeypatch.setattr("application.settings.settings.llm_provider", "openai")
    monkeypatch.setitem(
        __import__("application.operations.model_router", fromlist=["_PROVIDER_REQUESTS"])._PROVIDER_REQUESTS,
        "openai",
        rate_limited,
    )
    monkeypatch.setitem(
        __import__("application.operations.model_router", fromlist=["_PROVIDER_REQUESTS"])._PROVIDER_REQUESTS,
        "gemini",
        gemini,
    )
    result = ModelRouter().call("DIAGNOSE", "prompt")
    assert result.decision.provider == "gemini"
    assert result.decision.tokens == 7
    assert "unavailable" in result.decision.reason


def test_neither_provider_keeps_deterministic_diagnosis_fallback(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("offline")

    module = __import__("application.operations.model_router", fromlist=["_PROVIDER_REQUESTS"])
    monkeypatch.setitem(module._PROVIDER_REQUESTS, "openai", unavailable)
    monkeypatch.setitem(module._PROVIDER_REQUESTS, "gemini", unavailable)
    diagnosis = DiagnosisEngine(router=ModelRouter()).diagnose(
        failure_class=FailureClass.REALTIME_DEGRADATION,
        telemetry={"amount_minor": 500},
    )
    assert diagnosis.recommended_playbook.value == "REROUTE_RAIL"
    assert diagnosis.confidence == 0.0


def test_router_explain_endpoint_makes_no_model_call(client, monkeypatch):
    def must_not_call(*_args, **_kwargs):
        raise AssertionError("the explanation endpoint must not call a provider")

    module = __import__("application.operations.model_router", fromlist=["_PROVIDER_REQUESTS"])
    monkeypatch.setitem(module._PROVIDER_REQUESTS, "openai", must_not_call)
    monkeypatch.setitem(module._PROVIDER_REQUESTS, "gemini", must_not_call)
    response = client.post(
        "/api/v1/router/explain",
        json={"task": "DIAGNOSE", "amount_inr": 50_000},
    )
    assert response.status_code == 200
    assert response.json()["tier"] == "full"
    assert response.json()["provider"] == "openai"


def test_router_explain_uses_the_editable_discount_cap(client, monkeypatch):
    monkeypatch.setitem(
        __import__("application.operations.model_router", fromlist=["_PROVIDER_REQUESTS"])._PROVIDER_REQUESTS,
        "openai",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no model call")),
    )
    assert client.patch("/api/v1/policy", json={"max_discount_pct": 10}).status_code == 200
    near = client.post(
        "/api/v1/router/explain",
        json={"task": "DECIDE", "amount_inr": 500, "discount_pct": 9},
    ).json()
    far = client.post(
        "/api/v1/router/explain",
        json={"task": "DECIDE", "amount_inr": 500, "discount_pct": 7},
    ).json()
    assert near["raised_by"] == ["guardrail_proximity"]
    assert far["raised_by"] == []
