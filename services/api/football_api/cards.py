"""Shareable match card — server-rendered PNG (mplsoccer, MIT-licensed).

Score header + xG-scaled shot map + attribution footer. Cached per match.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mplsoccer import Pitch  # noqa: E402

HOME_C, AWAY_C, GOAL_C = "#4f8ff7", "#ef5350", "#00e676"


def render_card(bundle_dir: str | Path, out_path: str | Path) -> Path:
    d = Path(bundle_dir)
    manifest = json.loads((d / "manifest.json").read_text())
    shots = json.loads((d / "shots.json").read_text())
    meta = manifest["meta"]

    pitch = Pitch(pitch_type="custom", pitch_length=105, pitch_width=68,
                  pitch_color="#0e3b1e", line_color="#9fd4a8", linewidth=1.5)
    fig, ax = pitch.draw(figsize=(9, 6.4))
    fig.patch.set_facecolor("#101418")

    match_shots = [s for s in shots["shots"] if s["period"] <= 4]  # exclude shootout
    for s in match_shots:
        x = s["location"]["x"] + 52.5  # canonical -> mplsoccer custom (0..105, 0..68)
        y = s["location"]["y"] + 34.0
        is_goal = s["outcome"] == "goal"
        ax.scatter(
            x, y, s=80 + s["xg"] * 900,
            c=GOAL_C if is_goal else (HOME_C if s["team"] == "home" else AWAY_C),
            edgecolors="#111111", linewidths=1, alpha=0.9 if is_goal else 0.75,
            zorder=3 if is_goal else 2,
        )

    xg = {"home": 0.0, "away": 0.0}
    for s in match_shots:
        xg[s["team"]] += s["xg"]

    fig.suptitle(
        f"{meta['home']['name']} {meta['score'][0]}–{meta['score'][1]} {meta['away']['name']}",
        color="white", fontsize=20, fontweight="bold", y=0.985,
    )
    ax.set_title(
        f"{meta['competition']} · {meta['season']}   |   "
        f"xG {xg['home']:.2f} – {xg['away']:.2f}   ·   dot size = shot quality (xG)",
        color="#9aa0a6", fontsize=10, pad=8,
    )
    fig.text(0.5, 0.015, manifest["provenance"]["attributionText"],
             color="#9aa0a6", fontsize=7, ha="center")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out
