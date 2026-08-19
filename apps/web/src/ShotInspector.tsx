// Glass-box xG inspector: per-feature log-odds waterfall + live counterfactual.
import type { Point, Shot, XgModelSpec } from './types'
import { counterfactual, type XgResult } from './xgClient'

const LABELS: Record<string, string> = {
  distance_m: 'Distance (m)',
  goal_angle_rad: 'Goal angle (rad)',
  is_header: 'Header',
  under_pressure: 'Under pressure',
  is_open_play: 'Open play',
  first_time: 'First-time',
}

function Waterfall({ result }: { result: XgResult }) {
  const items = result.contributions
  const max = Math.max(...items.map((c) => Math.abs(c.logOddsContribution)), 0.5)
  // dedicated label column so bars never overlap text
  const labelW = 104, valueW = 44, rowH = 26, w = 300
  const chartW = w - labelW - valueW
  const mid = labelW + chartW / 2
  return (
    <svg width={w} height={items.length * rowH + 8} style={{ display: 'block' }}>
      <line x1={mid} y1={0} x2={mid} y2={items.length * rowH} stroke="#555" strokeDasharray="3 3" />
      {items.map((c, i) => {
        const len = (Math.abs(c.logOddsContribution) / max) * (chartW / 2 - 4)
        const pos = c.logOddsContribution >= 0
        return (
          <g key={c.feature} transform={`translate(0, ${i * rowH})`}>
            <rect
              x={pos ? mid : mid - len} y={5} width={Math.max(len, 1)} height={14} rx={3}
              fill={pos ? '#00c853' : '#ff5252'} opacity={c.significant ? 0.95 : 0.35}
            />
            <text x={4} y={16} fill="#ccc" fontSize={11}>{LABELS[c.feature] ?? c.feature}</text>
            <text x={w - 4} y={16} fill={c.significant ? '#fff' : '#888'} fontSize={11} textAnchor="end">
              {c.logOddsContribution >= 0 ? '+' : ''}{c.logOddsContribution.toFixed(2)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

interface Props {
  shot: Shot
  model: XgModelSpec
  cfLoc: Point | null
  onReset: () => void
  onClose: () => void
}

export default function ShotInspector({ shot, model, cfLoc, onReset, onClose }: Props) {
  const moved = !!cfLoc && (cfLoc.x !== shot.location.x || cfLoc.y !== shot.location.y)
  // Show the published (pipeline) values until the user actually drags —
  // avoids sub-0.001 rounding drift between pipeline and client geometry.
  const live: XgResult = moved
    ? counterfactual(model, shot, cfLoc)
    : { xg: shot.xg, logOdds: shot.logOdds, baselineXg: shot.baselineXg, contributions: shot.contributions }
  return (
    <div className="panel inspector">
      <div className="panel-head">
        <strong>{shot.player}</strong>
        <button onClick={onClose}>×</button>
      </div>
      <div className="xg-big">
        xG <span className={moved ? 'cf' : ''}>{live.xg.toFixed(3)}</span>
        {moved && <span className="orig"> (was {shot.xg.toFixed(3)})</span>}
      </div>
      <div className="muted">
        {shot.outcome.replace(/_/g, ' ')} · P{shot.period} {Math.floor(shot.t / 60000)}′ · baseline {live.baselineXg.toFixed(3)}
      </div>
      <p className="hint">
        {moved
          ? 'Counterfactual: shot moved — xG recomputed live in your browser.'
          : 'Drag the pink marker on the pitch to ask “what if the shot came from here?”'}
      </p>
      {moved && <button className="link" onClick={onReset}>reset to actual location</button>}
      <h4>Why this number — log-odds contributions</h4>
      <Waterfall result={live} />
      <p className="hint">
        Glass-box logistic regression (β·x per feature, trained on {model.trainingShots} shots
        from {model.trainingMatches} matches). No black box: these bars ARE the model.
      </p>
    </div>
  )
}
