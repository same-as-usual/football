"""Per-source usage policy — the compliance seam.

Commercial builds MUST refuse to publish artifacts whose policy says
commercial_use_allowed=False. This is enforced in pipeline publish().
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourcePolicy:
    source_key: str
    source_name: str
    license_tag: str
    attribution_text: str
    commercial_use_allowed: bool
    contains_personal_tracking_data: bool = False
    region_restrictions: list[str] = field(default_factory=list)
    notes: str = ""


POLICIES: dict[str, SourcePolicy] = {
    "statsbomb_open": SourcePolicy(
        source_key="statsbomb_open",
        source_name="StatsBomb Open Data",
        license_tag="statsbomb-open-noncommercial",
        attribution_text=(
            "Data provided by StatsBomb (StatsBomb Open Data). "
            "https://github.com/statsbomb/open-data"
        ),
        commercial_use_allowed=False,  # bespoke LICENSE.pdf — verify before any commercial use
        contains_personal_tracking_data=False,  # 360 freeze-frames are anonymised (no player ids)
        notes="Free tier only until StatsBomb terms explicitly cleared for commercial use.",
    ),
    "metrica_open": SourcePolicy(
        source_key="metrica_open",
        source_name="Metrica Sports Sample Data",
        license_tag="metrica-sample",
        attribution_text="Tracking sample data by Metrica Sports.",
        commercial_use_allowed=False,
        contains_personal_tracking_data=False,  # anonymised sample games
    ),
    "club_football_2000_2025": SourcePolicy(
        source_key="club_football_2000_2025",
        source_name="Club Football Match Data 2000-2025 (xgabora)",
        license_tag="MIT",
        attribution_text=(
            "Match aggregates: Club Football Match Data 2000-2025 (A. Gabor, MIT), "
            "sourced from Football-Data.co.uk and ClubElo.com."
        ),
        commercial_use_allowed=True,  # MIT — league-context/Elo enrichment only (no event data)
        notes="Match-aggregate only: results, team totals, odds, Elo. Cannot power replay/xG/xT.",
    ),
}


def policy_for(source_key: str) -> SourcePolicy:
    return POLICIES[source_key]
