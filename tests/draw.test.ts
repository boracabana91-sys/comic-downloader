import { describe, it, expect } from 'vitest'
import { pchip } from '@engine/draw/pchip'
import { makeDirector, cutTimes, cutEffects } from '@engine/draw/director'
import { mouthTrack } from '@engine/draw/lipsync'
import { renderDrawn, FPS } from '@engine/draw/render'
import { FORMATS } from '@engine/formats'
import { SAMPLE_RATE } from '@engine/ffmpeg'

describe('PCHIP camera motion', () => {
  it('passes through keys and never overshoots', () => {
    const f = pchip([0, 1, 2, 3], [1, 1.2, 1.5, 1.85])
    expect(f(0)).toBeCloseTo(1)
    expect(f(2)).toBeCloseTo(1.5)
    let prev = -Infinity
    for (let t = 0; t <= 3; t += 0.01) {
      const v = f(t)
      expect(v).toBeGreaterThanOrEqual(prev - 1e-9) // monotone data → monotone motion
      expect(v).toBeLessThanOrEqual(1.85 + 1e-9)
      prev = v
    }
  })
  it('keeps moving between keys (no dead stops mid-shot)', () => {
    const f = pchip([0, 1, 2], [0, 1, 2])
    expect(f(1.01) - f(0.99)).toBeGreaterThan(0.015)
  })
})

describe('director timing (matches the reference rhythm)', () => {
  const dir = makeDirector({ durationSec: 11, punchSec: 4.82, phrases: [{ start: 0.4, end: 1.8 }, { start: 2.1, end: 2.8 }, { start: 4.82, end: 6.1 }] })
  it('first cut is exactly on the punch line, then one every second', () => {
    expect(dir.cuts[0]).toBeCloseTo(4.82)
    for (let i = 1; i < dir.cuts.length; i++) expect(dir.cuts[i] - dir.cuts[i - 1]).toBeCloseTo(1)
    expect(cutTimes(4.82, 11)).toEqual(dir.cuts)
  })
  it('one continuous shot before the punch line, pushing in', () => {
    expect(dir.takeAt(4.8)).toBe(-1)
    expect(dir.takeAt(4.83)).toBe(0)
    const a = dir.state(0.5, { open: 0, wide: 0.5 }).cam.zoom
    const b = dir.state(4.7, { open: 0, wide: 0.5 }).cam.zoom
    expect(b).toBeGreaterThan(a + 0.5)
  })
  it('the punch-line take is a close-up with a wink and a laugh', () => {
    const s = dir.state(4.82 + 0.4, { open: 0, wide: 0.5 })
    expect(s.cam.zoom).toBeGreaterThan(2.4)
    expect(s.pose.winkR).toBeGreaterThan(0.9)
    expect(s.pose.grin).toBeGreaterThan(0.9)
    expect(s.pose.hearts.length).toBeGreaterThan(0)
  })
  it('mouth stays symmetric unless the smirk asks otherwise', () => {
    const s = dir.state(1.0, { open: 0.5, wide: 0.5 })
    expect(s.pose.open).toBe(0.5)
    expect(s.pose.smirk).toBeGreaterThanOrEqual(0)
  })
  it('3-frame white flash and blur around each cut', () => {
    const c = Math.round(4.82 * FPS)
    expect(cutEffects(c, [c]).flash).toBeCloseTo(0.85)
    expect(cutEffects(c + 2, [c]).flash).toBeCloseTo(0.2)
    expect(cutEffects(c + 3, [c]).flash).toBe(0)
    expect(cutEffects(c - 1, [c]).blur).toBe(11)
    expect(cutEffects(c + 10, [c]).blur).toBe(0)
  })
})

describe('lip-sync', () => {
  it('opens fast on speech and closes more slowly', () => {
    const n = SAMPLE_RATE * 2
    const l = new Float32Array(n)
    for (let i = SAMPLE_RATE * 0.5; i < SAMPLE_RATE; i++) l[i] = 0.4 * Math.sin((2 * Math.PI * 200 * i) / SAMPLE_RATE)
    const m = mouthTrack({ l, r: l }, 30, 60)
    expect(m[5].open).toBe(0)
    expect(m[17].open).toBeGreaterThan(0.6) // ~2 frames after speech starts
    expect(m[31].open).toBeGreaterThan(0) // still closing after speech stops
    expect(m[45].open).toBe(0)
  })
})

describe('drawing real frames', () => {
  it('draws the opening, the punch-line flash and a close-up', async () => {
    const got: { i: number; bright: number }[] = []
    const fmt = { ...FORMATS.vertical, width: 180, height: 320 }
    const punch = 4.82
    const pf = Math.round(punch * FPS)
    await renderDrawn({
      ffmpeg: '', fmt, durationSec: 8, punchSec: punch, phrases: [{ start: 0.4, end: 1.8 }, { start: punch, end: 6 }],
      voiceTrack: { l: new Float32Array(SAMPLE_RATE * 8), r: new Float32Array(SAMPLE_RATE * 8) },
      audioWav: '', outPartial: '', onlyFrames: [10, pf, pf + 15],
      onFrame: (i, canvas) => {
        const d = canvas.getContext('2d').getImageData(0, 0, 180, 320).data
        let s = 0
        for (let k = 0; k < d.length; k += 4) s += d[k] + d[k + 1] + d[k + 2]
        got.push({ i, bright: s / (d.length / 4) / 3 })
      }
    })
    expect(got).toHaveLength(3)
    expect(got[1].bright).toBeGreaterThan(got[0].bright + 60) // white flash on the punch line
    expect(got[2].bright).toBeGreaterThan(40) // a real picture, not black
  }, 60_000)
})
