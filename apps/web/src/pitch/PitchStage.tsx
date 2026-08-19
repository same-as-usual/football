// PixiJS pitch stage: animated replay (ball + 360 freeze-frame dots),
// xT overlay, shot markers, and drag-to-counterfactual.
import { useEffect, useRef } from 'react'
import { Application, Container, Graphics, Text } from 'pixi.js'
import type { FrameChunk, Point, Shot, XThreatGrid } from '../types'

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

export interface StageHandles {
  setTime: (periodT: { period: number; t: number } | null) => void
  setXtVisible: (v: boolean) => void
  setSelectedShot: (shot: Shot | null, cfLoc?: Point | null) => void
}

interface Props {
  frames: FrameChunk | null
  shots: Shot[]
  xtGrid: XThreatGrid | null
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
    // goal mouth
    g.rect(Math.min(px(gx), px(gx + 2 * s)), py(3.66), 2 * SCALE, 7.32 * SCALE).stroke({ width: 2, color: 0xffffff })
  }
}

export default function PitchStage({ frames, shots, xtGrid, onShotClick, onCfDrag, handlesRef }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const propsRef = useRef({ onShotClick, onCfDrag })
  propsRef.current = { onShotClick, onCfDrag }

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

      // ---- xT overlay (attacking -> right) ---------------------------- //
      const xtLayer = new Container(); xtLayer.visible = false; app.stage.addChild(xtLayer)
      if (xtGrid) {
        const max = Math.max(...xtGrid.values.flat(), 1e-6)
        const cw = (L / xtGrid.cols) * SCALE, ch = (W / xtGrid.rows) * SCALE
        const g = new Graphics()
        for (let r = 0; r < xtGrid.rows; r++)
          for (let c = 0; c < xtGrid.cols; c++) {
            const v = xtGrid.values[r][c] / max
            g.rect(px(-L / 2) + c * cw, py(W / 2) + (xtGrid.rows - 1 - r) * ch, cw, ch)
              .fill({ color: 0xff9800, alpha: v * 0.55 })
          }
        xtLayer.addChild(g)
        const lbl = new Text({ text: 'xT overlay — attacking →', style: { fill: 0xffe0b2, fontSize: 12 } })
        lbl.position.set(MARGIN, 4); xtLayer.addChild(lbl)
      }

      // ---- shot markers ------------------------------------------------ //
      const shotLayer = new Container(); app.stage.addChild(shotLayer)
      for (const s of shots) {
        const m = new Graphics()
        const r = 4 + Math.sqrt(s.xg) * 10
        m.circle(0, 0, r).fill({ color: s.outcome === 'goal' ? COLORS.goal : COLORS.shot, alpha: 0.85 })
          .stroke({ width: 1.5, color: 0x222222 })
        m.position.set(px(s.location.x), py(s.location.y))
        m.eventMode = 'static'; m.cursor = 'pointer'
        m.on('pointertap', () => propsRef.current.onShotClick(s))
        shotLayer.addChild(m)
      }

      // ---- replay layer (ball + freeze-frame dots) --------------------- //
      const playerLayer = new Container(); app.stage.addChild(playerLayer)
      const ball = new Graphics()
      ball.circle(0, 0, 5).fill(COLORS.ball).stroke({ width: 1.5, color: 0x333333 })
      ball.visible = false
      app.stage.addChild(ball)

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
        const mx = (p.x - MARGIN) / SCALE - L / 2
        const my = W / 2 - (p.y - MARGIN) / SCALE
        const cx = Math.max(-L / 2, Math.min(L / 2, mx))
        const cy = Math.max(-W / 2, Math.min(W / 2, my))
        cf.position.set(px(cx), py(cy))
        propsRef.current.onCfDrag({ x: Math.round(cx * 100) / 100, y: Math.round(cy * 100) / 100 })
      })

      // ---- imperative handles ------------------------------------------ //
      const kfs = frames?.keyframes ?? []
      handlesRef.current = {
        setXtVisible: (v) => { xtLayer.visible = v },
        setSelectedShot: (shot, cfLoc) => {
          if (!shot) { cf.visible = false; return }
          const loc = cfLoc ?? shot.location
          cf.visible = true
          cf.position.set(px(loc.x), py(loc.y))
        },
        setTime: (pt) => {
          if (!pt || kfs.length === 0) { ball.visible = false; playerLayer.removeChildren(); return }
          // binary search last keyframe with period,t <= target
          const key = (k: { period: number; t: number }) => k.period * 4_000_000 + k.t
          const target = key(pt)
          let lo = 0, hi = kfs.length - 1, idx = -1
          while (lo <= hi) {
            const mid = (lo + hi) >> 1
            if (key(kfs[mid]) <= target) { idx = mid; lo = mid + 1 } else hi = mid - 1
          }
          if (idx < 0) { ball.visible = false; playerLayer.removeChildren(); return }
          const a = kfs[idx]
          const b = kfs[idx + 1]
          let bx = a.ball.x, by = a.ball.y
          if (b && b.period === a.period && b.t > a.t && b.t - a.t < 6000) {
            const f = Math.min(1, (pt.t - a.t) / (b.t - a.t))
            bx = a.ball.x + (b.ball.x - a.ball.x) * f
            by = a.ball.y + (b.ball.y - a.ball.y) * f
          }
          ball.visible = true
          ball.position.set(px(bx), py(by))
          // 360 freeze-frame dots near the current keyframe
          playerLayer.removeChildren()
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
        },
      }
    })()

    return () => {
      destroyed = true
      handlesRef.current = null
      try { app.destroy(true, { children: true }) } catch { /* not yet inited */ }
      host.replaceChildren()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frames, shots, xtGrid])

  return <div ref={hostRef} style={{ lineHeight: 0, borderRadius: 12, overflow: 'hidden' }} />
}
