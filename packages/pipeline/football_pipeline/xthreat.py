"""Expected Threat (xT) — 16x12 grid Markov model (Karun Singh formulation).

Event-data only. Trained on a corpus of matches. The bulk of the value stabilizes
in ~4-5 iterations (Karun Singh's observation); strict max-norm convergence to 1e-4
takes ~100+ cheap iterations because deep-defensive cells have p_move ~= 1.
All computation in MODEL coords: acting team attacks +x, pitch 105x68 meters.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from football_core.coords import PITCH_LENGTH, PITCH_WIDTH, statsbomb_to_canonical

COLS, ROWS = 16, 12


def cell_of(x: float, y: float) -> int:
    """Model coords -> flat cell index (col-major invariant: idx = row*COLS + col)."""
    col = min(COLS - 1, max(0, int((x + PITCH_LENGTH / 2) / (PITCH_LENGTH / COLS))))
    row = min(ROWS - 1, max(0, int((y + PITCH_WIDTH / 2) / (PITCH_WIDTH / ROWS))))
    return row * COLS + col


def _model_xy(loc: list[float]) -> tuple[float, float]:
    return statsbomb_to_canonical(loc[0], loc[1])


def train_xt(all_events: list[list[dict[str, Any]]], max_iter: int = 500, tol: float = 1e-4):
    """Fit the xT grid from raw StatsBomb events across matches.

    Returns (xt: np.ndarray[ROWS*COLS], iterations, converged).
    """
    n = ROWS * COLS
    shot_count = np.zeros(n)
    goal_count = np.zeros(n)
    move_count = np.zeros(n)
    trans = np.zeros((n, n))

    for events in all_events:
        for ev in events:
            t = ev["type"]["name"]
            loc = ev.get("location")
            if not loc:
                continue
            if t == "Shot":
                sh = ev.get("shot", {})
                if (sh.get("type", {}) or {}).get("name") == "Penalty":
                    continue
                c = cell_of(*_model_xy(loc))
                shot_count[c] += 1
                if (sh.get("outcome", {}) or {}).get("name") == "Goal":
                    goal_count[c] += 1
            elif t in ("Pass", "Carry"):
                if t == "Pass" and ev.get("pass", {}).get("outcome"):
                    continue  # unsuccessful pass
                end = ev.get("pass", {}).get("end_location") if t == "Pass" else ev.get("carry", {}).get("end_location")
                if not end:
                    continue
                c0 = cell_of(*_model_xy(loc))
                c1 = cell_of(*_model_xy(end))
                move_count[c0] += 1
                trans[c0, c1] += 1

    total = shot_count + move_count
    total_safe = np.where(total == 0, 1, total)
    p_shot = shot_count / total_safe
    p_move = move_count / total_safe
    p_goal = np.divide(goal_count, np.where(shot_count == 0, 1, shot_count))
    row_sums = trans.sum(axis=1, keepdims=True)
    T = np.divide(trans, np.where(row_sums == 0, 1, row_sums))

    xt = np.zeros(n)
    iters, converged = 0, False
    for i in range(1, max_iter + 1):
        new = p_shot * p_goal + p_move * (T @ xt)
        delta = float(np.max(np.abs(new - xt)))
        xt = new
        iters = i
        if delta < tol:
            converged = True
            break
    return xt, iters, converged


def xt_delta(xt: np.ndarray, start_loc: list[float], end_loc: list[float]) -> tuple[float, float, float]:
    """Per-move xT (before, after, delta) in model coords."""
    before = round(float(xt[cell_of(*_model_xy(start_loc))]), 4)
    after = round(float(xt[cell_of(*_model_xy(end_loc))]), 4)
    return before, after, round(after - before, 4)  # delta from rounded values: exact invariant


def grid_rows(xt: np.ndarray) -> list[list[float]]:
    """Flat -> rows x cols nested list (row 0 = y min), rounded for JSON."""
    return [[round(float(xt[r * COLS + c]), 4) for c in range(COLS)] for r in range(ROWS)]
