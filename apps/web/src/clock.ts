// Match clock: map a single global ms value <-> (period, t-within-period).
// Period lengths are derived from the data (supports 2 periods or ET; shootout excluded).

export interface PeriodMap {
  periods: number[]         // e.g. [1, 2] or [1, 2, 3, 4]
  lengths: Record<number, number>   // period -> duration ms
  offsets: Record<number, number>   // period -> global start ms
  total: number
}

export function buildPeriodMap(samples: { period: number; t: number }[]): PeriodMap {
  const lengths: Record<number, number> = {}
  for (const s of samples) {
    if (s.period > 4) continue // shootout is not on the replay timeline
    lengths[s.period] = Math.max(lengths[s.period] ?? 0, s.t)
  }
  const periods = Object.keys(lengths).map(Number).sort((a, b) => a - b)
  const offsets: Record<number, number> = {}
  let acc = 0
  for (const p of periods) {
    offsets[p] = acc
    acc += lengths[p]
  }
  return { periods, lengths, offsets, total: acc }
}

export function toPeriodTime(pm: PeriodMap, global: number): { period: number; t: number } {
  for (let i = pm.periods.length - 1; i >= 0; i--) {
    const p = pm.periods[i]
    if (global >= pm.offsets[p]) return { period: p, t: global - pm.offsets[p] }
  }
  return { period: pm.periods[0] ?? 1, t: 0 }
}

export function toGlobal(pm: PeriodMap, period: number, t: number): number {
  return (pm.offsets[period] ?? 0) + t
}

/** Display minute with football convention offsets (45', 90', 105'). */
export function displayMinute(period: number, t: number): string {
  const base = { 1: 0, 2: 45, 3: 90, 4: 105 }[period] ?? 0
  if (period === 5) return 'pens'
  return `${Math.floor(t / 60000) + base}′`
}
