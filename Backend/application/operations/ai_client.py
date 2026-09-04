"""Compatibility builders over the advisory model router.

The public ``generate(prompt) -> str`` builders remain because tests and the
simulation runner call them directly. Provider construction itself lives in
``model_router`` and both SDKs remain lazy.
"""

from __future__ import annotations

from application.operations.diagnosis_service import DiagnosisEngine, GenerateFn
from application.operations.model_router import build_task_generate, router


def build_generate(api_key: str | None = None, model: str | None = None) -> GenerateFn:
    """Build the diagnosis generator, routed by default.

    Explicit key/model arguments preserve the historical Gemini override while
    still using the shared provider registry.
    """
    return build_task_generate(
        "DIAGNOSE",
        provider="gemini" if api_key is not None or model is not None else None,
        model=model,
        api_key=api_key,
    )


def build_text_generate(api_key: str | None = None, model: str | None = None) -> GenerateFn:
    """Build the plain-text DRAFT generator used for human-facing messages."""
    return build_task_generate(
        "DRAFT",
        live=True,
        provider="gemini" if api_key is not None or model is not None else None,
        model=model,
        api_key=api_key,
    )


def default_diagnosis_engine() -> DiagnosisEngine:
    """Return a diagnosis engine whose default calls carry amount context."""
    return DiagnosisEngine(router=router)


def build_strong_generate() -> GenerateFn:
    """Build the DECIDE generator; provider choice stays inside the router."""
    return build_task_generate("DECIDE")
