# football — the explorable, explainable match

A free, browser-based football match you can **scrub, interrogate, and play with**:

- **Animated replay** — ball path + StatsBomb 360 freeze-frame positions on a PixiJS (WebGL) pitch, with timeline scrubber and playback speeds.
- **xT overlay** — a 16×12 Expected Threat grid (Markov model, trained from event data), plus per-pass/carry xT deltas in the live feed.
- **Glass-box xG** — plain logistic regression; every shot's xG decomposes into per-feature log-odds contributions (β·x). The waterfall bars *are* the model — no black box.
- **Playable counterfactuals** — drag a shot anywhere on the pitch; xG and its explanation recompute instantly, client-side, from the shipped coefficients.
- **Attribution & compliance built in** — every artifact carries provenance; commercial builds refuse to publish data not cleared for commercial use.

- **Space overlays** — velocity-aware **Spearman (2018) pitch control** computed from 25 Hz tracking
  (documented physics: vmax 5 m/s, reaction 0.7 s, λ 4.3, 0.04 s integration steps), plus live
  client-side **Voronoi** tessellation during playback.
- **Auto-generated match story** — LLM "wordalisation" of structured match facts (Claude behind a
  swappable `LLMClient`, deterministic template fallback with zero hallucination risk), plus a
  server-rendered **shareable PNG match card**.

Demo bundles:
- **UEFA Euro 2020 final, Italy 1–1 England** (StatsBomb Open Data: events + 360 freeze-frames,
  extra time + shootout handled) — xT, glass-box xG, interpolated replay.
- **Metrica Sample Game 2** (continuous 25 Hz tracking) — full 22-player animated replay,
  pitch control, Voronoi.

## Architecture (commercial-upgradeable by construction)

```
packages/core        canonical MatchBundle model (pydantic) — the only contract
packages/adapters    data-source adapters (StatsBomb open today; paid feeds later)
packages/licensing   source policies, attribution, entitlements stub (paywall seam)
packages/pipeline    offline compute: xT Markov grid, glass-box xG, replay keyframes
services/api         FastAPI: artifact chunks, entitlements, SPA hosting
apps/web             React + TypeScript + PixiJS frontend
artifacts/           published MatchBundle JSON (CDN-shaped, immutable)
```

Provider names appear **only** in `packages/adapters` and `packages/licensing/policy.py`.
Swapping StatsBomb Open Data for a licensed Opta/Stats Perform feed is an adapter +
policy entry — zero changes to core, API, or frontend.

## Quickstart

```bash
# Python (uses uv; plain venv+pip works too)
uv venv .venv && uv pip install -e ".[dev]"

# 1a. Event-plane pipeline (downloads Euro 2020 open data, trains xT + xG, publishes artifacts)
.venv/bin/python -m football_pipeline.run --competition 55 --season 43

# 1b. Tracking pipeline (Metrica sample: continuous replay + Spearman pitch control)
.venv/bin/python -m football_pipeline.run_metrica

# 2. Build the frontend
cd apps/web && npm install && npm run build && cd ../..

# 3. Serve (API + built app on :8000)
.venv/bin/uvicorn football_api.main:app --host 0.0.0.0 --port 8000
```

Tests: `.venv/bin/python -m pytest tests/ -q` (contract, convergence, log-odds
reconstruction, compliance-refusal).

## Data & licensing

- **StatsBomb Open Data** — free research use with attribution; **not cleared for
  commercial use** (bespoke license). The publish step enforces this: a commercial
  build refuses these artifacts.
- Continuous tracking (true pitch control) requires a tracking source
  (Metrica/SkillCorner samples — Phase 2); StatsBomb 360 gives freeze-frames at events,
  which is what the replay honestly labels as interpolated.

## Narrative backends

`packages/narrative` picks the backend at runtime: with `ANTHROPIC_API_KEY` (or an
`ant auth` profile token) set, stories are written by Claude from a **structured fact
sheet only** (anti-hallucination: the model never sees free prose, and penalty
shootouts/extra time are pre-resolved in the facts). Without credentials, a
deterministic template narrator produces a factual story at zero cost.

## Roadmap

- ~~Phase 2: pitch control + Voronoi overlays~~ ✅
- ~~Phase 3: narratives + shareable cards~~ ✅ (playable pitch-control counterfactuals pending)
- **Phase 4**: full-competition ingestion, CDN artifacts, real entitlements/paywall, paid-feed adapters, SHAP option.
