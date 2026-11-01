// Stage 3 (director from timeline.json) + stage 4 (lip-sync from the voice-only track).
import { describe, it, expect } from 'vitest'
import { pchip } from '@engine/draw/pchip'
import { makeDirector, cutEffects, takePlan, FPS } from '@engine/draw/director'
import { mouthTrack } from '@engine/draw/lipsync'
import { renderDrawn } from '@engine/draw/render'
import { FORMATS } from '@engine/formats'
import { SAMPLE_RATE } from '@engine/ffmpeg'
import { flashFrames, loopScore } from '@engine/preflight'

const GOLDEN_TL = { punch_time: 8.24, cuts: [9.24, 10.24, 11.24, 12.44, 13.44, 14.54, 15.64], duration: 18, pause_before_punch: 2 }

describe('PCHIP camera motion', () => {
  it('passes through keys and never overshoots', () => {
    const f = pchip([0, 1, 2, 3], [1, 1.2, 1.5, 1.85])
    let prev = -Infinity
    for (let t = 0; t <= 3; t += 0.01) { const v = f(t); expect(v).toBeGreaterThanOrEqual(prev - 1e-9); expect(v).toBeLessThanOrEqual(1.85 + 1e-9); prev = v }
    expect(f(2)).toBeCloseTo(1.5)
  })
})

describe('director: built from the timeline, never a template loop', () => {
  const d = makeDirector(GOLDEN_TL)
  it('one opening shot until the punch line, then one take per cut', () => {
    expect(d.takes.map((t) => t.start)).toEqual([8.24, ...GOLDEN_TL.cuts])
    expect(d.takeAt(8.2)).toBe(-1)
    expect(d.takeAt(8.25)).toBe(0)
  })
  it('golden case plays the 8 reference takes in order, ending on the flirty smirk', () => {
    expect(d.takes.map((t) => t.ref)).toEqual([0, 1, 2, 3, 4, 5, 6, 7])
  })
  it('longer videos re-use takes in a different order, with no repeating cycle', () => {
    const p = takePlan(16)
    expect(p[0]).toBe(0)
    expect(p[p.length - 1]).toBe(7)
    const mid = p.slice(1, -1).join(',')
    for (let k = 2; k <= 6; k++) {
      const a = p.slice(1, 1 + k).join(','), b = p.slice(1 + k, 1 + 2 * k).join(',')
      expect(a === b && b.length > 0).toBe(false)
    }
    expect(mid.length).toBeGreaterThan(0)
  })
  it('opening: close on the glass, reveal wide, sip during the pause', () => {
    expect(d.state(0, 0, 0).cam.zoom).toBeGreaterThan(3)
    expect(d.state(Math.round(6.2 * FPS), 0, 0).cam.zoom).toBeLessThan(1.4)
    expect(d.state(Math.round(7.0 * FPS), 0, 0).pose.sip).toBeGreaterThan(0.9)
  })
  it('hearts only at the very end', () => {
    for (let f = 0; f < Math.round(16.1 * FPS); f += 5) expect(d.state(f, 0, 0).pose.hearts.length).toBe(0)
    expect(d.state(Math.round(17.0 * FPS), 0, 0).pose.hearts.length).toBeGreaterThan(0)
  })
  it('the punch take winks; the last take smirks', () => {
    expect(d.state(Math.round(8.7 * FPS), 0, 0).pose.winkR).toBeGreaterThan(0.9)
    expect(d.state(Math.round(16.5 * FPS), 0, 0).pose.smirk).toBeGreaterThan(0.95)
  })
  it('white flash 0.9/0.5/0.2 on the 3 frames from each cut; blur 3,7,11,7,3.5,1.5 around it', () => {
    const c = Math.round(8.24 * FPS)
    expect([0, 1, 2, 3].map((k) => cutEffects(c + k, [c]).flash)).toEqual([0.9, 0.5, 0.2, 0])
    expect([-1, 0, 1, 2, 3, 4, 5].map((k) => cutEffects(c + k, [c]).blur)).toEqual([3, 7, 11, 7, 3.5, 1.5, 0])
  })
  it('the timeline drives it: a different punch time moves every cut', () => {
    const d2 = makeDirector({ ...GOLDEN_TL, punch_time: 6, cuts: [7, 8, 9], duration: 12 })
    expect(d2.takes.map((t) => t.start)).toEqual([6, 7, 8, 9])
    expect(d2.takes.map((t) => t.ref)).toEqual([0, 1, 2, 7])
  })
})

describe('lip-sync from the voice-only track', () => {
  it('opens on speech, is fully CLOSED when the voice is silent', () => {
    const n = SAMPLE_RATE * 3
    const l = new Float32Array(n)
    for (let i = SAMPLE_RATE * 0.5; i < SAMPLE_RATE * 1.5; i++) l[i] = 0.4 * Math.sin((2 * Math.PI * 200 * i) / SAMPLE_RATE) * (0.6 + 0.4 * Math.sin(i / 900))
    const m = mouthTrack({ l, r: l }, 30, 90)
    expect(m[5].open).toBe(0)
    expect(Math.max(...m.slice(17, 44).map((x) => x.open))).toBeGreaterThan(0.6)
    for (let f = 52; f < 90; f++) expect(m[f].open).toBeLessThan(0.1)
  })
})

describe('rendering real frames', () => {
  it('flash frames on the punch line and every cut; no loop', async () => {
    const fmt = { ...FORMATS.vertical, width: 72, height: 128 }
    const frames: Uint8Array[] = []
    await renderDrawn({
      ffmpeg: '', fmt, timeline: GOLDEN_TL,
      voiceTrack: { l: new Float32Array(SAMPLE_RATE * 18), r: new Float32Array(SAMPLE_RATE * 18) },
      audioWav: '', outPartial: '',
      onFrame: (_i, c) => {
        const d = c.getContext('2d').getImageData(0, 0, 72, 128).data
        const g = new Uint8Array(72 * 128)
        for (let k = 0; k < g.length; k++) g[k] = (d[k * 4] + d[k * 4 + 1] + d[k * 4 + 2]) / 3
        frames.push(g)
      }
    })
    expect(frames.length).toBe(540)
    const want = [8.24, ...GOLDEN_TL.cuts].map((c) => Math.round(c * FPS))
    const got = flashFrames(frames)
    for (const w of want) expect(got.some((g) => Math.abs(g - w) <= 1)).toBe(true)
    expect(loopScore(frames)).toBeLessThan(0.3)
  }, 600_000)
})
