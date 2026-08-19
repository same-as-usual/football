// Mirrors packages/core/football_core/model.py — the canonical JSON contract.
// The frontend depends ONLY on these shapes; it never imports a provider name.

export interface Point { x: number; y: number }

export interface Provenance {
  sourceKey: string
  sourceName: string
  licenseTag: string
  attributionText: string
  commercialUseAllowed: boolean
  containsPersonalTrackingData: boolean
  regionRestrictions: string[]
}

export interface Capabilities {
  hasEvents: boolean
  hasFreezeFrames: boolean
  hasContinuousTracking: boolean
  hasPitchControl: boolean
  hasXThreat: boolean
  hasGlassBoxXg: boolean
  frameRateHz: number | null
}

export interface Manifest {
  schemaVersion: string
  matchId: string
  meta: {
    competition: string
    season: string
    home: { id: string; name: string }
    away: { id: string; name: string }
    score: [number, number]
    kickoff: string | null
    pitch: { length: number; width: number }
  }
  capabilities: Capabilities
  provenance: Provenance
}

export interface XThreatDelta { before: number; after: number; delta: number }

export interface CanonicalEvent {
  eventId: string
  t: number
  period: number
  type: string
  team: 'home' | 'away'
  player?: string
  recipient?: string
  start?: Point
  end?: Point
  outcome?: string
  xThreat?: XThreatDelta
}

export interface FeatureContribution {
  feature: string
  value: number
  logOddsContribution: number
  significant: boolean
}

export interface XgModelSpec {
  type: string
  version: string
  intercept: number
  features: string[]
  coefficients: Record<string, number>
  trainingMatches: number
  trainingShots: number
}

export interface Shot {
  eventId: string
  t: number
  period: number
  team: 'home' | 'away'
  player: string
  location: Point
  attackingRight: boolean
  outcome: string
  xg: number
  logOdds: number
  baselineXg: number
  contributions: FeatureContribution[]
  featureValues: Record<string, number>
}

export interface ShotChunk { model: XgModelSpec; shots: Shot[] }

export interface PlayerDot { x: number; y: number; team: 'home' | 'away' | 'unknown'; keeper: boolean; actor: boolean }

export interface Keyframe { t: number; period: number; ball: Point; players: PlayerDot[]; eventRef?: string }

export interface FrameChunk { interpolated: boolean; keyframes: Keyframe[] }

export interface XThreatGrid { cols: number; rows: number; values: number[][]; iterations: number; converged: boolean }
