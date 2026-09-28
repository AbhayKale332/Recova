"""Model-route explanation endpoint."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.operations.policy_repository import get_policy
from application.operations.model_router import explain_route
from application.persistence import get_db
from application.settings import settings

router = APIRouter(prefix="/router", tags=["router"])

# Tasks whose judgment Jev answers first; the tiered LLM route below is then the
# fallback. DRAFT and CONVERSE produce text, which stays with the LLM.
_JEV_FIRST = {"CLASSIFY", "DIAGNOSE", "DECIDE"}


class ExplainBody(BaseModel):
    task: Literal["CLASSIFY", "DRAFT", "DIAGNOSE", "CONVERSE", "DECIDE"]
    amount_inr: float = Field(default=0, ge=0)
    retries_used: int = Field(default=0, ge=0)
    voice_attempts: int = Field(default=0, ge=0)
    discount_pct: float | None = Field(default=None, ge=0, le=100)


@router.post("/explain")
def explain(body: ExplainBody, db: Session = Depends(get_db)) -> dict:
    """Return the deterministic route explanation without calling a provider."""
    policy_cap_pct = float(get_policy(db)["max_discount_pct"])
    route = explain_route(
        body.task,
        amount_inr=body.amount_inr,
        retries_used=body.retries_used,
        voice_attempts=body.voice_attempts,
        discount_pct=body.discount_pct,
        policy_cap_pct=policy_cap_pct,
    ).as_dict()
    route["jev"] = {
        "first": body.task in _JEV_FIRST,
        "model": settings.jev_model,
        "available": bool(settings.jev_enabled and settings.open_router),
    }
    return route
