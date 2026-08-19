"""Canonical MatchBundle models (pydantic v2) — the single source of truth.

These models define the JSON contract published to `artifacts/{matchId}/`
and consumed by the frontend. Frontend TS types mirror these shapes.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------------------- #
# Provenance / licensing (the compliance seam)
# --------------------------------------------------------------------------- #
class Provenance(BaseModel):
    sourceKey: str
    sourceName: str
    licenseTag: str
    attributionText: str
    commercialUseAllowed: bool
    containsPersonalTrackingData: bool = False
    regionRestrictions: list[str] = Field(default_factory=list)


class Capabilities(BaseModel):
    hasEvents: bool = False
    hasFreezeFrames: bool = False
    hasContinuousTracking: bool = False
    hasPitchControl: bool = False
    hasXThreat: bool = False
    hasGlassBoxXg: bool = False
    frameRateHz: Optional[float] = None


# --------------------------------------------------------------------------- #
# Match meta
# --------------------------------------------------------------------------- #
class TeamRef(BaseModel):
    id: str
    name: str


class PitchSpec(BaseModel):
    length: float = 105.0
    width: float = 68.0


class MatchMeta(BaseModel):
    competition: str
    season: str
    home: TeamRef
    away: TeamRef
    score: tuple[int, int]
    kickoff: Optional[str] = None
    pitch: PitchSpec = Field(default_factory=PitchSpec)


class ChunkIndex(BaseModel):
    events: str = "events.json"
    shots: str = "shots.json"
    frames: Optional[str] = "frames.json"  # keyframes (event-plane) or tracking.json (continuous)
    spaceGrids: Optional[str] = None
    freezeFrames: Optional[str] = None
    narrative: Optional[str] = None


class Manifest(BaseModel):
    schemaVersion: str = SCHEMA_VERSION
    matchId: str
    meta: MatchMeta
    capabilities: Capabilities
    provenance: Provenance
    chunks: ChunkIndex = Field(default_factory=ChunkIndex)


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
class Point(BaseModel):
    x: float
    y: float


class XThreatDelta(BaseModel):
    before: float
    after: float
    delta: float


class CanonicalEvent(BaseModel):
    eventId: str
    t: int  # ms from period start
    period: int
    type: str  # pass | carry | shot | ...
    team: Literal["home", "away"]
    player: Optional[str] = None
    playerId: Optional[str] = None
    recipient: Optional[str] = None
    start: Optional[Point] = None
    end: Optional[Point] = None
    outcome: Optional[str] = None
    xThreat: Optional[XThreatDelta] = None
    freezeFrameRef: Optional[str] = None


class EventChunk(BaseModel):
    events: list[CanonicalEvent]


# --------------------------------------------------------------------------- #
# Glass-box xG
# --------------------------------------------------------------------------- #
class XgModelSpec(BaseModel):
    type: Literal["logistic_regression"] = "logistic_regression"
    version: str
    intercept: float
    features: list[str]
    coefficients: dict[str, float]  # shipped to client for live counterfactuals
    trainingMatches: int
    trainingShots: int


class FeatureContribution(BaseModel):
    feature: str
    value: float
    logOddsContribution: float
    significant: bool  # |contribution| > 0.1 log-odds (ShotsGPT threshold)


class CounterfactualSpec(BaseModel):
    editable: list[str] = Field(default_factory=lambda: ["location"])
    recompute: Literal["client", "server", "wasm"] = "client"


class Shot(BaseModel):
    eventId: str
    t: int
    period: int
    team: Literal["home", "away"]
    player: str
    location: Point
    attackingRight: bool  # True if shooting at +x goal in canonical coords
    outcome: str  # goal | saved | off_t | ...
    xg: float
    logOdds: float
    baselineXg: float
    contributions: list[FeatureContribution]
    featureValues: dict[str, float]
    counterfactualSpec: CounterfactualSpec = Field(default_factory=CounterfactualSpec)
    freezeFrameRef: Optional[str] = None


class ShotChunk(BaseModel):
    model: XgModelSpec
    shots: list[Shot]


# --------------------------------------------------------------------------- #
# Replay frames (sparse/interpolated for event-plane; continuous for tracking)
# --------------------------------------------------------------------------- #
class PlayerDot(BaseModel):
    x: float
    y: float
    team: Literal["home", "away", "unknown"]
    keeper: bool = False
    actor: bool = False


class Keyframe(BaseModel):
    t: int  # ms from period start
    period: int
    ball: Point
    players: list[PlayerDot] = Field(default_factory=list)
    eventRef: Optional[str] = None


class FrameChunk(BaseModel):
    interpolated: bool
    frameRateHz: Optional[float] = None
    keyframes: list[Keyframe]


# --------------------------------------------------------------------------- #
# Continuous tracking (compact flat-array format — kilobytes matter at 5+ Hz)
# --------------------------------------------------------------------------- #
class TrackingPlayer(BaseModel):
    pid: str
    team: Literal["home", "away"]
    num: int
    keeper: bool = False


class TrackingChunk(BaseModel):
    """frames: [period, t_ms, ball_x, ball_y, p0_x, p0_y, p1_x, p1_y, ...]
    aligned to `players`; None where a player is off-pitch."""
    interpolated: bool = False
    frameRateHz: float
    players: list[TrackingPlayer]
    frames: list[list[Optional[float]]]


# --------------------------------------------------------------------------- #
# Space grids (pitch control) — values flat row-major, row 0 = y min
# --------------------------------------------------------------------------- #
class SpaceSnapshot(BaseModel):
    period: int
    t: int  # ms from period start
    values: list[float]  # P(home controls cell), flat row-major


class SpaceGridChunk(BaseModel):
    kind: Literal["pitch_control"] = "pitch_control"
    cols: int
    rows: int
    physics: dict[str, float]  # documented Spearman params used
    snapshots: list[SpaceSnapshot]


# --------------------------------------------------------------------------- #
# xThreat grid (published once per match for the overlay)
# --------------------------------------------------------------------------- #
class XThreatGrid(BaseModel):
    cols: int = 16
    rows: int = 12
    values: list[list[float]]  # rows x cols, row 0 = bottom (y min), col 0 = x min
    iterations: int
    converged: bool
