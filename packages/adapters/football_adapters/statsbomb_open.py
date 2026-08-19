"""StatsBomb Open Data adapter (free tier).

Events + 360 freeze-frames. Governed by StatsBomb's bespoke LICENSE.pdf:
attribution required; commercial use NOT cleared (see licensing.policy).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from football_core.model import Capabilities, Provenance
from football_licensing.policy import policy_for

RAW_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


class StatsBombOpenAdapter:
    source_key = "statsbomb_open"

    def __init__(self, competition_id: int, season_id: int, cache_dir: str | Path = "data/raw/statsbomb"):
        self.competition_id = competition_id
        self.season_id = season_id
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def _fetch(self, rel: str) -> Any:
        local = self.cache / rel.replace("/", "_")
        if local.exists():
            return json.loads(local.read_text())
        r = requests.get(f"{RAW_BASE}/{rel}", timeout=60)
        r.raise_for_status()
        local.write_text(r.text)
        return r.json()

    # ------------------------------------------------------------------ #
    def list_matches(self) -> list[dict[str, Any]]:
        return self._fetch(f"matches/{self.competition_id}/{self.season_id}.json")

    def load_events(self, match_id: str) -> list[dict[str, Any]]:
        return self._fetch(f"events/{match_id}.json")

    def load_freeze_frames(self, match_id: str) -> list[dict[str, Any]]:
        try:
            return self._fetch(f"three-sixty/{match_id}.json")
        except requests.HTTPError:
            return []

    def load_lineups(self, match_id: str) -> list[dict[str, Any]]:
        return self._fetch(f"lineups/{match_id}.json")

    def capabilities(self, match_id: str) -> Capabilities:
        has_360 = bool(self.load_freeze_frames(match_id))
        return Capabilities(
            hasEvents=True,
            hasFreezeFrames=has_360,
            hasContinuousTracking=False,
            hasPitchControl=False,
            hasXThreat=True,
            hasGlassBoxXg=True,
        )

    def provenance(self, match_id: str) -> Provenance:  # noqa: ARG002
        p = policy_for(self.source_key)
        return Provenance(
            sourceKey=p.source_key,
            sourceName=p.source_name,
            licenseTag=p.license_tag,
            attributionText=p.attribution_text,
            commercialUseAllowed=p.commercial_use_allowed,
            containsPersonalTrackingData=p.contains_personal_tracking_data,
            regionRestrictions=p.region_restrictions,
        )
