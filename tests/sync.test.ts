// Stage 1 (audio brain) + stage 5 (preflight) on GENERATED sounds, so they run anywhere.
// The golden-case acceptance test (owner's real files) is in tests/golden.test.ts.
import { describe, it, expect, beforeAll } from 'vitest'
import { createRequire } from 'node:module'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { encodeWav, runTool, SAMPLE_RATE, type Stereo } from '@engine/ffmpeg'
import { samp } from '@engine/audio/analysis'
import { findPhrases, groupUnits, firstDownbeat, CUT_OFFSETS } from '@engine/audio/brain'
import { buildAudio, renderDraft, type AudioPlan } from '@engine/project'
import { FORMATS } from '@engine/formats'

const require = createRequire(import.meta.url)
const ff: string = require('ffmpeg-static')

const silence = (s: number): Stereo => ({ l: new Float32Array(samp(s)), r: new Float32Array(samp(s)) })
function speak(x: Stereo, a: number, b: number, amp = 0.3) {
  let ph = 0
  for (let i = samp(a); i < samp(b); i++) {
    const t = i / SAMPLE_RATE
    ph += (2 * Math.PI * (180 + 30 * Math.sin(2 * Math.PI * 3 * t))) / SAMPLE_RATE
    const v = amp * (0.5 + 0.5 * Math.sin(2 * Math.PI * 6 * t)) * (Math.sin(ph) + 0.5 * Math.sin(2 * ph) + 0.3 * Math.sin(3 * ph))
    x.l[i] += v; x.r[i] += v
  }
}
function bed(x: Stereo, from: number, to: number, level: number) {
  for (let i = samp(from); i < Math.min(x.l.length, samp(to)); i++) {
    const v = level * 0.25 * Math.sin((2 * Math.PI * 330 * i) / SAMPLE_RATE)
    x.l[i] += v; x.r[i] += v
  }
  for (let t = from; t < to; t += 0.5) for (let i = 0; i < samp(0.12); i++) {
    const d = samp(t) + i
    if (d >= x.l.length) break
    const v = level * Math.exp(-i / samp(0.04)) * Math.sin((2 * Math.PI * 110 * i) / SAMPLE_RATE)
    x.l[d] += v; x.r[d] += v
  }
}

const dir = mkdtempSync(join(tmpdir(), 'catty-brain-'))
const VOICE = join(dir, 'voice.wav')
const INTRO = join(dir, 'intro.wav')
const CHORUS = join(dir, 'chorus.wav')
const DOWNBEAT = 0.1
let plan: AudioPlan

beforeAll(async () => {
  // Three units: set-up (0.5–1.6), a second line after a 1.2 s pause (2.8–3.4), the punch line (4.5–5.3).
  const v = silence(6)
  speak(v, 0.5, 1.0); speak(v, 1.2, 1.6) // one unit (gap 0.2 s < 0.9 s)
  speak(v, 2.8, 3.4)
  speak(v, 4.5, 5.3, 0.15) // quieter punch line → must be levelled up
  writeFileSync(VOICE, encodeWav(v))
  const intro = silence(10)
  bed(intro, 0, 10, 0.15)
  writeFileSync(INTRO, encodeWav(intro))
  const ch = silence(12)
  bed(ch, DOWNBEAT, 12, 0.35) // first downbeat 0.10 s in
  writeFileSync(CHORUS, encodeWav(ch))
  plan = await buildAudio({
    ffmpeg: ff, workDir: join(dir, 'work'), voice: VOICE,
    music: [{ path: INTRO, role: 'intro' }, { path: CHORUS, role: 'punchline' }],
    pauseSec: 2, punchUnits: null, mdx: null, style: 'draw'
  })
}, 120_000)

describe('audio brain: phrases → units', () => {
  it('groups words into units; a gap of ≥ 0.9 s splits units', () => {
    expect(groupUnits([[0.5, 1.0], [1.2, 1.6], [2.8, 3.4], [4.5, 5.3]])).toEqual([[0.5, 1.6], [2.8, 3.4], [4.5, 5.3]])
    expect(plan.phrases.map((p) => [p.startSec, p.endSec].map((x) => Math.round(x * 10) / 10))).toEqual([[0.5, 1.6], [2.8, 3.4], [4.5, 5.3]])
  })
  it('finds phrases like silencedetect -38 dB / 0.18 s', () => {
    const x = silence(2)
    speak(x, 0.3, 0.6); speak(x, 0.7, 1.0); speak(x, 1.5, 1.8)
    const ph = findPhrases(x)
    expect(ph.length).toBe(2) // the 0.1 s gap merges, the 0.5 s gap splits
  })
  it('defaults to the LAST unit as the punch line, flagged as a guess', () => {
    expect(plan.punchUnits).toEqual([2])
    expect(plan.punchGuessed).toBe(true)
  })
})

describe('audio brain: placement (reference rules)', () => {
  const tl = () => plan.timeline
  it('punch unit starts exactly on the punch time 8.24', () => {
    expect(tl().punch_time).toBe(8.24)
    const p = tl().placed.find((x) => x.unit === 2)!
    expect(Math.abs(p.dest[0] - 8.24)).toBeLessThan(0.001)
  })
  it('the units before it keep their natural gaps and end exactly 2.0 s before it', () => {
    const [a, b] = tl().placed
    expect(b.dest[0] - a.dest[1]).toBeCloseTo(2.8 - 1.6, 1)
    expect(tl().pause_before_punch).toBeCloseTo(2.0, 2)
  })
  it('levels the quieter punch line up (never the quietest, capped at +6 dB)', () => {
    const g = tl().placed.find((x) => x.unit === 2)!.gain
    expect(g).toBeGreaterThan(1.3)
    expect(g).toBeLessThanOrEqual(2.0)
  })
  it('chorus first downbeat lands on the punch time; intro ends where the chorus starts', () => {
    // firstDownbeat works on a 10 ms grid (as in the reference), so allow ±15 ms
    expect(Math.abs(tl().chorus_downbeat! - DOWNBEAT)).toBeLessThanOrEqual(0.015)
    expect(Math.abs(tl().chorus_start! + tl().chorus_downbeat! - 8.24)).toBeLessThan(0.001)
    expect(Math.abs(tl().intro_offset! - (10 - tl().chorus_start!))).toBeLessThan(0.002)
    expect(Math.abs(plan.syncErrorMs!)).toBeLessThanOrEqual(20)
  })
  it('cuts are the reference offsets after the punch line', () => {
    expect(tl().cuts).toEqual(CUT_OFFSETS.map((d) => Math.round((8.24 + d) * 100) / 100))
    expect(tl().duration).toBe(18)
  })
  it('voice ≥ 8 dB over the music; loudness −14…−16.5 LUFS; true peak ≤ −1 dB', () => {
    expect(tl().voice_over_music_db).toBeGreaterThanOrEqual(8)
    expect(plan.loudness.lufs).toBeGreaterThanOrEqual(-16.5)
    expect(plan.loudness.lufs).toBeLessThanOrEqual(-14)
    expect(plan.loudness.truePeakDb).toBeLessThanOrEqual(-1)
  })
  it('firstDownbeat finds the strongest early rise', () => {
    const c = silence(1)
    bed(c, 0.23, 1, 0.4)
    expect(firstDownbeat(c)).toBeCloseTo(0.23, 1)
  })
})

describe('manual timeline editing still works on top of the automatic sync', () => {
  it('moving the music by hand really moves its beat (+250 ms)', async () => {
    const chorusClip = plan.editor.clips.find((c) => c.path === CHORUS)!
    const manual = await buildAudio({
      ffmpeg: ff, workDir: join(dir, 'work-manual'), voice: VOICE,
      music: [{ path: INTRO, role: 'intro' }, { path: CHORUS, role: 'punchline' }],
      pauseSec: 2, punchUnits: [2], mdx: null,
      manualMusic: plan.editor.clips.map((c) => ({ path: c.path, dstFromPunchSec: c.dstSec - plan.punchAtSec + 0.25, inSec: c.inSec, outSec: c.outSec }))
    })
    expect(manual.editor.manual).toBe(true)
    expect(manual.syncErrorMs!).toBeGreaterThan(200)
    expect(manual.syncErrorMs!).toBeLessThan(300)
    expect(chorusClip).toBeTruthy()
  }, 120_000)
})

describe('render + preflight (both shapes)', () => {
  for (const fmt of [FORMATS.vertical, FORMATS.landscape]) {
    it(`${fmt.label}: native ${fmt.width}×${fmt.height}, all preflight checks green`, async () => {
      const small = { ...fmt, width: fmt.width / 4, height: fmt.height / 4 } // quarter size keeps the test fast
      const out = join(dir, `out-${fmt.id}.mp4`)
      const r = await renderDraft({ ffmpeg: ff, workDir: join(dir, 'work'), outFile: out, plan, visual: { type: 'drawn' }, fmt: small })
      const info = await runTool(ff, ['-i', out]).catch((e: Error) => ({ stderr: e.message }))
      expect(info.stderr).toContain(`${small.width}x${small.height}`)
      const failed = r.qa.filter((q) => !q.ok).map((q) => q.text)
      expect(failed).toEqual([])
    }, 900_000)
  }
})
