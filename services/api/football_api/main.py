"""FastAPI service — serves canonical MatchBundle artifacts + entitlements stub.

Free tier is static-file-shaped by design (CDN-ready); this API adds the
attribution guarantee and the future paywall boundary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from football_licensing.entitlements import resolve_entitlements

ARTIFACTS = Path(os.environ.get("ARTIFACTS_DIR", "artifacts")).resolve()
WEB_DIST = Path(os.environ.get("WEB_DIST", "apps/web/dist")).resolve()

app = FastAPI(title="football — the explorable, explainable match")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=4096)  # tracking/space chunks are megabytes raw

ALLOWED_CHUNKS = {
    "manifest.json", "events.json", "shots.json", "frames.json", "xt_grid.json",
    "tracking.json", "space.json", "narrative.json",
}


@app.get("/api/matches")
def list_matches() -> dict:
    index = ARTIFACTS / "index.json"
    if not index.exists():
        return {"matches": []}
    return json.loads(index.read_text())


@app.get("/api/matches/{match_id}/card.png")
def get_card(match_id: str):
    """Server-rendered shareable match card (PNG). Must precede the generic chunk route."""
    if not re.fullmatch(r"[a-z0-9-]+", match_id):
        raise HTTPException(404, "invalid match id")
    bundle = ARTIFACTS / match_id
    if not (bundle / "manifest.json").exists():
        raise HTTPException(404, "not found")
    out = bundle / "card.png"
    if not out.exists():
        from football_api.cards import render_card
        render_card(bundle, out)
    return FileResponse(out, media_type="image/png")


@app.get("/api/matches/{match_id}/{chunk}")
def get_chunk(match_id: str, chunk: str):
    if chunk not in ALLOWED_CHUNKS:
        raise HTTPException(404, "unknown chunk")
    if not re.fullmatch(r"[a-z0-9-]+", match_id):  # defense-in-depth vs traversal
        raise HTTPException(404, "invalid match id")
    path = ARTIFACTS / match_id / chunk
    if not path.exists():
        raise HTTPException(404, "not found")
    payload = json.loads(path.read_text())
    # attribution guarantee: every manifest response must carry attribution
    if chunk == "manifest.json" and not payload.get("provenance", {}).get("attributionText"):
        raise HTTPException(500, "artifact missing attribution — refusing to serve")
    return payload


@app.post("/api/matches/{match_id}/narrative")
def make_narrative(match_id: str) -> dict:
    """Generate (and cache) the wordalised match story from structured facts."""
    if not re.fullmatch(r"[a-z0-9-]+", match_id):
        raise HTTPException(404, "invalid match id")
    bundle = ARTIFACTS / match_id
    if not (bundle / "manifest.json").exists():
        raise HTTPException(404, "not found")
    cache = bundle / "narrative.json"
    if cache.exists():
        return json.loads(cache.read_text())
    from football_narrative.llm_client import generate_narrative
    from football_narrative.wordaliser import build_match_facts

    result = generate_narrative(build_match_facts(bundle))
    cache.write_text(json.dumps(result))
    return result


@app.get("/api/me/entitlements")
def me_entitlements() -> dict:
    e = resolve_entitlements()
    return {"plan": e.plan, "features": "all-free"}


# --- static frontend (built app) ----------------------------------------- #
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):  # noqa: ARG001
        return FileResponse(WEB_DIST / "index.html")
