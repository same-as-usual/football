"""Wordalisation: turn MatchBundle artifacts into STRUCTURED metadata, then prose.

Anti-hallucination design (per WSC Sports / ShotsGPT findings): the LLM only ever
sees structured facts extracted from the published artifacts — never free prose —
and is instructed to use nothing beyond them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_match_facts(bundle_dir: str | Path) -> dict[str, Any]:
    """Extract a compact, structured fact sheet from published artifacts."""
    d = Path(bundle_dir)
    manifest = json.loads((d / "manifest.json").read_text())
    shots = json.loads((d / "shots.json").read_text())
    events = json.loads((d / "events.json").read_text())

    home = manifest["meta"]["home"]["name"]
    away = manifest["meta"]["away"]["name"]

    def team_name(side: str) -> str:
        return home if side == "home" else away

    # Period 5 = penalty shootout: kicks are not match goals and not match xG.
    open_play = [s for s in shots["shots"] if s["period"] <= 4]
    shootout = [s for s in shots["shots"] if s["period"] == 5]
    goals = [s for s in open_play if s["outcome"] == "goal"]
    xg_totals = {"home": 0.0, "away": 0.0}
    for s in open_play:
        xg_totals[s["team"]] += s["xg"]

    big_chances = sorted(
        (s for s in open_play if s["outcome"] != "goal"),
        key=lambda s: -s["xg"],
    )[:3]

    PERIOD_OFFSET_MIN = {1: 0, 2: 45, 3: 90, 4: 105}

    def minute(s: dict) -> int:
        return s["t"] // 60000 + PERIOD_OFFSET_MIN.get(s["period"], 0)

    # biggest xT swings (threat created by passes/carries)
    xt_moves = [e for e in events["events"] if e.get("xThreat")]
    top_threat = sorted(xt_moves, key=lambda e: -e["xThreat"]["delta"])[:3]

    return {
        "competition": manifest["meta"]["competition"],
        "season": manifest["meta"]["season"],
        "home": home,
        "away": away,
        "finalScore": manifest["meta"]["score"],
        "xg": {home: round(xg_totals["home"], 2), away: round(xg_totals["away"], 2)},
        "wentToExtraTime": any(s["period"] in (3, 4) for s in shots["shots"]),
        "penaltyShootout": (
            {
                home: sum(1 for s in shootout if s["team"] == "home" and s["outcome"] == "goal"),
                away: sum(1 for s in shootout if s["team"] == "away" and s["outcome"] == "goal"),
            }
            if shootout else None
        ),
        "shotCounts": {
            home: sum(1 for s in open_play if s["team"] == "home"),
            away: sum(1 for s in open_play if s["team"] == "away"),
        },
        "goals": [
            {
                "team": team_name(g["team"]), "player": g["player"],
                "period": g["period"], "minute": minute(g), "xg": g["xg"],
            }
            for g in sorted(goals, key=lambda g: (g["period"], g["t"]))
        ],
        "bigMissedChances": [
            {"team": team_name(s["team"]), "player": s["player"], "xg": s["xg"],
             "outcome": s["outcome"], "minute": minute(s)}
            for s in big_chances
        ],
        "topThreatMoments": [
            {"team": team_name(e["team"]), "player": e.get("player"),
             "type": e["type"], "xtGained": e["xThreat"]["delta"], "minute": minute(e)}
            for e in top_threat
        ],
        "attribution": manifest["provenance"]["attributionText"],
    }


SYSTEM_PROMPT = """You are a football match storyteller writing for engaged fans.
You will receive a STRUCTURED fact sheet extracted from verified match data.

Rules (strict):
- Use ONLY the facts provided. Never invent events, players, scores, or context
  that is not in the fact sheet. If a detail is missing, do not mention it.
- Translate numbers into meaning: an xG of 0.05 is "a hopeful effort from range";
  0.4+ is "a chance he really should score". xT gains show who created danger.
- 3 short paragraphs, ~150 words total: (1) the result and its shape,
  (2) the decisive moments (goals, big misses), (3) what the underlying numbers
  say about who deserved what.
- Tone: vivid but factual — a knowledgeable friend, not a tabloid."""


def build_prompt(facts: dict[str, Any]) -> str:
    return (
        "Write the match story from this fact sheet.\n\n"
        f"```json\n{json.dumps(facts, indent=1)}\n```"
    )
