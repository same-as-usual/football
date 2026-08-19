"""Publish canonical MatchBundle artifacts — with compliance enforcement.

Commercial builds refuse to publish artifacts whose source policy says
commercialUseAllowed=False. Every artifact carries provenance/attribution.
"""
from __future__ import annotations

import json
from pathlib import Path

from football_core.model import (
    EventChunk, FrameChunk, Manifest, ShotChunk, SpaceGridChunk, TrackingChunk, XThreatGrid,
)
from football_licensing.entitlements import COMMERCIAL_BUILD


class ComplianceError(RuntimeError):
    pass


def publish_bundle(
    out_dir: str | Path,
    manifest: Manifest,
    events: EventChunk,
    shots: ShotChunk,
    frames: FrameChunk | None = None,
    xt_grid: XThreatGrid | None = None,
    tracking: TrackingChunk | None = None,
    space_grids: SpaceGridChunk | None = None,
) -> Path:
    if not manifest.provenance.attributionText.strip():
        raise ComplianceError("Refusing to publish artifact without attribution text.")
    if COMMERCIAL_BUILD and not manifest.provenance.commercialUseAllowed:
        raise ComplianceError(
            f"Source '{manifest.provenance.sourceKey}' is not cleared for commercial use."
        )

    out = Path(out_dir) / manifest.matchId
    out.mkdir(parents=True, exist_ok=True)

    (out / "manifest.json").write_text(manifest.model_dump_json())
    (out / "events.json").write_text(events.model_dump_json(exclude_none=True))
    (out / "shots.json").write_text(shots.model_dump_json(exclude_none=True))
    if frames is not None:
        (out / "frames.json").write_text(frames.model_dump_json(exclude_none=True))
    if xt_grid is not None:
        (out / "xt_grid.json").write_text(xt_grid.model_dump_json())
    if tracking is not None:
        (out / "tracking.json").write_text(tracking.model_dump_json())
    if space_grids is not None:
        (out / "space.json").write_text(space_grids.model_dump_json())

    # top-level index of published matches
    index_path = Path(out_dir) / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"matches": []}
    entry = {
        "matchId": manifest.matchId,
        "home": manifest.meta.home.name,
        "away": manifest.meta.away.name,
        "score": list(manifest.meta.score),
        "competition": manifest.meta.competition,
        "season": manifest.meta.season,
    }
    index["matches"] = [m for m in index["matches"] if m["matchId"] != manifest.matchId] + [entry]
    index_path.write_text(json.dumps(index, indent=1))
    return out
