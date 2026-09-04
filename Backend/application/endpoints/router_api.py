"""Model-route explanation endpoint."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.operations.policy_repository import get_policy
from application.operations.model_router import explain_route
from application.persistence import get_db

router = APIRouter(prefix="/router", tags=["router"])


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
    return explain_route(
        body.task,
        amount_inr=body.amount_inr,
        retries_used=body.retries_used,
        voice_attempts=body.voice_attempts,
        discount_pct=body.discount_pct,
        policy_cap_pct=policy_cap_pct,
    ).as_dict()
