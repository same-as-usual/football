import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import PitchStage, { type Overlay, type StageHandles } from './pitch/PitchStage'
import ShotInspector from './ShotInspector'
import { buildPeriodMap, displayMinute, toPeriodTime, type PeriodMap } from './clock'
import type {
  CanonicalEvent, FrameChunk, Manifest, MatchListItem, Narrative, Point, Shot,
  ShotChunk, SpaceGridChunk, TrackingChunk, XThreatGrid,
} from './types'
import './App.css'

const API = import.meta.env.DEV ? 'http://localhost:8000' : ''

async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`)
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json()
}

interface Bundle {
  manifest: Manifest
  events: CanonicalEvent[]
  shotChunk: ShotChunk
  frames: FrameChunk | null
  tracking: TrackingChunk | null
  xtGrid: XThreatGrid | null
  spaceGrid: SpaceGridChunk | null
}

async function loadBundle(id: string): Promise<Bundle> {
  const manifest = await fetchJson<Manifest>(`/api/matches/${id}/manifest.json`)
  const caps = manifest.capabilities
  const [events, shotChunk, frames, tracking, xtGrid, spaceGrid] = await Promise.all([
    fetchJson<{ events: CanonicalEvent[] }>(`/api/matches/${id}/events.json`),
    fetchJson<ShotChunk>(`/api/matches/${id}/shots.json`),
    caps.hasContinuousTracking ? null : fetchJson<FrameChunk>(`/api/matches/${id}/frames.json`),
    caps.hasContinuousTracking ? fetchJson<TrackingChunk>(`/api/matches/${id}/tracking.json`) : null,
    caps.hasXThreat ? fetchJson<XThreatGrid>(`/api/matches/${id}/xt_grid.json`) : null,
    caps.hasPitchControl ? fetchJson<SpaceGridChunk>(`/api/matches/${id}/space.json`) : null,
  ])
  return { manifest, events: events.events, shotChunk, frames, tracking, xtGrid, spaceGrid }
}

export default function App() {
  const [matches, setMatches] = useState<MatchListItem[]>([])
  const [matchId, setMatchId] = useState<string | null>(null)
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [clock, setClock] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(8)
  const [overlay, setOverlay] = useState<Overlay>('none')
  const [selectedShot, setSelectedShot] = useState<Shot | null>(null)
  const [cfLoc, setCfLoc] = useState<Point | null>(null)
  const [narrative, setNarrative] = useState<Narrative | null>(null)
  const [narrativeBusy, setNarrativeBusy] = useState(false)

  const handlesRef = useRef<StageHandles | null>(null)

  useEffect(() => {
    fetchJson<{ matches: MatchListItem[] }>('/api/matches')
      .then((idx) => {
        setMatches(idx.matches)
        if (idx.matches.length) setMatchId(idx.matches[0].matchId)
        else setError('No published matches — run the pipeline first.')
      })
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!matchId) return
    setBundle(null); setNarrative(null); setSelectedShot(null); setCfLoc(null)
    setClock(0); setPlaying(false); setOverlay('none')
    loadBundle(matchId).then(setBundle).catch((e) => setError(String(e)))
  }, [matchId])

  const periodMap: PeriodMap = useMemo(() => {
    if (!bundle) return buildPeriodMap([])
    const samples = bundle.tracking
      ? bundle.tracking.frames.map((f) => ({ period: f[0] as number, t: f[1] as number }))
      : (bundle.frames?.keyframes ?? [])
    return buildPeriodMap(samples)
  }, [bundle])

  // playback clock
  useEffect(() => {
    if (!playing || periodMap.total === 0) return
    let raf = 0
    let prev = performance.now()
    const tick = (now: number) => {
      setClock((c) => Math.min(periodMap.total, c + (now - prev) * speed))
      prev = now
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, speed, periodMap])

  useEffect(() => {
    if (periodMap.total === 0) return
    handlesRef.current?.setTime(toPeriodTime(periodMap, clock))
  }, [clock, periodMap, bundle])

  useEffect(() => { handlesRef.current?.setOverlay(overlay) }, [overlay, bundle])
  useEffect(() => { handlesRef.current?.setSelectedShot(selectedShot, cfLoc) }, [selectedShot, cfLoc])

  const currentEvents = useMemo(() => {
    if (!bundle) return []
    const { period, t } = toPeriodTime(periodMap, clock)
    return bundle.events
      .filter((e) => e.period === period && e.t <= t)
      .slice(-8)
      .reverse()
  }, [bundle, clock, periodMap])

  const generateNarrative = useCallback(async () => {
    if (!matchId) return
    setNarrativeBusy(true)
    try {
      const r = await fetch(`${API}/api/matches/${matchId}/narrative`, { method: 'POST' })
      if (!r.ok) throw new Error(`narrative: ${r.status}`)
      setNarrative(await r.json())
    } catch (e) {
      setError(String(e))
    } finally {
      setNarrativeBusy(false)
    }
  }, [matchId])

  if (error) return <div className="center error">{error}</div>
  if (!bundle) return <div className="center">Loading match…</div>

  const { manifest, shotChunk } = bundle
  const { meta, provenance, capabilities } = manifest
  const pt = toPeriodTime(periodMap, clock)

  const overlays: { id: Overlay; label: string; enabled: boolean }[] = [
    { id: 'none', label: 'no overlay', enabled: true },
    { id: 'xt', label: 'xThreat', enabled: !!bundle.xtGrid },
    { id: 'pitch-control', label: 'pitch control', enabled: !!bundle.spaceGrid },
    { id: 'voronoi', label: 'Voronoi', enabled: !!bundle.tracking },
  ]

  return (
    <div className="app">
      <header>
        <div className="header-row">
          <h1>
            <span className="home">{meta.home.name}</span> {meta.score[0]}–{meta.score[1]}{' '}
            <span className="away">{meta.away.name}</span>
          </h1>
          <select className="match-picker" value={matchId ?? ''} onChange={(e) => setMatchId(e.target.value)}>
            {matches.map((m) => (
              <option key={m.matchId} value={m.matchId}>
                {m.home} {m.score[0]}–{m.score[1]} {m.away} · {m.competition}
              </option>
            ))}
          </select>
        </div>
        <div className="muted">
          {meta.competition} · {meta.season}{meta.kickoff ? ` · ${meta.kickoff}` : ''}
          {capabilities.hasContinuousTracking && ' · continuous tracking'}
        </div>
      </header>

      <div className="layout">
        <div>
          <PitchStage
            key={matchId}
            frames={bundle.frames}
            tracking={bundle.tracking}
            shots={shotChunk.shots}
            xtGrid={bundle.xtGrid}
            spaceGrid={bundle.spaceGrid}
            onShotClick={(s) => { setSelectedShot(s); setCfLoc(null) }}
            onCfDrag={(loc) => setCfLoc(loc)}
            handlesRef={handlesRef}
          />
          <div className="controls">
            <button onClick={() => setPlaying((p) => !p)}>{playing ? '⏸ pause' : '▶ play'}</button>
            <input
              type="range" min={0} max={periodMap.total || 1} value={clock}
              onChange={(e) => setClock(Number(e.target.value))}
            />
            <span className="clock">{displayMinute(pt.period, pt.t)}</span>
            <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
              {[1, 4, 8, 16, 32].map((s) => <option key={s} value={s}>{s}×</option>)}
            </select>
            <select value={overlay} onChange={(e) => setOverlay(e.target.value as Overlay)}>
              {overlays.map((o) => (
                <option key={o.id} value={o.id} disabled={!o.enabled}>{o.label}</option>
              ))}
            </select>
          </div>
          {bundle.frames?.interpolated && (
            <div className="hint">
              Replay reconstructed from events + 360 freeze-frames (interpolated, not continuous tracking).
            </div>
          )}
          {bundle.spaceGrid && overlay === 'pitch-control' && (
            <div className="hint">
              Spearman (2018) pitch control — <span className="home">blue = {meta.home.name}</span>,{' '}
              <span className="away">red = {meta.away.name}</span>. Computed every 5s of game time from
              25 Hz tracking with documented physics (vmax 5 m/s, reaction 0.7 s, λ 4.3).
            </div>
          )}
        </div>

        <aside>
          {selectedShot ? (
            <ShotInspector
              shot={selectedShot}
              model={shotChunk.model}
              cfLoc={cfLoc}
              onReset={() => setCfLoc(null)}
              onClose={() => { setSelectedShot(null); setCfLoc(null) }}
            />
          ) : (
            <div className="panel">
              <h3>Shots — click a marker</h3>
              <ul className="shotlist">
                {shotChunk.shots.map((s) => (
                  <li key={s.eventId} onClick={() => { setSelectedShot(s); setCfLoc(null) }}>
                    <span className={`dot ${s.team}`} />
                    <span className={s.outcome === 'goal' ? 'goal' : ''}>
                      {displayMinute(s.period, s.t)} {s.player} · xG {s.xg.toFixed(2)} · {s.outcome.replace(/_/g, ' ')}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="panel">
            <div className="panel-head">
              <h3>Match story</h3>
              <a className="link" href={`${API}/api/matches/${matchId}/card.png`} target="_blank" rel="noreferrer">
                share card ↗
              </a>
            </div>
            {narrative ? (
              <>
                {narrative.text.split('\n\n').map((p, i) => <p key={i} className="story">{p}</p>)}
                <div className="hint">generated by {narrative.backend} from structured match facts only</div>
              </>
            ) : (
              <button onClick={generateNarrative} disabled={narrativeBusy}>
                {narrativeBusy ? 'writing…' : '✦ generate match story'}
              </button>
            )}
          </div>

          <div className="panel">
            <h3>Live feed</h3>
            <ul className="feed">
              {currentEvents.map((e) => (
                <li key={e.eventId}>
                  <span className={`dot ${e.team}`} />
                  {e.type.replace(/_/g, ' ')} — {e.player ?? ''}
                  {e.xThreat && Math.abs(e.xThreat.delta) > 0.02 && (
                    <span className={e.xThreat.delta > 0 ? 'xt-up' : 'xt-down'}>
                      {' '}xT {e.xThreat.delta > 0 ? '+' : ''}{e.xThreat.delta.toFixed(3)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>

      <footer className="attribution">
        {provenance.attributionText}
        {!capabilities.hasContinuousTracking && ' · Event-plane data (no continuous tracking).'}
      </footer>
    </div>
  )
}
