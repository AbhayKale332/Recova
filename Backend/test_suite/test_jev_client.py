"""Jev client: request shape, answer parsing, and every failure mode raising
DecisionUnavailable. No network - httpx.MockTransport stands in for OpenRouter."""

import json

import httpx
import pytest

from application.operations import jev_client
from application.operations.jev_client import (
    Choice,
    DecisionUnavailable,
    Noul,
    Score,
    choice,
    decide,
    noul,
    route_decision_for,
    score,
    summarise,
)
from application.settings import settings

KEY = "sk-or-v1-test-secret-key"

QUESTIONS = {
    "stop": noul("Is the customer asking to stop contact?"),
    "when": choice("When will they pay?", {"tomorrow": "Tomorrow", "not_stated": "Not stated"}),
    "urgency": score("How urgent?", ["Low", "High"]),
}

GOOD = {
    "id": "gen-dec-1",
    "model": "typesafe/jev-1.13-20260917",
    "provider": "TypeSafe",
    "answers": {
        "stop": {"type": "noul", "noul": 0.03},
        "when": {
            "type": "choice",
            "choice": "tomorrow",
            "probabilities": {"tomorrow": 0.9, "not_stated": 0.1},
            "confidence": 0.8,
        },
        "urgency": {
            "type": "score",
            "score": 0.2,
            "legend": {"0": "Low", "1": "High"},
            "probabilities": {"0": 0.8, "1": 0.2},
            "confidence": 0.6,
        },
    },
    "usage": {"input_tokens": 120, "output_tokens": 30, "cost": 0.000005},
}


@pytest.fixture
def jev_on(monkeypatch):
    monkeypatch.setattr(settings, "jev_enabled", True)
    monkeypatch.setattr(settings, "open_router", KEY)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _returning(status=200, body=None, text=None):
    def handler(request):
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=body if body is not None else GOOD)

    return handler


def test_request_shape(jev_on):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=GOOD)

    decide({"reply": "hi"}, QUESTIONS, session_id="s-1", client=_client(handler))
    assert seen["url"] == settings.jev_url
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["body"]["model"] == "typesafe/jev-1.13-20260917"
    assert seen["body"]["state"] == {"reply": "hi"}
    assert seen["body"]["questions"] == QUESTIONS
    assert seen["body"]["session_id"] == "s-1"


def test_session_id_is_optional(jev_on):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=GOOD)

    decide({"reply": "hi"}, QUESTIONS, client=_client(handler))
    assert "session_id" not in seen["body"]


def test_parses_every_primitive(jev_on):
    j = decide({}, QUESTIONS, client=_client(_returning()))
    assert j.model == "typesafe/jev-1.13-20260917"
    assert j.answers["stop"] == Noul(0.03)
    assert j.noul("stop") == 0.03
    assert j.choice("when") == Choice("tomorrow", {"tomorrow": 0.9, "not_stated": 0.1}, 0.8)
    assert isinstance(j.score("urgency"), Score)
    assert j.score("urgency").legend == {"0": "Low", "1": "High"}
    assert j.cost_usd == 0.000005
    assert j.input_tokens == 120
    assert j.request_id == "gen-dec-1"


def test_accessor_of_wrong_type_raises(jev_on):
    j = decide({}, QUESTIONS, client=_client(_returning()))
    with pytest.raises(DecisionUnavailable):
        j.noul("when")


def test_disabled_raises(monkeypatch):
    monkeypatch.setattr(settings, "jev_enabled", False)
    monkeypatch.setattr(settings, "open_router", KEY)
    with pytest.raises(DecisionUnavailable):
        decide({}, QUESTIONS, client=_client(_returning()))


def test_empty_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "jev_enabled", True)
    monkeypatch.setattr(settings, "open_router", "")
    with pytest.raises(DecisionUnavailable):
        decide({}, QUESTIONS, client=_client(_returning()))


@pytest.mark.parametrize("status", [429, 500])
def test_http_errors_raise(jev_on, status):
    with pytest.raises(DecisionUnavailable) as err:
        decide({}, QUESTIONS, client=_client(_returning(status, {"error": "nope"})))
    assert str(status) in str(err.value)
    assert KEY not in str(err.value)


def test_timeout_raises(jev_on):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(DecisionUnavailable) as err:
        decide({}, QUESTIONS, client=_client(handler))
    assert KEY not in str(err.value)


def test_non_json_raises(jev_on):
    with pytest.raises(DecisionUnavailable):
        decide({}, QUESTIONS, client=_client(_returning(text="<html>")))


def test_missing_answer_raises(jev_on):
    body = {**GOOD, "answers": {k: v for k, v in GOOD["answers"].items() if k != "when"}}
    with pytest.raises(DecisionUnavailable):
        decide({}, QUESTIONS, client=_client(_returning(body=body)))


def test_wrong_answer_type_raises(jev_on):
    body = {**GOOD, "answers": {**GOOD["answers"], "stop": {"type": "choice", "choice": "x"}}}
    with pytest.raises(DecisionUnavailable):
        decide({}, QUESTIONS, client=_client(_returning(body=body)))


def test_route_decision_and_summary(jev_on):
    j = decide({}, QUESTIONS, client=_client(_returning()))
    route = route_decision_for("SCREEN", j, "Jev read the reply")
    assert route.provider == "openrouter"
    assert route.model == "typesafe/jev-1.13-20260917"
    assert route.tier == "system-one"
    assert route.tokens == 120
    summary = summarise(j)
    assert summary["answers"]["stop"] == {"type": "noul", "p": 0.03}
    assert summary["answers"]["when"]["choice"] == "tomorrow"
    assert summary["answers"]["urgency"]["type"] == "score"
    json.dumps(summary)


def test_builders():
    assert noul("q") == {"type": "noul", "instructions": "q"}
    assert noul("q", true="a", false="b")["criteria"] == {"true": "a", "false": "b"}
    assert choice("q", {"a": "A"})["criteria"] == {"a": "A"}
    assert score("q", ["lo", "hi"])["criteria"] == ["lo", "hi"]


def test_suite_runs_offline_by_default():
    # The autouse jev_offline fixture: without it the real .env key would be used.
    assert settings.jev_enabled is False
    with pytest.raises(DecisionUnavailable):
        jev_client.decide({}, QUESTIONS)
