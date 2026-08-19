// Client-side glass-box xG — the playable counterfactual.
// Pure arithmetic on shipped logistic-regression coefficients: instant recompute
// on drag, no server round-trip. Mirrors football_pipeline.xg_glassbox.score_shot.

import type { FeatureContribution, Point, Shot, XgModelSpec } from './types'

const PITCH_LENGTH = 105
const GOAL_X = PITCH_LENGTH / 2
const POST_Y = 7.32 / 2
const SIGNIFICANT = 0.1

/** Recompute geometry features from a (display-coords) shot location. */
export function geometryFeatures(loc: Point, attackingRight: boolean) {
  // map display -> model coords (shooter attacks +x)
  const xm = attackingRight ? loc.x : -loc.x
  const ym = attackingRight ? loc.y : -loc.y
  const dist = Math.hypot(GOAL_X - xm, ym)
  const a1 = Math.atan2(POST_Y - ym, GOAL_X - xm)
  const a2 = Math.atan2(-POST_Y - ym, GOAL_X - xm)
  return { distance_m: dist, goal_angle_rad: Math.abs(a1 - a2) }
}

export interface XgResult {
  xg: number
  logOdds: number
  baselineXg: number
  contributions: FeatureContribution[]
}

export function scoreShot(model: XgModelSpec, features: Record<string, number>): XgResult {
  let logOdds = model.intercept
  const contributions: FeatureContribution[] = model.features.map((f) => {
    const contrib = (model.coefficients[f] ?? 0) * (features[f] ?? 0)
    logOdds += contrib
    return {
      feature: f,
      value: features[f] ?? 0,
      logOddsContribution: contrib,
      significant: Math.abs(contrib) > SIGNIFICANT,
    }
  })
  return {
    xg: 1 / (1 + Math.exp(-logOdds)),
    logOdds,
    baselineXg: 1 / (1 + Math.exp(-model.intercept)),
    contributions,
  }
}

/** What-if: move the shot to a new location, keep non-geometry features. */
export function counterfactual(model: XgModelSpec, shot: Shot, newLoc: Point): XgResult {
  const feats = { ...shot.featureValues, ...geometryFeatures(newLoc, shot.attackingRight) }
  return scoreShot(model, feats)
}
