"""Pipeline orchestrator: one StatsBomb open match end-to-end.

Usage:
    python -m football_pipeline.run --competition 55 --season 43 [--match-id 3795506]
    (default: picks the final of the competition; trains xT + xG on the whole corpus)
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from football_adapters.statsbomb_open import StatsBombOpenAdapter
from football_core.model import (
    CanonicalEvent, ChunkIndex, EventChunk, Manifest, MatchMeta, PitchSpec, Point,
    Shot, ShotChunk, TeamRef, XgModelSpec, XThreatDelta, XThreatGrid,
)
from football_pipeline.frames import build_keyframes
from football_pipeline.normalize import (
    KEPT_TYPES, attacking_right, end_location, event_outcome, parse_ts_ms, to_display,
)
from football_pipeline.publish import publish_bundle
from football_pipeline.xg_glassbox import (
    FEATURES, PENALTY_XG, score_shot, shot_features, train_xg,
)
from football_pipeline.xthreat import grid_rows, train_xt, xt_delta


def log(msg: str) -> None:
    print(f"[pipeline] {msg}", flush=True)


def build_events(raw_events: list[dict[str, Any]], home_id: int, xt) -> EventChunk:
    out: list[CanonicalEvent] = []
    for ev in raw_events:
        etype = ev["type"]["name"]
        if etype not in KEPT_TYPES or not ev.get("location"):
            continue
        is_home = ev["team"]["id"] == home_id
        period = ev["period"]
        start = to_display(ev["location"], is_home, period)
        end_raw = end_location(ev)
        end = to_display(end_raw, is_home, period) if end_raw else None

        xtd = None
        if etype in ("Pass", "Carry") and end_raw and not (etype == "Pass" and ev.get("pass", {}).get("outcome")):
            b, a, d = xt_delta(xt, ev["location"], end_raw)
            xtd = XThreatDelta(before=b, after=a, delta=d)

        out.append(CanonicalEvent(
            eventId=ev["id"],
            t=parse_ts_ms(ev["timestamp"]),
            period=period,
            type=etype.lower().replace(" ", "_"),
            team="home" if is_home else "away",
            player=(ev.get("player") or {}).get("name"),
            playerId=str((ev.get("player") or {}).get("id", "")) or None,
            recipient=(ev.get("pass", {}).get("recipient") or {}).get("name"),
            start=Point(x=start[0], y=start[1]) if start else None,
            end=Point(x=end[0], y=end[1]) if end else None,
            outcome=event_outcome(ev),
            xThreat=xtd,
        ))
    return EventChunk(events=out)


def build_shots(raw_events: list[dict[str, Any]], home_id: int, xg_model: dict,
                model_spec: XgModelSpec, ff_ids: set[str]) -> ShotChunk:
    shots: list[Shot] = []
    for ev in raw_events:
        if ev["type"]["name"] != "Shot" or not ev.get("location"):
            continue
        sh = ev["shot"]
        is_home = ev["team"]["id"] == home_id
        period = ev["period"]
        atk_right = attacking_right(is_home, period)
        loc = to_display(ev["location"], is_home, period)
        feats = shot_features(ev)
        if loc is None or feats is None:
            continue
        is_pen = (sh.get("type", {}) or {}).get("name") == "Penalty"
        if is_pen:
            xg, log_odds, baseline, contribs = PENALTY_XG, 0.0, PENALTY_XG, []
        else:
            xg, log_odds, baseline, contribs = score_shot(xg_model, feats)
        shots.append(Shot(
            eventId=ev["id"],
            t=parse_ts_ms(ev["timestamp"]),
            period=period,
            team="home" if is_home else "away",
            player=(ev.get("player") or {}).get("name", "?"),
            location=Point(x=loc[0], y=loc[1]),
            attackingRight=atk_right,
            outcome=(sh.get("outcome", {}) or {}).get("name", "?").lower().replace(" ", "_"),
            xg=xg, logOdds=log_odds, baselineXg=baseline,
            contributions=contribs, featureValues=feats,
            freezeFrameRef=ev["id"] if ev["id"] in ff_ids else None,
        ))
    return ShotChunk(model=model_spec, shots=shots)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--competition", type=int, default=55)  # UEFA Euro
    ap.add_argument("--season", type=int, default=43)       # 2020
    ap.add_argument("--match-id", type=int, default=None)
    ap.add_argument("--train-matches", type=int, default=60, help="corpus size cap for xT/xG training")
    ap.add_argument("--out", default="artifacts")
    args = ap.parse_args()

    adapter = StatsBombOpenAdapter(args.competition, args.season)
    matches = adapter.list_matches()
    log(f"{len(matches)} matches in competition {args.competition}/{args.season}")

    target = None
    if args.match_id:
        target = next(m for m in matches if m["match_id"] == args.match_id)
    else:
        stage_rank = {"Final": 0, "Semi-finals": 1}
        target = sorted(matches, key=lambda m: stage_rank.get((m.get("competition_stage") or {}).get("name"), 9))[0]
    match_id = target["match_id"]
    log(f"target match: {target['home_team']['home_team_name']} vs {target['away_team']['away_team_name']} ({match_id})")

    # ---- training corpus ------------------------------------------------- #
    corpus_ids = [m["match_id"] for m in matches][: args.train_matches]
    corpus: list[list[dict[str, Any]]] = []
    t0 = time.time()
    for i, mid in enumerate(corpus_ids, 1):
        corpus.append(adapter.load_events(mid))
        if i % 10 == 0:
            log(f"fetched {i}/{len(corpus_ids)} match event files ({time.time()-t0:.0f}s)")

    log("training xT (16x12 Markov)...")
    xt, iters, converged = train_xt(corpus)
    log(f"xT converged={converged} in {iters} iterations, max={xt.max():.4f}")

    log("training glass-box xG (logistic regression)...")
    xg_model, n_shots = train_xg(corpus)
    log(f"xG trained on {n_shots} shots; intercept={xg_model['intercept']}, coefs={xg_model['coefficients']}")

    # ---- target match ----------------------------------------------------- #
    raw_events = adapter.load_events(match_id)
    frames_360 = adapter.load_freeze_frames(match_id)
    home_id = next(ev["team"]["id"] for ev in raw_events
                   if ev["team"]["name"] == target["home_team"]["home_team_name"])
    ff_ids = {f["event_uuid"] for f in frames_360}
    log(f"{len(raw_events)} raw events, {len(frames_360)} 360 freeze-frames")

    model_spec = XgModelSpec(
        version="1.0.0",
        intercept=xg_model["intercept"],
        features=FEATURES,
        coefficients=xg_model["coefficients"],
        trainingMatches=len(corpus_ids),
        trainingShots=n_shots,
    )

    events = build_events(raw_events, home_id, xt)
    shots = build_shots(raw_events, home_id, xg_model, model_spec, ff_ids)
    frames = build_keyframes(raw_events, frames_360, home_id)
    xt_grid = XThreatGrid(values=grid_rows(xt), iterations=iters, converged=converged)

    caps = adapter.capabilities(match_id)
    manifest = Manifest(
        matchId=f"sb-{match_id}",
        meta=MatchMeta(
            competition=(target.get("competition") or {}).get("competition_name", "?"),
            season=(target.get("season") or {}).get("season_name", "?"),
            home=TeamRef(id=str(target["home_team"]["home_team_id"]), name=target["home_team"]["home_team_name"]),
            away=TeamRef(id=str(target["away_team"]["away_team_id"]), name=target["away_team"]["away_team_name"]),
            score=(target["home_score"], target["away_score"]),
            kickoff=f"{target.get('match_date','')} {target.get('kick_off','') or ''}".strip(),
            pitch=PitchSpec(),
        ),
        capabilities=caps,
        provenance=adapter.provenance(match_id),
        chunks=ChunkIndex(frames="frames.json"),
    )

    out = publish_bundle(args.out, manifest, events, shots, frames, xt_grid)
    log(f"published MatchBundle -> {out}")
    log(f"events={len(events.events)} shots={len(shots.shots)} keyframes={len(frames.keyframes)}")


if __name__ == "__main__":
    sys.exit(main())
