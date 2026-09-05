"""Demo endpoint for the tiny learned repayment-probability model.

See ``application.operations.repayment_model`` - this is a small logistic
regression fit at startup, exposed for demos. It is not the simulator's
projection model.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from application.operations.repayment_model import (
    FEATURES,
    MODEL,
    TEST_ACCURACY,
    TRAIN_ACCURACY,
    RepaymentFeatures,
    predict,
)

router = APIRouter(prefix="/repayment", tags=["repayment"])


class PredictBody(BaseModel):
    amount_inr: float = Field(gt=0)
    days_overdue: int = Field(default=0, ge=0)
    retries_used: int = Field(default=0, ge=0)
    prior_repayments: int = Field(default=0, ge=0)
    in_quiet_hours: bool = False
    channel_retried: bool = False
    failure_class: int = Field(default=1, ge=1, le=4)


@router.post("/predict")
def predict_repayment(body: PredictBody) -> dict:
    result = predict(RepaymentFeatures(**body.model_dump()))
    return {
        "probability": result.probability,
        "band": result.band,
        "contributions": [
            {"feature": name, "logit_contribution": value}
            for name, value in result.contributions
        ],
    }


@router.get("/model")
def model_card() -> dict:
    """Inspect the fitted weights and how well it learned the synthetic law."""
    return {
        "kind": "logistic_regression",
        "trained_on": "synthetic data (demo only)",
        "train_accuracy": round(TRAIN_ACCURACY, 3),
        "test_accuracy": round(TEST_ACCURACY, 3),
        "bias": round(MODEL.bias, 4),
        "weights": {
            name: round(w, 4) for name, w in zip(FEATURES, MODEL.weights)
        },
    }
