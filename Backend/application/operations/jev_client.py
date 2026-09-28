"""Client for Jev, TypeSafe's System One decision model, served by OpenRouter.

Jev reads application state and answers typed questions with probabilities -
never text. Code owns the workflow and every deterministic step; Jev supplies
the judgments code cannot make. Three primitives:

    noul    probability that a condition holds
    choice  one option from a closed set, with a distribution over the set
    score   a probability-weighted position on ordered levels

Every failure - no key, Jev disabled, transport error, non-2xx, a malformed or
mistyped answer - raises ``DecisionUnavailable``. Callers catch it and take
their existing deterministic or LLM path, so Jev being down never changes
behaviour beyond losing the better judgment.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from application.operations.model_router import RouteDecision
from application.settings import settings

logger = logging.getLogger(__name__)


class DecisionUnavailable(RuntimeError):
    """Jev could not answer; the caller must fall back."""


@dataclass(frozen=True)
class Noul:
    p: float


@dataclass(frozen=True)
class Choice:
    choice: str
    probabilities: dict[str, float]
    confidence: float | None


@dataclass(frozen=True)
class Score:
    score: float
    probabilities: dict[str, float]
    confidence: float | None
    legend: dict[str, Any] | None


Answer = Noul | Choice | Score


@dataclass(frozen=True)
class Judgments:
    answers: dict[str, Answer]
    model: str
    latency_ms: float
    cost_usd: float | None = None
    input_tokens: int | None = None
    request_id: str | None = None

    def _get(self, key: str, kind: type) -> Any:
        answer = self.answers.get(key)
        if not isinstance(answer, kind):
            raise DecisionUnavailable(f"Jev answer {key!r} missing or not a {kind.__name__}")
        return answer

    def noul(self, key: str) -> float:
        return self._get(key, Noul).p

    def choice(self, key: str) -> Choice:
        return self._get(key, Choice)

    def score(self, key: str) -> Score:
        return self._get(key, Score)


# ---------------------------------------------------------------- builders


def noul(instructions: Any, *, true: Any = None, false: Any = None) -> dict[str, Any]:
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if true is not None and false is not None:
        question["criteria"] = {"true": true, "false": false}
    return question


def choice(instructions: Any, options: dict[str, Any]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": dict(options)}


def score(instructions: Any, levels: list[Any]) -> dict[str, Any]:
    """``levels`` is ordered lowest first."""
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


# ------------------------------------------------------------------ calls


def _float_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {str(k): float(v) for k, v in value.items() if isinstance(v, (int, float))}


def _opt_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _parse_answer(key: str, expected: str, raw: Any) -> Answer:
    if not isinstance(raw, dict) or raw.get("type") != expected:
        got = raw.get("type") if isinstance(raw, dict) else type(raw).__name__
        raise DecisionUnavailable(f"Jev answer {key!r}: expected {expected}, got {got!r}")
    try:
        if expected == "noul":
            return Noul(p=float(raw["noul"]))
        if expected == "choice":
            return Choice(
                choice=str(raw["choice"]),
                probabilities=_float_map(raw.get("probabilities")),
                confidence=_opt_float(raw.get("confidence")),
            )
        return Score(
            score=float(raw["score"]),
            probabilities=_float_map(raw.get("probabilities")),
            confidence=_opt_float(raw.get("confidence")),
            legend=raw.get("legend") if isinstance(raw.get("legend"), dict) else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionUnavailable(f"Jev answer {key!r} malformed: {exc}") from exc


def decide(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    session_id: str | None = None,
    client: httpx.Client | None = None,
) -> Judgments:
    """Ask Jev every question in one request; they are answered in parallel."""
    if not settings.jev_enabled:
        raise DecisionUnavailable("Jev is disabled (JEV_ENABLED=false)")
    if not settings.open_router:
        raise DecisionUnavailable("OpenRouter key is missing (OPEN_ROUTER)")
    if not questions:
        raise DecisionUnavailable("No questions to ask")

    body: dict[str, Any] = {"model": settings.jev_model, "state": state, "questions": questions}
    if session_id:
        body["session_id"] = session_id
    headers = {"Authorization": f"Bearer {settings.open_router}", "Content-Type": "application/json"}

    started = time.perf_counter()
    try:
        if client is not None:
            response = client.post(settings.jev_url, json=body, headers=headers, timeout=settings.jev_timeout_s)
        else:
            with httpx.Client() as owned:
                response = owned.post(settings.jev_url, json=body, headers=headers, timeout=settings.jev_timeout_s)
    except httpx.HTTPError as exc:
        raise DecisionUnavailable(f"Jev transport error: {type(exc).__name__}") from exc
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    if response.status_code >= 300:
        raise DecisionUnavailable(f"Jev HTTP {response.status_code}: {response.text[:200]}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise DecisionUnavailable("Jev returned a non-JSON body") from exc
    raw_answers = payload.get("answers") if isinstance(payload, dict) else None
    if not isinstance(raw_answers, dict):
        raise DecisionUnavailable("Jev response has no answers")

    answers = {
        key: _parse_answer(key, question["type"], raw_answers.get(key))
        for key, question in questions.items()
    }
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    tokens = usage.get("input_tokens")
    judgments = Judgments(
        answers=answers,
        model=str(payload.get("model") or settings.jev_model),
        latency_ms=latency_ms,
        cost_usd=_opt_float(usage.get("cost")),
        input_tokens=int(tokens) if isinstance(tokens, int) else None,
        request_id=payload.get("id"),
    )
    logger.info(
        "Jev %s answered %s in %.0fms (cost %s)",
        judgments.model,
        ",".join(questions),
        latency_ms,
        judgments.cost_usd,
    )
    return judgments


# ------------------------------------------------------------ presentation


def route_decision_for(task: str, judgments: Judgments, reason: str) -> RouteDecision:
    """Present a Jev call in the router's wire shape so the UI renders it as-is."""
    return RouteDecision(
        task=task,
        tier="system-one",
        provider="openrouter",
        model=judgments.model,
        reason=reason,
        raised_by=[],
        escalated_from=None,
        latency_ms=judgments.latency_ms,
        tokens=judgments.input_tokens,
    )


def summarise(judgments: Judgments) -> dict[str, Any]:
    """Compact, JSON-safe view for audit payloads and the ``judgment`` SSE event."""
    answers: dict[str, Any] = {}
    for key, answer in judgments.answers.items():
        if isinstance(answer, Noul):
            answers[key] = {"type": "noul", "p": answer.p}
        elif isinstance(answer, Choice):
            answers[key] = {
                "type": "choice",
                "choice": answer.choice,
                "probabilities": answer.probabilities,
                "confidence": answer.confidence,
            }
        else:
            answers[key] = {
                "type": "score",
                "score": answer.score,
                "probabilities": answer.probabilities,
                "confidence": answer.confidence,
            }
    return {
        "model": judgments.model,
        "latency_ms": judgments.latency_ms,
        "cost_usd": judgments.cost_usd,
        "answers": answers,
    }
