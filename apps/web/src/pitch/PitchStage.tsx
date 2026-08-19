// PixiJS pitch stage: replay (event keyframes OR continuous tracking),
// overlays (xT, Spearman pitch control, Voronoi), shot markers, drag counterfactual.
import { useEffect, useRef } from 'react'
import { Application, Container, Graphics, Text } from 'pixi.js'
import { Delaunay } from 'd3-delaunay'
import type { FrameChunk, Point, Shot, SpaceGridChunk, TrackingChunk, XThreatGrid } from '../types'

const L = 105, W = 68
const SCALE = 8.2
const MARGIN = 24
export const STAGE_W = L * SCALE + MARGIN * 2
export const STAGE_H = W * SCALE + MARGIN * 2

const px = (x: number) => MARGIN + (x + L / 2) * SCALE
const py = (y: number) => MARGIN + (W / 2 - y) * SCALE // canonical y up -> screen y down

const COLORS = {
  pitch: 0x0e3b1e, line: 0x9fd4a8, home: 0x4f8ff7, away: 0xef5350,
  ball: 0xffffff, shot: 0xffc107, goal: 0x00e676, cf: 0xff80ab,
}

export type Overlay = 'none' | 'xt' | 'pitch-control' | 'voronoi'

export interface StageHandles {
  setTime: (pt: { period: number; t: number } | null) => void
  setOverlay: (o: Overlay) => void
  setSelectedShot: (shot: Shot | null, cfLoc?: Point | null) => void
}

interface Props {
  frames: FrameChunk | null          // event-plane keyframes (interpolated)
  tracking: TrackingChunk | null     // continuous tracking (flat arrays)
  shots: Shot[]
  xtGrid: XThreatGrid | null
  spaceGrid: SpaceGridChunk | null   // pitch-control snapshots
  onShotClick: (shot: Shot) => void
  onCfDrag: (loc: Point) => void
  handlesRef: React.MutableRefObject<StageHandles | null>
}

function drawPitch(g: Graphics) {
  g.rect(0, 0, STAGE_W, STAGE_H).fill(COLORS.pitch)
  const line = { width: 2, color: COLORS.line, alpha: 0.9 }
  g.rect(px(-L / 2), py(W / 2), L * SCALE, W * SCALE).stroke(line)
  g.moveTo(px(0), py(W / 2)).lineTo(px(0), py(-W / 2)).stroke(line)
  g.circle(px(0), py(0), 9.15 * SCALE).stroke(line)
  for (const s of [1, -1]) {
    const gx = (L / 2) * s
    g.rect(Math.min(px(gx), px(gx - 16.5 * s)), py(20.16), 16.5 * SCALE, 40.32 * SCALE).stroke(line)
    g.rect(Math.min(px(gx), px(gx - 5.5 * s)), py(9.16), 5.5 * SCALE, 18.32 * SCALE).stroke(line)
    g.circle(px(gx - 11 * s), py(0), 2).fill(COLORS.line)
    g.rect(Math.min(px(gx), px(gx + 2 * s)), py(3.66), 2 * SCALE, 7.32 * SCALE).stroke({ width: 2, color: 0xffffff })
  }
}

// mix red (0, away) -> transparent (0.5) -> blue (1, home)
function pcColor(v: number): { color: number; alpha: number } {
  return v >= 0.5
    ? { color: COLORS.home, alpha: (v - 0.5) * 1.4 }
    : { color: COLORS.away, alpha: (0.5 - v) * 1.4 }
}

export default function PitchStage(props: Props) {
  const { frames, tracking, shots, xtGrid, spaceGrid, handlesRef } = props
  const hostRef = useRef<HTMLDivElement>(null)
  const cbRef = useRef({ onShotClick: props.onShotClick, onCfDrag: props.onCfDrag })
  cbRef.current = { onShotClick: props.onShotClick, onCfDrag: props.onCfDrag }

  useEffect(() => {
    if (!hostRef.current) return
    let destroyed = false
    const app = new Application()
    const host = hostRef.current

    ;(async () => {
      await app.init({ width: STAGE_W, height: STAGE_H, antialias: true, background: COLORS.pitch })
      if (destroyed) { app.destroy(true); return }
      host.appendChild(app.canvas)

      const pitchG = new Graphics(); drawPitch(pitchG); app.stage.addChild(pitchG)

      // ---- overlay layers --------------------------------------------- //
      const overlayLayer = new Container(); app.stage.addChild(overlayLayer)
      const xtG = new Graphics(); const pcG = new Graphics(); const vorG = new Graphics()
      overlayLayer.addChild(pcG, vorG, xtG)
      let overlay: Overlay = 'none'
      let lastPcIdx = -1

      if (xtGrid) {
        const max = Math.max(...xtGrid.values.flat(), 1e-6)
        const cw = (L / xtGrid.cols) * SCALE, ch = (W / xtGrid.rows) * SCALE
        for (let r = 0; r < xtGrid.rows; r++)
          for (let c = 0; c < xtGrid.cols; c++) {
            const v = xtGrid.values[r][c] / max
            xtG.rect(px(-L / 2) + c * cw, py(W / 2) + (xtGrid.rows - 1 - r) * ch, cw, ch)
              .fill({ color: 0xff9800, alpha: v * 0.55 })
          }
        const lbl = new Text({ text: 'xT — attacking →', style: { fill: 0xffe0b2, fontSize: 12 } })
        lbl.position.set(MARGIN, 4); xtG.addChild(lbl)
      }
      xtG.visible = pcG.visible = vorG.visible = false

      const drawPitchControl = (pt: { period: number; t: number }) => {
        if (!spaceGrid) return
        const snaps = spaceGrid.snapshots
        // nearest snapshot by (period, t)
        const key = (p: number, t: number) => p * 10_000_000 + t
        const target = key(pt.period, pt.t)
        let lo = 0, hi = snaps.length - 1, idx = 0
        while (lo <= hi) {
          const mid = (lo + hi) >> 1
          if (key(snaps[mid].period, snaps[mid].t) <= target) { idx = mid; lo = mid + 1 } else hi = mid - 1
        }
        if (idx === lastPcIdx) return
        lastPcIdx = idx
        const snap = snaps[idx]
        pcG.clear()
        const cw = (L / spaceGrid.cols) * SCALE, ch = (W / spaceGrid.rows) * SCALE
        for (let r = 0; r < spaceGrid.rows; r++)
          for (let c = 0; c < spaceGrid.cols; c++) {
            const v = snap.values[r * spaceGrid.cols + c]
            const { color, alpha } = pcColor(v)
            if (alpha < 0.04) continue
            pcG.rect(px(-L / 2) + c * cw, py(W / 2) + (spaceGrid.rows - 1 - r) * ch, cw, ch)
              .fill({ color, alpha: Math.min(alpha, 0.65) })
          }
      }

      const drawVoronoi = (pts: { x: number; y: number; team: string }[]) => {
        vorG.clear()
        if (pts.length < 4) return
        const delaunay = Delaunay.from(pts, (p: { x: number }) => px(p.x), (p: { y: number }) => py(p.y))
        const vor = delaunay.voronoi([px(-L / 2), py(W / 2), px(L / 2), py(-W / 2)])
        for (let i = 0; i < pts.length; i++) {
          const cell = vor.cellPolygon(i)
          if (!cell) continue
          const color = pts[i].team === 'home' ? COLORS.home : COLORS.away
          vorG.poly(cell.flat()).fill({ color, alpha: 0.16 }).stroke({ width: 1, color, alpha: 0.5 })
        }
      }

      // ---- shot markers ------------------------------------------------ //
      const shotLayer = new Container(); app.stage.addChild(shotLayer)
      for (const s of shots) {
        if (s.period > 4) continue // shootout kicks aren't on the pitch timeline
        const m = new Graphics()
        const r = 4 + Math.sqrt(s.xg) * 10
        m.circle(0, 0, r).fill({ color: s.outcome === 'goal' ? COLORS.goal : COLORS.shot, alpha: 0.85 })
          .stroke({ width: 1.5, color: 0x222222 })
        m.position.set(px(s.location.x), py(s.location.y))
        m.eventMode = 'static'; m.cursor = 'pointer'
        m.on('pointertap', () => cbRef.current.onShotClick(s))
        shotLayer.addChild(m)
      }

      // ---- replay entities ---------------------------------------------- //
      const playerLayer = new Container(); app.stage.addChild(playerLayer)
      const ball = new Graphics()
      ball.circle(0, 0, 5).fill(COLORS.ball).stroke({ width: 1.5, color: 0x333333 })
      ball.visible = false
      app.stage.addChild(ball)

      // continuous tracking: persistent sprite per player w/ jersey number
      interface PSprite { c: Container; g: Graphics }
      const pSprites: PSprite[] = []
      if (tracking) {
        for (const p of tracking.players) {
          const c = new Container()
          const g = new Graphics()
          g.circle(0, 0, 7).fill(p.team === 'home' ? COLORS.home : COLORS.away)
            .stroke({ width: p.keeper ? 2.5 : 1, color: p.keeper ? 0xffeb3b : 0x111111 })
          const t = new Text({ text: String(p.num), style: { fill: 0xffffff, fontSize: 8, fontWeight: 'bold' } })
          t.anchor.set(0.5)
          c.addChild(g, t)
          c.visible = false
          playerLayer.addChild(c)
          pSprites.push({ c, g })
        }
      }

      // ---- counterfactual marker (draggable) ---------------------------- //
      const cf = new Graphics()
      cf.circle(0, 0, 11).fill({ color: COLORS.cf, alpha: 0.9 }).stroke({ width: 2, color: 0xffffff })
      cf.visible = false; cf.eventMode = 'static'; cf.cursor = 'grab'
      app.stage.addChild(cf)
      let dragging = false
      cf.on('pointerdown', () => { dragging = true; cf.cursor = 'grabbing' })
      app.stage.eventMode = 'static'
      app.stage.hitArea = app.screen
      app.stage.on('pointerup', () => { dragging = false; cf.cursor = 'grab' })
      app.stage.on('pointerupoutside', () => { dragging = false })
      app.stage.on('pointermove', (e) => {
        if (!dragging || !cf.visible) return
        const p = e.global
        const cx = Math.max(-L / 2, Math.min(L / 2, (p.x - MARGIN) / SCALE - L / 2))
        const cy = Math.max(-W / 2, Math.min(W / 2, W / 2 - (p.y - MARGIN) / SCALE))
        cf.position.set(px(cx), py(cy))
        cbRef.current.onCfDrag({ x: Math.round(cx * 100) / 100, y: Math.round(cy * 100) / 100 })
      })

      // ---- time -> scene ------------------------------------------------ //
      const kfs = frames?.keyframes ?? []
      const tFrames = tracking?.frames ?? []
      const nPlayers = tracking?.players.length ?? 0
      const key = (p: number, t: number) => p * 10_000_000 + t

      const bsearch = (get: (i: number) => number, n: number, target: number) => {
        let lo = 0, hi = n - 1, idx = -1
        while (lo <= hi) {
          const mid = (lo + hi) >> 1
          if (get(mid) <= target) { idx = mid; lo = mid + 1 } else hi = mid - 1
        }
        return idx
      }

      const setTimeTracking = (pt: { period: number; t: number }) => {
        const target = key(pt.period, pt.t)
        const idx = bsearch((i) => key(tFrames[i][0] as number, tFrames[i][1] as number), tFrames.length, target)
        if (idx < 0) { ball.visible = false; pSprites.forEach((s) => (s.c.visible = false)); return }
        const a = tFrames[idx]
        const b = tFrames[idx + 1]
        let f = 0
        if (b && b[0] === a[0] && (b[1] as number) > (a[1] as number)) {
          f = Math.min(1, (pt.t - (a[1] as number)) / ((b[1] as number) - (a[1] as number)))
        }
        const lerp = (i: number): number | null => {
          const av = a[i] as number | null
          const bv = b ? (b[i] as number | null) : null
          if (av == null) return null
          if (bv == null || f === 0) return av
          return av + (bv - av) * f
        }
        const bx = lerp(2), by = lerp(3)
        ball.visible = bx != null
        if (bx != null && by != null) ball.position.set(px(bx), py(by))
        const vorPts: { x: number; y: number; team: string }[] = []
        for (let i = 0; i < nPlayers; i++) {
          const x = lerp(4 + i * 2), y = lerp(5 + i * 2)
          const sp = pSprites[i]
          if (x == null || y == null) { sp.c.visible = false; continue }
          sp.c.visible = true
          sp.c.position.set(px(x), py(y))
          vorPts.push({ x, y, team: tracking!.players[i].team })
        }
        if (overlay === 'voronoi') drawVoronoi(vorPts)
        if (overlay === 'pitch-control') drawPitchControl(pt)
      }

      const setTimeKeyframes = (pt: { period: number; t: number }) => {
        const target = key(pt.period, pt.t)
        const idx = bsearch((i) => key(kfs[i].period, kfs[i].t), kfs.length, target)
        playerLayer.removeChildren()
        if (idx < 0) { ball.visible = false; return }
        const a = kfs[idx], b = kfs[idx + 1]
        let bx = a.ball.x, by = a.ball.y
        if (b && b.period === a.period && b.t > a.t && b.t - a.t < 6000) {
          const f = Math.min(1, (pt.t - a.t) / (b.t - a.t))
          bx += (b.ball.x - bx) * f; by += (b.ball.y - by) * f
        }
        ball.visible = true
        ball.position.set(px(bx), py(by))
        const dt = Math.abs(pt.t - a.t)
        if (a.players.length > 0 && dt < 1500) {
          const alpha = Math.max(0.25, 1 - dt / 1500)
          const g = new Graphics()
          for (const p of a.players) {
            const color = p.team === 'home' ? COLORS.home : p.team === 'away' ? COLORS.away : 0xaaaaaa
            g.circle(px(p.x), py(p.y), p.actor ? 7 : 6)
              .fill({ color, alpha })
              .stroke({ width: p.keeper ? 2.5 : 1, color: p.keeper ? 0xffeb3b : 0x111111, alpha })
          }
          playerLayer.addChild(g)
        }
      }

      let lastPt: { period: number; t: number } | null = null
      handlesRef.current = {
        setOverlay: (o) => {
          overlay = o
          xtG.visible = o === 'xt'
          pcG.visible = o === 'pitch-control'
          vorG.visible = o === 'voronoi'
          lastPcIdx = -1
          if (lastPt) (tracking ? setTimeTracking : setTimeKeyframes)(lastPt)
        },
        setSelectedShot: (shot, cfLoc) => {
          if (!shot) { cf.visible = false; return }
          const loc = cfLoc ?? shot.location
          cf.visible = true
          cf.position.set(px(loc.x), py(loc.y))
        },
        setTime: (pt) => {
          lastPt = pt
          if (!pt) { ball.visible = false; return }
          if (tracking) setTimeTracking(pt)
          else setTimeKeyframes(pt)
        },
      }
    })()

    return () => {
      destroyed = true
      handlesRef.current = null
      try { app.destroy(true, { children: true }) } catch { /* not inited */ }
      host.replaceChildren()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frames, tracking, shots, xtGrid, spaceGrid])

  return <div ref={hostRef} style={{ lineHeight: 0, borderRadius: 12, overflow: 'hidden' }} />
}
