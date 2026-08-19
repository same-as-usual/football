"""FastAPI service — serves canonical MatchBundle artifacts + entitlements stub.

Free tier is static-file-shaped by design (CDN-ready); this API adds the
attribution guarantee and the future paywall boundary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from football_licensing.entitlements import resolve_entitlements

ARTIFACTS = Path(os.environ.get("ARTIFACTS_DIR", "artifacts")).resolve()
WEB_DIST = Path(os.environ.get("WEB_DIST", "apps/web/dist")).resolve()

app = FastAPI(title="football — the explorable, explainable match")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ALLOWED_CHUNKS = {"manifest.json", "events.json", "shots.json", "frames.json", "xt_grid.json"}


@app.get("/api/matches")
def list_matches() -> dict:
    index = ARTIFACTS / "index.json"
    if not index.exists():
        return {"matches": []}
    return json.loads(index.read_text())


@app.get("/api/matches/{match_id}/{chunk}")
def get_chunk(match_id: str, chunk: str):
    if chunk not in ALLOWED_CHUNKS:
        raise HTTPException(404, "unknown chunk")
    path = ARTIFACTS / match_id / chunk
    if not path.exists():
        raise HTTPException(404, "not found")
    payload = json.loads(path.read_text())
    # attribution guarantee: every manifest response must carry attribution
    if chunk == "manifest.json" and not payload.get("provenance", {}).get("attributionText"):
        raise HTTPException(500, "artifact missing attribution — refusing to serve")
    return payload


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
