import { useEffect, useMemo, useRef, useState } from 'react'
import PitchStage, { type StageHandles } from './pitch/PitchStage'
import ShotInspector from './ShotInspector'
import type { CanonicalEvent, FrameChunk, Manifest, Point, Shot, ShotChunk, XThreatGrid } from './types'
import './App.css'

const API = import.meta.env.DEV ? 'http://localhost:8000' : ''

async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`)
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json()
}

const PERIOD_MS = 45 * 60 * 1000

export default function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [events, setEvents] = useState<CanonicalEvent[]>([])
  const [shotChunk, setShotChunk] = useState<ShotChunk | null>(null)
  const [frames, setFrames] = useState<FrameChunk | null>(null)
  const [xtGrid, setXtGrid] = useState<XThreatGrid | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [clock, setClock] = useState(0) // global ms across periods
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(8)
  const [showXt, setShowXt] = useState(false)
  const [selectedShot, setSelectedShot] = useState<Shot | null>(null)
  const [cfLoc, setCfLoc] = useState<Point | null>(null)

  const handlesRef = useRef<StageHandles | null>(null)

  useEffect(() => {
    ;(async () => {
      try {
        const idx = await fetchJson<{ matches: { matchId: string }[] }>('/api/matches')
        if (!idx.matches.length) { setError('No published matches — run the pipeline first.'); return }
        const id = idx.matches[0].matchId
        const [m, e, s, f, x] = await Promise.all([
          fetchJson<Manifest>(`/api/matches/${id}/manifest.json`),
          fetchJson<{ events: CanonicalEvent[] }>(`/api/matches/${id}/events.json`),
          fetchJson<ShotChunk>(`/api/matches/${id}/shots.json`),
          fetchJson<FrameChunk>(`/api/matches/${id}/frames.json`),
          fetchJson<XThreatGrid>(`/api/matches/${id}/xt_grid.json`),
        ])
        setManifest(m); setEvents(e.events); setShotChunk(s); setFrames(f); setXtGrid(x)
      } catch (err) {
        setError(String(err))
      }
    })()
  }, [])

  const maxClock = useMemo(() => {
    if (!frames?.keyframes.length) return 2 * PERIOD_MS
    const last = frames.keyframes[frames.keyframes.length - 1]
    return (last.period - 1) * PERIOD_MS + last.t
  }, [frames])

  // playback clock
  useEffect(() => {
    if (!playing) return
    let raf = 0
    let prev = performance.now()
    const tick = (now: number) => {
      setClock((c) => Math.min(maxClock, c + (now - prev) * speed))
      prev = now
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, speed, maxClock])

  // push time into pixi
  useEffect(() => {
    const period = clock < PERIOD_MS ? 1 : 2
    const t = period === 1 ? clock : clock - PERIOD_MS
    handlesRef.current?.setTime({ period, t })
  }, [clock, frames])

  useEffect(() => { handlesRef.current?.setXtVisible(showXt) }, [showXt])
  useEffect(() => { handlesRef.current?.setSelectedShot(selectedShot, cfLoc) }, [selectedShot, cfLoc])

  const currentEvents = useMemo(() => {
    const period = clock < PERIOD_MS ? 1 : 2
    const t = period === 1 ? clock : clock - PERIOD_MS
    return events
      .filter((e) => e.period === period && e.t <= t)
      .slice(-8)
      .reverse()
  }, [events, clock])

  if (error) return <div className="center error">{error}</div>
  if (!manifest || !shotChunk) return <div className="center">Loading match…</div>

  const { meta, provenance, capabilities } = manifest
  const mins = Math.floor(clock / 60000)

  return (
    <div className="app">
      <header>
        <h1>
          <span className="home">{meta.home.name}</span> {meta.score[0]}–{meta.score[1]}{' '}
          <span className="away">{meta.away.name}</span>
        </h1>
        <div className="muted">{meta.competition} · {meta.season} · {meta.kickoff}</div>
      </header>

      <div className="layout">
        <div>
          <PitchStage
            frames={frames}
            shots={shotChunk.shots}
            xtGrid={xtGrid}
            onShotClick={(s) => { setSelectedShot(s); setCfLoc(null) }}
            onCfDrag={(loc) => setCfLoc(loc)}
            handlesRef={handlesRef}
          />
          <div className="controls">
            <button onClick={() => setPlaying((p) => !p)}>{playing ? '⏸ pause' : '▶ play'}</button>
            <input
              type="range" min={0} max={maxClock} value={clock}
              onChange={(e) => setClock(Number(e.target.value))}
            />
            <span className="clock">{mins}′</span>
            <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
              {[1, 4, 8, 16, 32].map((s) => <option key={s} value={s}>{s}×</option>)}
            </select>
            <label className="toggle">
              <input type="checkbox" checked={showXt} onChange={(e) => setShowXt(e.target.checked)} />
              xT overlay
            </label>
          </div>
          {frames?.interpolated && (
            <div className="hint">
              Replay reconstructed from events + StatsBomb 360 freeze-frames (interpolated, not continuous
              tracking). Player dots appear at freeze-frame moments; ball path is interpolated between events.
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
                      {s.player} · xG {s.xg.toFixed(2)} · {s.outcome.replace(/_/g, ' ')}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
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
