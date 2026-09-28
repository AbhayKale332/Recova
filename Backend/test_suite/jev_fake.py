"""A stand-in for jev_client.decide: answers whatever questions it is asked,
from a dict of overrides, so call sites can be tested without the network."""

from __future__ import annotations

from typing import Any

from application.operations.jev_client import Choice, DecisionUnavailable, Judgments, Noul, Score

MODEL = "typesafe/jev-1.13-20260917"


def fake_decide(answers: dict[str, Any] | None = None, *, calls: list | None = None, fail: bool = False):
    """``answers`` maps a question key to a float (noul p), a str (choice), or a
    (choice, confidence) tuple. Unlisted nouls answer 0.02; unlisted choices
    pick ``none`` / ``not_stated`` if offered, else the first option."""
    answers = answers or {}

    def decide(state, questions, **_kwargs) -> Judgments:
        if calls is not None:
            calls.append({"state": state, "questions": questions})
        if fail:
            raise DecisionUnavailable("fake outage")
        out = {}
        for key, q in questions.items():
            given = answers.get(key)
            if q["type"] == "noul":
                out[key] = Noul(float(given) if given is not None else 0.02)
            elif q["type"] == "choice":
                options = list(q["criteria"])
                if isinstance(given, tuple):
                    pick, confidence = given
                else:
                    pick = given or next((o for o in ("none", "not_stated") if o in options), options[0])
                    confidence = 0.9
                assert pick in options, f"{key}: {pick!r} not offered in {options}"
                out[key] = Choice(pick, {o: (0.9 if o == pick else 0.1 / max(1, len(options) - 1)) for o in options}, confidence)
            else:
                out[key] = Score(float(given or 0), {}, 0.9, None)
        return Judgments(answers=out, model=MODEL, latency_ms=1.0, cost_usd=0.0, input_tokens=10)

    return decide
