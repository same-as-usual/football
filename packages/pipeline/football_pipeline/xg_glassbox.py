"""Glass-box xG — plain logistic regression, per-feature contribution = beta_j * x_j.

ShotsGPT approach: contributions read directly off the linear log-odds;
surface only |contribution| > 0.1 log-odds as "significant".
Penalties are excluded from training and assigned a fixed conversion rate.

All geometry in MODEL coords (shooter attacks +x; goal center at (52.5, 0)).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression

from football_core.coords import GOAL_WIDTH, PITCH_LENGTH, statsbomb_to_canonical

GOAL_X = PITCH_LENGTH / 2
POST_Y = GOAL_WIDTH / 2
PENALTY_XG = 0.76
SIGNIFICANCE_LOG_ODDS = 0.1

FEATURES = ["distance_m", "goal_angle_rad", "is_header", "under_pressure", "is_open_play", "first_time"]


def shot_features(ev: dict[str, Any]) -> dict[str, float] | None:
    """Extract glass-box features from a raw StatsBomb shot event."""
    loc = ev.get("location")
    sh = ev.get("shot", {})
    if not loc:
        return None
    x, y = statsbomb_to_canonical(loc[0], loc[1])
    dist = math.hypot(GOAL_X - x, y)
    # opening angle subtended by the posts
    a1 = math.atan2(POST_Y - y, GOAL_X - x)
    a2 = math.atan2(-POST_Y - y, GOAL_X - x)
    angle = abs(a1 - a2)
    body = ((sh.get("body_part", {}) or {}).get("name") or "").lower()
    return {
        "distance_m": round(dist, 2),
        "goal_angle_rad": round(angle, 3),
        "is_header": 1.0 if "head" in body else 0.0,
        "under_pressure": 1.0 if ev.get("under_pressure") else 0.0,
        "is_open_play": 1.0 if (sh.get("type", {}) or {}).get("name") == "Open Play" else 0.0,
        "first_time": 1.0 if sh.get("first_time") else 0.0,
    }


def is_trainable_shot(ev: dict[str, Any]) -> bool:
    if ev["type"]["name"] != "Shot":
        return False
    sh = ev.get("shot", {})
    return (sh.get("type", {}) or {}).get("name") != "Penalty"


def train_xg(all_events: list[list[dict[str, Any]]]):
    """Fit logistic regression across the corpus. Returns (model_dict, n_shots)."""
    X, y = [], []
    for events in all_events:
        for ev in events:
            if not is_trainable_shot(ev):
                continue
            f = shot_features(ev)
            if f is None:
                continue
            X.append([f[k] for k in FEATURES])
            y.append(1 if (ev["shot"].get("outcome", {}) or {}).get("name") == "Goal" else 0)
    clf = LogisticRegression(C=np.inf, max_iter=2000)  # unpenalized — coefficients stay interpretable
    clf.fit(np.array(X), np.array(y))
    model = {
        "intercept": round(float(clf.intercept_[0]), 4),
        "coefficients": {k: round(float(c), 4) for k, c in zip(FEATURES, clf.coef_[0])},
    }
    return model, len(y)


def score_shot(model: dict, features: dict[str, float]):
    """Returns (xg, log_odds, contributions list) — pure glass-box arithmetic."""
    intercept = model["intercept"]
    coefs = model["coefficients"]
    contributions = []
    log_odds = intercept
    for k in FEATURES:
        contrib = coefs[k] * features[k]
        log_odds += contrib
        contributions.append({
            "feature": k,
            "value": features[k],
            "logOddsContribution": round(contrib, 4),
            "significant": abs(contrib) > SIGNIFICANCE_LOG_ODDS,
        })
    xg = 1.0 / (1.0 + math.exp(-log_odds))
    baseline_xg = 1.0 / (1.0 + math.exp(-intercept))
    return round(xg, 4), round(log_odds, 4), round(baseline_xg, 4), contributions
