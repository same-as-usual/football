"""Metrica Sports open sample adapter — continuous 25Hz tracking + events.

Coordinates: normalized [0,1], origin top-left, y down; absolute (no per-team
attacking normalization; teams swap ends at half time).
Convention: the first player column of each team's tracking file is the keeper.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import requests

from football_core.coords import PITCH_LENGTH, PITCH_WIDTH
from football_core.model import Capabilities, Provenance
from football_licensing.policy import policy_for

RAW_BASE = "https://raw.githubusercontent.com/metrica-sports/sample-data/master/data"


def norm_to_canonical(x: float, y: float) -> tuple[float, float]:
    """Metrica normalized (y down) -> canonical meters (y up)."""
    return (x - 0.5) * PITCH_LENGTH, (0.5 - y) * PITCH_WIDTH


class MetricaOpenAdapter:
    source_key = "metrica_open"

    def __init__(self, game: str = "Sample_Game_2", cache_dir: str | Path = "data/raw/metrica"):
        self.game = game
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)

    def _fetch(self, suffix: str) -> Path:
        fname = f"{self.game}_{suffix}.csv"
        local = self.cache / fname
        if not local.exists():
            r = requests.get(f"{RAW_BASE}/{self.game}/{fname}", timeout=120)
            r.raise_for_status()
            local.write_bytes(r.content)
        return local

    # ------------------------------------------------------------------ #
    def load_tracking(self, side: str) -> tuple[pd.DataFrame, list[str]]:
        """Returns (df, player_ids). df columns: Period, Frame, Time [s],
        then <pid>_x, <pid>_y per player, plus ball_x, ball_y."""
        path = self._fetch(f"RawTrackingData_{side}_Team")
        header = pd.read_csv(path, nrows=3, header=None)
        jerseys = header.iloc[1].tolist()
        cols = header.iloc[2].tolist()
        names: list[str] = []
        player_ids: list[str] = []
        i = 0
        while i < len(cols):
            c = str(cols[i])
            if c in ("Period", "Frame", "Time [s]"):
                names.append(c); i += 1
            elif c.startswith("Player"):
                pid = f"{side[0]}{jerseys[i]}"  # e.g. H11, A25
                player_ids.append(pid)
                names += [f"{pid}_x", f"{pid}_y"]; i += 2
            elif c == "Ball":
                names += ["ball_x", "ball_y"]; i += 2
            else:
                names.append(f"_skip{i}"); i += 1
        df = pd.read_csv(path, skiprows=3, header=None, names=names[: len(pd.read_csv(path, skiprows=3, nrows=1, header=None).columns)])
        return df, player_ids

    def load_events(self) -> pd.DataFrame:
        return pd.read_csv(self._fetch("RawEventsData"))

    def capabilities(self) -> Capabilities:
        return Capabilities(
            hasEvents=True,
            hasFreezeFrames=False,
            hasContinuousTracking=True,
            hasPitchControl=True,
            hasXThreat=False,
            hasGlassBoxXg=True,
            frameRateHz=25.0,
        )

    def provenance(self) -> Provenance:
        p = policy_for(self.source_key)
        return Provenance(
            sourceKey=p.source_key,
            sourceName=p.source_name,
            licenseTag=p.license_tag,
            attributionText=p.attribution_text,
            commercialUseAllowed=p.commercial_use_allowed,
            containsPersonalTrackingData=p.contains_personal_tracking_data,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def attacking_right(gk_x_mean: float) -> bool:
        """A team whose keeper averages on the left half attacks right."""
        return gk_x_mean < 0.5

    @staticmethod
    def merged_tracking(home: pd.DataFrame, away: pd.DataFrame) -> pd.DataFrame:
        away_cols = [c for c in away.columns if c.startswith("A") or c in ("Period", "Frame")]
        return home.merge(away[away_cols], on=["Period", "Frame"], how="inner")
