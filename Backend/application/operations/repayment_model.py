"""A tiny logistic-regression model that scores a customer's probability of repayment.

This is a *demo* model, not the production estimator. The simulator's real
projection lives in ``application.simulation.probability`` and is a Bayesian
prior/posterior design that deliberately avoids fitting to seeded data. This
module does the opposite on purpose: it trains an actual classifier by gradient
descent so the demo can show a learned decision surface, feature weights, and a
per-case score.

Everything is pure stdlib. Training data is generated from a hand-written
"ground truth" rule with noise, the model is fit once at import time (a few
hundred rows, a couple hundred epochs - well under a second), and the fitted
weights are then reused for every prediction.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# --- Feature layout -------------------------------------------------------------
# Order matters: weights are aligned to this list.
FEATURES = [
    "amount_log",        # ln(amount_inr / 5000), bigger asks convert worse
    "days_overdue",      # scaled to ~[0, 1] over 120 days
    "retries_used",      # scaled to ~[0, 1] over 4 attempts
    "prior_repayments",  # scaled to ~[0, 1] over 5 past on-time payments
    "in_quiet_hours",    # 1 if contact is deferred, else 0
    "channel_retried",   # 1 if the chosen channel was already tried, else 0
    "failure_class_1",   # one-hot: transient rail failure (recoverable)
    "failure_class_2",   # one-hot: authentication / 3DS friction
    "failure_class_3",   # one-hot: insufficient funds
    "failure_class_4",   # one-hot: deliberate / disputed
]

_AMOUNT_REFERENCE_INR = 5000.0


@dataclass
class RepaymentFeatures:
    """Raw inputs for one case, before scaling."""

    amount_inr: float
    days_overdue: int = 0
    retries_used: int = 0
    prior_repayments: int = 0
    in_quiet_hours: bool = False
    channel_retried: bool = False
    failure_class: int = 1  # 1..4

    def to_vector(self) -> list[float]:
        fc = max(1, min(4, int(self.failure_class)))
        return [
            math.log(max(self.amount_inr, 1.0) / _AMOUNT_REFERENCE_INR),
            min(self.days_overdue, 120) / 120.0,
            min(self.retries_used, 4) / 4.0,
            min(self.prior_repayments, 5) / 5.0,
            1.0 if self.in_quiet_hours else 0.0,
            1.0 if self.channel_retried else 0.0,
            1.0 if fc == 1 else 0.0,
            1.0 if fc == 2 else 0.0,
            1.0 if fc == 3 else 0.0,
            1.0 if fc == 4 else 0.0,
        ]


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-min(x, 60.0)))
    e = math.exp(max(x, -60.0))
    return e / (1.0 + e)


# --- Synthetic ground truth ----------------------------------------------------
# A repayment "law" a domain expert would roughly agree with. The model never
# sees this function - it only sees noisy 0/1 labels drawn from it.
_CLASS_BASE = {1: 0.78, 2: 0.62, 3: 0.45, 4: 0.25}


def _true_probability(f: RepaymentFeatures) -> float:
    logit = _logit(_CLASS_BASE[max(1, min(4, int(f.failure_class)))])
    logit += -0.20 * math.log(max(f.amount_inr, 1.0) / _AMOUNT_REFERENCE_INR)
    logit += -0.010 * min(f.days_overdue, 120)
    logit += -0.45 * min(f.retries_used, 4)
    logit += 0.35 * min(f.prior_repayments, 5)
    logit += -0.55 if f.in_quiet_hours else 0.0
    logit += -0.50 if f.channel_retried else 0.0
    return _sigmoid(logit)


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def _make_dataset(n: int, seed: int) -> list[tuple[list[float], int]]:
    rng = random.Random(seed)
    rows: list[tuple[list[float], int]] = []
    for _ in range(n):
        f = RepaymentFeatures(
            amount_inr=rng.choice([500, 1500, 3000, 5000, 12000, 30000, 75000]),
            days_overdue=rng.randint(0, 120),
            retries_used=rng.randint(0, 4),
            prior_repayments=rng.randint(0, 5),
            in_quiet_hours=rng.random() < 0.3,
            channel_retried=rng.random() < 0.35,
            failure_class=rng.randint(1, 4),
        )
        label = 1 if rng.random() < _true_probability(f) else 0
        rows.append((f.to_vector(), label))
    return rows


# --- The model ---------------------------------------------------------------
@dataclass
class LogisticRegression:
    weights: list[float] = field(default_factory=lambda: [0.0] * len(FEATURES))
    bias: float = 0.0

    def predict_proba(self, x: list[float]) -> float:
        z = self.bias + sum(w * xi for w, xi in zip(self.weights, x))
        return _sigmoid(z)

    def fit(
        self,
        data: list[tuple[list[float], int]],
        *,
        epochs: int = 250,
        lr: float = 0.3,
        l2: float = 1e-4,
    ) -> "LogisticRegression":
        n = len(data)
        for _ in range(epochs):
            g_w = [0.0] * len(self.weights)
            g_b = 0.0
            for x, y in data:
                err = self.predict_proba(x) - y
                for j, xi in enumerate(x):
                    g_w[j] += err * xi
                g_b += err
            for j in range(len(self.weights)):
                self.weights[j] -= lr * (g_w[j] / n + l2 * self.weights[j])
            self.bias -= lr * (g_b / n)
        return self

    def accuracy(self, data: list[tuple[list[float], int]]) -> float:
        hits = sum(1 for x, y in data if (self.predict_proba(x) >= 0.5) == bool(y))
        return hits / max(len(data), 1)


@dataclass
class RepaymentPrediction:
    probability: float
    band: str            # "high" / "medium" / "low"
    contributions: list[tuple[str, float]]  # (feature, signed logit contribution)


_TRAIN = _make_dataset(600, seed=42)
_TEST = _make_dataset(200, seed=7)
MODEL = LogisticRegression().fit(_TRAIN)
TRAIN_ACCURACY = MODEL.accuracy(_TRAIN)
TEST_ACCURACY = MODEL.accuracy(_TEST)


def predict_for_case(
    *,
    failure_class: int,
    amount_inr: float,
    days_overdue: int = 0,
    retries_used: int = 0,
    prior_repayments: int = 0,
    in_quiet_hours: bool = False,
    channel_retried: bool = False,
) -> RepaymentPrediction:
    """Score a case from loose primitives - the shape callers outside this
    module (the decision layer, the API) actually have on hand."""
    return predict(
        RepaymentFeatures(
            amount_inr=amount_inr,
            days_overdue=days_overdue,
            retries_used=retries_used,
            prior_repayments=prior_repayments,
            in_quiet_hours=in_quiet_hours,
            channel_retried=channel_retried,
            failure_class=failure_class,
        )
    )


def predict(f: RepaymentFeatures) -> RepaymentPrediction:
    x = f.to_vector()
    p = MODEL.predict_proba(x)
    contribs = sorted(
        ((name, round(w * xi, 4)) for name, w, xi in zip(FEATURES, MODEL.weights, x)),
        key=lambda c: abs(c[1]),
        reverse=True,
    )
    band = "high" if p >= 0.66 else "medium" if p >= 0.4 else "low"
    return RepaymentPrediction(probability=round(p, 4), band=band, contributions=contribs)
