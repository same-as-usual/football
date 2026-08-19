"""Metrica tracking pipeline: continuous replay + Spearman pitch control.

Usage:
    python -m football_pipeline.run_metrica [--game Sample_Game_2]
        [--replay-hz 5] [--pc-every-s 5] [--xg-model artifacts/sb-3795506/shots.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time

import numpy as np
import pandas as pd

from football_adapters.metrica_open import MetricaOpenAdapter, norm_to_canonical
from football_core.coords import PITCH_LENGTH, PITCH_WIDTH
from football_core.model import (
    CanonicalEvent, ChunkIndex, EventChunk, Manifest, MatchMeta, PitchSpec, Point,
    Shot, ShotChunk, SpaceGridChunk, SpaceSnapshot, TeamRef, TrackingChunk,
    TrackingPlayer, XgModelSpec,
)
from football_pipeline.pitch_control import COLS, PHYSICS, ROWS, pitch_control_frame, velocities
from football_pipeline.publish import publish_bundle
from football_pipeline.xg_glassbox import FEATURES, score_shot

FPS = 25.0


def log(msg: str) -> None:
    print(f"[metrica] {msg}", flush=True)


def to_canonical_cols(df: pd.DataFrame, pids: list[str]) -> None:
    """In-place: convert normalized Metrica coords to canonical meters."""
    for pid in pids + ["ball"]:
        x, y = df[f"{pid}_x"].to_numpy(), df[f"{pid}_y"].to_numpy()
        df[f"{pid}_x"] = (x - 0.5) * PITCH_LENGTH
        df[f"{pid}_y"] = (0.5 - y) * PITCH_WIDTH


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="Sample_Game_2")
    ap.add_argument("--replay-hz", type=float, default=5.0)
    ap.add_argument("--pc-every-s", type=float, default=5.0)
    ap.add_argument("--xg-model", default="artifacts/sb-3795506/shots.json")
    ap.add_argument("--out", default="artifacts")
    args = ap.parse_args()

    adapter = MetricaOpenAdapter(args.game)
    home_df, home_pids = adapter.load_tracking("Home")
    away_df, away_pids = adapter.load_tracking("Away")
    events = adapter.load_events()
    df = adapter.merged_tracking(home_df, away_df)
    pids = home_pids + away_pids
    to_canonical_cols(df, pids)
    log(f"{len(df)} tracking frames, {len(pids)} players, {len(events)} events")

    # period start times (Time [s] is continuous across the match)
    period_start = df.groupby("Period")["Time [s]"].min().to_dict()

    def to_period_ms(time_s: float, period: int) -> int:
        return int(round((time_s - period_start[period]) * 1000))

    # ---- attacking direction per (side, period): keeper = first pid ------- #
    atk_right: dict[tuple[str, int], bool] = {}
    for side, gk in (("home", home_pids[0]), ("away", away_pids[0])):
        for period in sorted(df["Period"].unique()):
            gk_x = df.loc[df["Period"] == period, f"{gk}_x"].mean()
            atk_right[(side, int(period))] = bool(gk_x < 0)
    log(f"attacking direction: {atk_right}")

    # ---- replay tracking chunk (downsampled) ------------------------------ #
    step = int(round(FPS / args.replay_hz))
    sampled = df.iloc[::step]
    players = [
        TrackingPlayer(pid=p, team="home" if p in home_pids else "away",
                       num=int(p[1:]), keeper=(p in (home_pids[0], away_pids[0])))
        for p in pids
    ]
    frames: list[list[float | None]] = []
    cols_xy = [c for p in pids for c in (f"{p}_x", f"{p}_y")]
    arr = sampled[["Period", "Time [s]", "ball_x", "ball_y", *cols_xy]].to_numpy()
    for row in arr:
        period = int(row[0])
        rec: list[float | None] = [period, to_period_ms(row[1], period)]
        for v in row[2:]:
            rec.append(None if math.isnan(v) else round(float(v), 2))
        frames.append(rec)
    tracking = TrackingChunk(frameRateHz=args.replay_hz, players=players, frames=frames)
    log(f"replay: {len(frames)} frames at {args.replay_hz} Hz")

    # ---- pitch control snapshots ------------------------------------------ #
    pos_all = df[cols_xy].to_numpy().reshape(len(df), len(pids), 2)
    vel_all = velocities(np.nan_to_num(pos_all), FPS)
    is_home = np.array([p.team == "home" for p in players])
    is_keeper = np.array([p.keeper for p in players])
    pc_step = int(round(FPS * args.pc_every_s))
    snapshots: list[SpaceSnapshot] = []
    t0 = time.time()
    for i in range(0, len(df), pc_step):
        row = df.iloc[i]
        ball = np.array([row["ball_x"], row["ball_y"]])
        if np.isnan(ball).any():
            continue
        pos, vel = pos_all[i], vel_all[i]
        on_pitch = ~np.isnan(pos).any(axis=1)
        if on_pitch.sum() < 10:
            continue
        control = pitch_control_frame(
            pos[on_pitch], vel[on_pitch], is_home[on_pitch], is_keeper[on_pitch], ball,
        )
        period = int(row["Period"])
        snapshots.append(SpaceSnapshot(
            period=period, t=to_period_ms(row["Time [s]"], period),
            values=[round(float(v), 2) for v in control],
        ))
    space = SpaceGridChunk(cols=COLS, rows=ROWS, physics=PHYSICS, snapshots=snapshots)
    log(f"pitch control: {len(snapshots)} snapshots ({COLS}x{ROWS}) in {time.time()-t0:.0f}s")

    # ---- events + shots ---------------------------------------------------- #
    xg_source = json.loads(open(args.xg_model).read())["model"]
    model = {"intercept": xg_source["intercept"], "coefficients": xg_source["coefficients"]}
    model_spec = XgModelSpec(**xg_source)

    canonical_events: list[CanonicalEvent] = []
    shots: list[Shot] = []
    goals = {"home": 0, "away": 0}
    for i, ev in events.iterrows():
        etype = str(ev["Type"]).strip()
        if etype not in ("PASS", "SHOT", "RECOVERY", "BALL LOST", "CHALLENGE", "SET PIECE"):
            continue
        side = str(ev["Team"]).strip().lower()
        period = int(ev["Period"])
        t = to_period_ms(float(ev["Start Time [s]"]), period)
        sx, sy = float(ev["Start X"]), float(ev["Start Y"])
        if math.isnan(sx):
            continue
        start = norm_to_canonical(sx, sy)
        end = None
        if not math.isnan(float(ev.get("End X", float("nan")))):
            end = norm_to_canonical(float(ev["End X"]), float(ev["End Y"]))
        subtype = str(ev.get("Subtype", "") or "")
        canonical_events.append(CanonicalEvent(
            eventId=f"m{i}", t=t, period=period,
            type=etype.lower().replace(" ", "_"), team=side,  # type: ignore[arg-type]
            player=str(ev.get("From", "") or "") or None,
            recipient=str(ev.get("To", "") or "") or None,
            start=Point(x=round(start[0], 2), y=round(start[1], 2)),
            end=Point(x=round(end[0], 2), y=round(end[1], 2)) if end else None,
            outcome="goal" if ("GOAL" in subtype and "OWN" not in subtype and etype == "SHOT") else None,
        ))
        if etype == "SHOT":
            right = atk_right[(side, period)]
            xm = start[0] if right else -start[0]
            ym = start[1] if right else -start[1]
            dist = math.hypot(PITCH_LENGTH / 2 - xm, ym)
            a1 = math.atan2(7.32 / 2 - ym, PITCH_LENGTH / 2 - xm)
            a2 = math.atan2(-7.32 / 2 - ym, PITCH_LENGTH / 2 - xm)
            feats = {
                "distance_m": round(dist, 2),
                "goal_angle_rad": round(abs(a1 - a2), 3),
                "is_header": 1.0 if "HEAD" in subtype else 0.0,
                "under_pressure": 0.0,
                "is_open_play": 1.0,
                "first_time": 0.0,
            }
            xg, log_odds, baseline, contribs = score_shot(model, feats)
            is_goal = "GOAL" in subtype and "OWN" not in subtype
            if is_goal:
                goals[side] += 1
            shots.append(Shot(
                eventId=f"m{i}", t=t, period=period, team=side,  # type: ignore[arg-type]
                player=str(ev.get("From", "?")),
                location=Point(x=round(start[0], 2), y=round(start[1], 2)),
                attackingRight=right,
                outcome="goal" if is_goal else ("on_target" if "ON TARGET" in subtype else "off_target"),
                xg=xg, logOdds=log_odds, baselineXg=baseline,
                contributions=contribs, featureValues=feats,
            ))
    log(f"events={len(canonical_events)} shots={len(shots)} score={goals}")

    manifest = Manifest(
        matchId=f"metrica-{args.game.lower().replace('_', '-')}",
        meta=MatchMeta(
            competition="Metrica Sample", season="anonymised",
            home=TeamRef(id="home", name="Home"), away=TeamRef(id="away", name="Away"),
            score=(goals["home"], goals["away"]), kickoff=None, pitch=PitchSpec(),
        ),
        capabilities=adapter.capabilities(),
        provenance=adapter.provenance(),
        chunks=ChunkIndex(frames="tracking.json", spaceGrids="space.json"),
    )
    out = publish_bundle(
        args.out, manifest, EventChunk(events=canonical_events),
        ShotChunk(model=model_spec, shots=shots),
        tracking=tracking, space_grids=space,
    )
    log(f"published -> {out}")


if __name__ == "__main__":
    sys.exit(main())
