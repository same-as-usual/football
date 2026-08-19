"""Spearman (2018) pitch control — vectorized numpy implementation.

Physics parameters follow the open LaurieOnTracking implementation of
"Off the Ball Scoring Opportunities" (Spearman, Sloan 2018):
  max speed 5 m/s · reaction time 0.7 s · tti sigma 0.45 s
  control rate lambda 4.3 (keeper 12.9 when defending) · ball speed 15 m/s
Integration over 0.04 s timesteps until 99% of control probability assigned.

P(home controls cell) is computed on a cols x rows grid over the pitch.
"""
from __future__ import annotations

import numpy as np

from football_core.coords import PITCH_LENGTH, PITCH_WIDTH

PHYSICS = {
    "maxSpeedMs": 5.0,
    "reactionTimeS": 0.7,
    "ttiSigmaS": 0.45,
    "controlLambda": 4.3,
    "keeperLambda": 12.9,
    "ballSpeedMs": 15.0,
    "dtS": 0.04,
    "convergence": 0.99,
}

COLS, ROWS = 48, 32


def grid_centers(cols: int = COLS, rows: int = ROWS) -> np.ndarray:
    """(rows*cols, 2) cell-center coordinates, row-major, row 0 = y min."""
    xs = (np.arange(cols) + 0.5) * PITCH_LENGTH / cols - PITCH_LENGTH / 2
    ys = (np.arange(rows) + 0.5) * PITCH_WIDTH / rows - PITCH_WIDTH / 2
    gx, gy = np.meshgrid(xs, ys)  # (rows, cols)
    return np.stack([gx.ravel(), gy.ravel()], axis=1)


def pitch_control_frame(
    pos: np.ndarray,       # (n, 2) player positions, meters
    vel: np.ndarray,       # (n, 2) player velocities, m/s
    is_home: np.ndarray,   # (n,) bool
    is_keeper: np.ndarray, # (n,) bool
    ball: np.ndarray,      # (2,) ball position
    cells: np.ndarray | None = None,
    max_steps: int = 250,
) -> np.ndarray:
    """Returns (rows*cols,) P(home controls each cell)."""
    p = PHYSICS
    if cells is None:
        cells = grid_centers()
    m = cells.shape[0]

    # ball travel time to each cell
    t_ball = np.linalg.norm(cells - ball, axis=1) / p["ballSpeedMs"]  # (m,)

    # player simple time-to-intercept: react (carry velocity), then sprint
    r_react = pos + vel * p["reactionTimeS"]                       # (n, 2)
    dists = np.linalg.norm(cells[None, :, :] - r_react[:, None, :], axis=2)  # (n, m)
    tti = p["reactionTimeS"] + dists / p["maxSpeedMs"]             # (n, m)

    lam = np.where(is_keeper, p["keeperLambda"], p["controlLambda"])[:, None]  # (n, 1)
    k = np.pi / np.sqrt(3.0) / p["ttiSigmaS"]

    ppcf = np.zeros_like(tti)          # (n, m) accumulated control prob
    t = t_ball.copy()                  # (m,) current time per cell
    active = np.ones(m, dtype=bool)
    for _ in range(max_steps):
        if not active.any():
            break
        ta = t[active]                                             # (ma,)
        f = 1.0 / (1.0 + np.exp(-k * (ta[None, :] - tti[:, active])))  # (n, ma)
        total = ppcf[:, active].sum(axis=0)                        # (ma,)
        dppcf = (1.0 - total)[None, :] * f * lam * p["dtS"]
        ppcf[:, active] += np.clip(dppcf, 0.0, None)
        t[active] += p["dtS"]
        active_idx = np.flatnonzero(active)
        done = ppcf[:, active_idx].sum(axis=0) >= p["convergence"]
        active[active_idx[done]] = False

    totals = ppcf.sum(axis=0)
    totals = np.where(totals == 0, 1.0, totals)
    home_control = ppcf[is_home].sum(axis=0) / totals
    return home_control


def velocities(track: np.ndarray, fps: float, smooth_window: int = 7) -> np.ndarray:
    """Finite-difference velocities with moving-average smoothing.
    track: (T, n, 2) positions -> (T, n, 2) velocities (m/s)."""
    v = np.gradient(track, axis=0) * fps
    if smooth_window > 1:
        kernel = np.ones(smooth_window) / smooth_window
        v = np.apply_along_axis(lambda a: np.convolve(a, kernel, mode="same"), 0, v)
    # cap outliers (bad detections) at 12 m/s
    speed = np.linalg.norm(v, axis=2, keepdims=True)
    v = np.where(speed > 12.0, v * (12.0 / np.where(speed == 0, 1, speed)), v)
    return v
