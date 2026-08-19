"""Pipeline + contract tests (method sanity checks from the plan)."""
import json
import math
from pathlib import Path

import pytest

from football_core.coords import statsbomb_to_canonical
from football_core.model import EventChunk, FrameChunk, Manifest, ShotChunk, XThreatGrid
from football_licensing.policy import POLICIES
from football_pipeline.xg_glassbox import FEATURES, score_shot

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts"
MATCHES = sorted(d for d in ARTIFACT_DIR.glob("sb-*") if d.is_dir()) if ARTIFACT_DIR.exists() else []

pytestmark = pytest.mark.skipif(not MATCHES, reason="no published artifacts — run the pipeline first")
MATCH = MATCHES[0] if MATCHES else None


def load(name: str):
    return json.loads((MATCH / name).read_text())


# --------------------------------------------------------------------------- #
def test_coords_transform():
    # StatsBomb center spot (60, 40) -> canonical origin
    assert statsbomb_to_canonical(60, 40) == (0.0, 0.0)
    # StatsBomb goal being attacked (120, 40) -> +x goal line
    assert statsbomb_to_canonical(120, 40) == (52.5, 0.0)
    # y axis flips (StatsBomb y down -> canonical y up)
    x, y = statsbomb_to_canonical(60, 0)
    assert y == 34.0


def test_manifest_schema_and_attribution():
    m = Manifest.model_validate(load("manifest.json"))
    assert m.provenance.attributionText.strip(), "artifact must carry attribution"
    assert m.provenance.sourceKey in POLICIES
    assert not m.provenance.commercialUseAllowed, "StatsBomb open must not be flagged commercial"


def test_events_schema_and_xt_deltas():
    chunk = EventChunk.model_validate(load("events.json"))
    assert len(chunk.events) > 500
    deltas = [e.xThreat for e in chunk.events if e.xThreat]
    assert deltas, "some events must carry xT deltas"
    for d in deltas:
        assert abs((d.after - d.before) - d.delta) < 1e-6


def test_xt_grid_converged_and_monotone_toward_goal():
    g = XThreatGrid.model_validate(load("xt_grid.json"))
    assert g.converged
    flat = [v for row in g.values for v in row]
    assert all(0 <= v <= 1 for v in flat)
    # threat near the attacked goal (right edge) must exceed own-half average
    right_edge = [row[-1] for row in g.values]
    left_half = [v for row in g.values for v in row[: g.cols // 2]]
    assert sum(right_edge) / len(right_edge) > sum(left_half) / len(left_half)


def test_glassbox_contributions_reconstruct_log_odds():
    chunk = ShotChunk.model_validate(load("shots.json"))
    model = chunk.model
    for s in chunk.shots:
        if not s.contributions:  # penalties
            continue
        total = model.intercept + sum(c.logOddsContribution for c in s.contributions)
        assert abs(total - s.logOdds) < 1e-2, f"contributions must reconstruct log-odds for {s.eventId}"
        assert abs(1 / (1 + math.exp(-s.logOdds)) - s.xg) < 1e-3
        assert 0 <= s.xg <= 1


def test_glassbox_score_shot_matches_published_model():
    chunk = ShotChunk.model_validate(load("shots.json"))
    model = {"intercept": chunk.model.intercept, "coefficients": chunk.model.coefficients}
    s = next(sh for sh in chunk.shots if sh.contributions)
    xg, log_odds, _, contribs = score_shot(model, {k: s.featureValues[k] for k in FEATURES})
    assert abs(xg - s.xg) < 1e-3
    assert abs(log_odds - s.logOdds) < 1e-3
    assert len(contribs) == len(FEATURES)


def test_frames_sorted_and_in_bounds():
    chunk = FrameChunk.model_validate(load("frames.json"))
    assert chunk.interpolated is True
    assert len(chunk.keyframes) > 1000
    prev = (0, -1)
    for k in chunk.keyframes:
        assert (k.period, k.t) >= prev
        prev = (k.period, k.t)
        assert -52.5 <= k.ball.x <= 52.5 and -34.0 <= k.ball.y <= 34.0


def test_commercial_build_refuses_noncommercial_source():
    from football_pipeline import publish
    from football_core.model import ChunkIndex
    m = Manifest.model_validate(load("manifest.json"))
    ev = EventChunk(events=[])
    sh = ShotChunk.model_validate(load("shots.json"))
    original = publish.COMMERCIAL_BUILD
    publish.COMMERCIAL_BUILD = True
    try:
        with pytest.raises(publish.ComplianceError):
            publish.publish_bundle("/tmp/_compliance_test", m, ev, sh)
    finally:
        publish.COMMERCIAL_BUILD = original
