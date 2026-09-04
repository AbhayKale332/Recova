"""Provider/model routing for advisory LLM calls.

The router is deliberately small and explicit.  It owns tier selection and
provider failover; the recovery engine still owns every consequential decision.
Both provider SDKs are imported inside their request functions so a demo can
fall back to the deterministic paths when an optional integration is broken.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, replace
from typing import Callable

from application.settings import settings

logger = logging.getLogger(__name__)

TASKS = {"CLASSIFY", "DRAFT", "DIAGNOSE", "CONVERSE", "DECIDE"}
TIERS = ("nano", "mini", "full")
_TIER_INDEX = {tier: index for index, tier in enumerate(TIERS)}
_TASK_FLOORS = {
    "CLASSIFY": "nano",
    "DRAFT": "nano",
    "DIAGNOSE": "mini",
    "CONVERSE": "mini",
    "DECIDE": "full",
}


@dataclass(frozen=True)
class RouteDecision:
    task: str
    tier: str
    provider: str
    model: str
    reason: str
    raised_by: list[str]
    escalated_from: str | None
    latency_ms: float
    tokens: int | None

    def as_dict(self) -> dict:
        """Return the wire shape used by the explanation endpoint and UI."""
        return {
            "task": self.task,
            "tier": self.tier,
            "provider": self.provider,
            "model": self.model,
            "reason": self.reason,
            "raised_by": list(self.raised_by),
            "escalated_from": self.escalated_from,
            "latency_ms": self.latency_ms,
            "tokens": self.tokens,
        }


@dataclass(frozen=True)
class RoutedResult:
    """A provider response paired with the decision that produced it."""

    result: str
    decision: RouteDecision


class ProviderUnavailable(RuntimeError):
    """Raised only after every configured provider has failed."""

    def __init__(self, message: str, decision: RouteDecision):
        super().__init__(message)
        self.decision = decision


def _normalise_task(task: str) -> str:
    normalised = str(task).upper()
    if normalised not in TASKS:
        raise ValueError(f"Unknown router task: {task!r}")
    return normalised


def _normalise_tier(tier: str) -> str:
    normalised = str(tier).lower()
    if normalised not in _TIER_INDEX:
        raise ValueError(f"Unknown router tier: {tier!r}")
    return normalised


def _raise_tier(tier: str, steps: int = 1) -> str:
    return TIERS[min(_TIER_INDEX[tier] + steps, len(TIERS) - 1)]


def _format_inr(amount_inr: float) -> str:
    return f"₹{int(round(amount_inr)):,}"


def _model_for(provider: str, tier: str) -> str:
    # The legacy names remain accepted as a compatibility bridge for local .env
    # files and direct callers of ai_client's old wrappers.
    value = getattr(settings, f"{provider}_{tier}_model", "")
    if value:
        return value
    legacy = {
        ("gemini", "nano"): "gemini_draft_model",
        ("gemini", "mini"): "gemini_model",
        ("gemini", "full"): "gemini_strong_model",
        ("openai", "full"): "openai_model",
    }.get((provider, tier))
    return str(getattr(settings, legacy, "")) if legacy else ""


def _provider_order(provider_override: str | None = None) -> list[str]:
    override = (provider_override or settings.llm_provider).strip().lower()
    if override in {"openai", "gemini"}:
        return [override, "gemini" if override == "openai" else "openai"]
    return ["openai", "gemini"]


def _raiser_details(
    *,
    amount_inr: float,
    retries_used: int,
    max_retries: int,
    voice_attempts: int,
    voice_attempt_cap: int,
    discount_pct: float | None,
    policy_cap_pct: float | None,
) -> tuple[list[str], list[str]]:
    raised_by: list[str] = []
    details: list[str] = []

    if amount_inr >= settings.router_stakes_threshold_inr:
        raised_by.append("stakes")
        details.append(f"{_format_inr(amount_inr)} at stake")

    proximity: list[str] = []
    if retries_used == max_retries - 1:
        proximity.append("last retry available")
    if voice_attempts == voice_attempt_cap - 1:
        proximity.append("last voice attempt available")
    if policy_cap_pct is not None and discount_pct is not None and discount_pct >= policy_cap_pct - 2:
        proximity.append("discount near policy cap")
    if proximity:
        raised_by.append("guardrail_proximity")
        details.extend(proximity)

    return raised_by, details


def _reason(
    *,
    floor: str,
    tier: str,
    model: str,
    raised_by: list[str],
    details: list[str],
    escalated_from: str | None,
) -> str:
    if escalated_from:
        return f"Response needed a stronger model → raised from {escalated_from} to {tier} · {model}"
    if details:
        return f"{' + '.join(details)} → raised to {tier} · {model}"
    return f"{floor} task floor → {tier} · {model}"


def explain_route(
    task: str,
    *,
    amount_inr: float = 0.0,
    retries_used: int = 0,
    max_retries: int = 3,
    voice_attempts: int = 0,
    voice_attempt_cap: int = 2,
    discount_pct: float | None = None,
    policy_cap_pct: float | None = None,
    live: bool = False,
    escalated_from: str | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> RouteDecision:
    """Explain the route without importing either provider or making a call.

    ``amount_inr`` is intentionally rupees. Callers holding a database
    ``amount_minor`` value convert once before entering this boundary.
    """
    task_name = _normalise_task(task)
    floor = _TASK_FLOORS[task_name]
    if task_name == "DRAFT" and live:
        floor = "mini"

    raised_by, details = _raiser_details(
        amount_inr=float(amount_inr),
        retries_used=int(retries_used),
        max_retries=int(max_retries),
        voice_attempts=int(voice_attempts),
        voice_attempt_cap=int(voice_attempt_cap),
        discount_pct=discount_pct,
        policy_cap_pct=float(policy_cap_pct) if policy_cap_pct is not None else None,
    )
    tier = floor
    for _ in raised_by:
        tier = _raise_tier(tier)

    provider = _provider_order(provider_override)[0]
    model = model_override or _model_for(provider, tier)
    return RouteDecision(
        task=task_name,
        tier=tier,
        provider=provider,
        model=model,
        reason=_reason(
            floor=floor,
            tier=tier,
            model=model,
            raised_by=raised_by,
            details=details,
            escalated_from=escalated_from,
        ),
        raised_by=raised_by,
        escalated_from=escalated_from,
        latency_ms=0.0,
        tokens=None,
    )


# Short, discoverable name for callers that only need the model-free decision.
route_decision = explain_route


def _json_response(task: str) -> bool:
    return task in {"CLASSIFY", "DIAGNOSE", "DECIDE"}


def _needs_escalation(task: str, output: str) -> bool:
    text = output.strip()
    if not text:
        return True
    lowered = text.lower()
    if any(
        phrase in lowered
        for phrase in ("i can't", "i cannot", "i’m sorry", "i'm sorry", "i am sorry", "refuse")
    ):
        return True
    if not _json_response(task):
        return False
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return True
    if not isinstance(payload, dict):
        return True
    confidence = payload.get("confidence")
    return isinstance(confidence, (int, float)) and confidence < 0.5


def _openai_request(
    prompt: str, model: str, *, json_mode: bool, api_key: str | None = None
) -> tuple[str, int | None]:
    if not api_key and not settings.openai_api_key:
        raise RuntimeError("OpenAI API key is missing")
    # Keep this import lazy: a broken optional install must not take down the API.
    from openai import OpenAI

    client = OpenAI(api_key=api_key or settings.openai_api_key)
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    usage = getattr(response, "usage", None)
    tokens = getattr(usage, "total_tokens", None)
    content = response.choices[0].message.content or ""
    return content, int(tokens) if tokens is not None else None


def _gemini_request(
    prompt: str, model: str, *, json_mode: bool, api_key: str | None = None
) -> tuple[str, int | None]:
    if not api_key and not settings.gemini_api_key:
        raise RuntimeError("Gemini API key is missing")
    # Both Gemini imports stay inside the provider adapter for offline startup.
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key or settings.gemini_api_key)
    config_kwargs = {
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
    }
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    usage = getattr(response, "usage_metadata", None)
    tokens = getattr(usage, "total_token_count", None)
    return response.text or "", int(tokens) if tokens is not None else None


_PROVIDER_REQUESTS: dict[str, Callable[..., tuple[str, int | None]]] = {
    "openai": _openai_request,
    "gemini": _gemini_request,
}


class ModelRouter:
    """Select a tier and provider for one advisory prompt."""

    def explain(self, task: str, **kwargs) -> RouteDecision:
        return explain_route(task, **kwargs)

    def route(self, task: str, **kwargs) -> RouteDecision:
        return self.explain(task, **kwargs)

    def call(
        self,
        task: str,
        prompt: str,
        *,
        validator: Callable[[str], bool] | None = None,
        provider_override: str | None = None,
        model_override: str | None = None,
        api_key_override: str | None = None,
        **kwargs,
    ) -> RoutedResult:
        task_name = _normalise_task(task)
        initial = explain_route(
            task_name,
            provider_override=provider_override,
            model_override=model_override,
            **kwargs,
        )
        validator = validator or (lambda output: not _needs_escalation(task_name, output))
        decision = initial
        escalated = False
        failures: list[str] = []

        for attempt in range(2):
            if attempt == 1:
                escalated = True
                next_tier = _raise_tier(initial.tier)
                decision = explain_route(
                    task_name,
                    provider_override=provider_override,
                    **kwargs,
                    escalated_from=initial.tier,
                )
                # A full-tier floor cannot be raised further, but the second
                # attempt is still recorded and never turns into a third call.
                decision = replace(
                    decision,
                    tier=next_tier,
                    model=_model_for(_provider_order(provider_override)[0], next_tier),
                    reason=_reason(
                        floor=_TASK_FLOORS[task_name],
                        tier=next_tier,
                        model=_model_for(_provider_order(provider_override)[0], next_tier),
                        raised_by=decision.raised_by,
                        details=[],
                        escalated_from=initial.tier,
                    ),
                )

            response_received = False
            for provider in _provider_order(provider_override):
                model = (
                    model_override
                    if provider == provider_override and model_override
                    else _model_for(provider, decision.tier)
                )
                started = time.perf_counter()
                try:
                    request_kwargs = {"json_mode": _json_response(task_name)}
                    if api_key_override and provider == provider_override:
                        request_kwargs["api_key"] = api_key_override
                    output, tokens = _PROVIDER_REQUESTS[provider](prompt, model, **request_kwargs)
                except Exception as exc:
                    failures.append(f"{provider}: {exc}")
                    # A 429, missing key/SDK, and transport failure all take
                    # the same safe path: try the other provider.
                    logger.warning("%s provider unavailable (%s); trying the next provider.", provider, exc)
                    continue

                response_received = True
                elapsed = round((time.perf_counter() - started) * 1000, 2)
                final_reason = decision.reason
                if provider != initial.provider:
                    provider_names = {"openai": "OpenAI", "gemini": "Gemini"}
                    final_reason = (
                        f"{decision.reason} · {provider_names[initial.provider]} unavailable "
                        f"→ {provider_names[provider]}"
                    )
                final = replace(
                    decision,
                    provider=provider,
                    model=model,
                    reason=final_reason,
                    latency_ms=elapsed,
                    tokens=tokens,
                )
                if validator(output) or attempt == 1:
                    return RoutedResult(result=output, decision=final)

                logger.warning(
                    "%s response for %s needs escalation; retrying once at the next tier.",
                    provider,
                    task_name,
                )
                # Do not try another provider at the same tier for malformed
                # content: this is one deliberate, observable escalation.
                break

            if not response_received:
                break
            if escalated:
                break

        message = "All configured LLM providers failed"
        if failures:
            message += f": {'; '.join(failures)}"
        raise ProviderUnavailable(message, decision)

    def generate(self, task: str, prompt: str, **kwargs) -> RoutedResult:
        """Named alias for integrations that think in terms of generation."""
        return self.call(task, prompt, **kwargs)


router = ModelRouter()


def build_task_generate(
    task: str,
    *,
    amount_inr: float = 0.0,
    live: bool = False,
    retries_used: int = 0,
    voice_attempts: int = 0,
    discount_pct: float | None = None,
    policy_cap_pct: float | None = None,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> Callable[[str], str]:
    """Adapt the routed result to the legacy ``generate(prompt) -> str`` API."""

    def generate(prompt: str) -> str:
        return router.call(
            task,
            prompt,
            amount_inr=amount_inr,
            live=live,
            retries_used=retries_used,
            voice_attempts=voice_attempts,
            discount_pct=discount_pct,
            policy_cap_pct=policy_cap_pct,
            provider_override=provider,
            model_override=model,
            api_key_override=api_key,
        ).result

    return generate
