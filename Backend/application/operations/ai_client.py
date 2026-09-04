"""The two remaining AI builders over the advisory model router."""

from __future__ import annotations

from application.operations.diagnosis_service import DiagnosisEngine, GenerateFn
from application.operations.model_router import build_task_generate, router


def default_diagnosis_engine() -> DiagnosisEngine:
    """Return a diagnosis engine whose default calls carry amount context."""
    return DiagnosisEngine(router=router)


def build_strong_generate() -> GenerateFn:
    """Build the DECIDE generator; provider choice stays inside the router."""
    return build_task_generate("DECIDE")
