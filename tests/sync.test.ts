// The brief's required tests: punch-line voice onset and music hit within ±1 frame at 30 fps,
// loudness, and native renders in both 9:16 and 16:9. Uses generated sounds (no copyrighted files).
import { describe, it, expect, beforeAll } from 'vitest'
import { createRequire } from 'node:module'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { encodeWav, decodeAudio, toMono, runTool, SAMPLE_RATE, type Stereo } from '@engine/ffmpeg'
import { findHits, findPhrases, sec, samp } from '@engine/audio/analysis'
import { planTimeline } from '@engine/audio/timeline'
import { buildAudio, renderDraft, type AudioPlan } from '@engine/project'
import { measureLoudness } from '@engine/loudness'
import { FORMATS } from '@engine/formats'

const require = createRequire(import.meta.url)
const ff: string = require('ffmpeg-static')
const FRAME_MS = 1000 / 30

function silence(s: number): Stereo {
  return { l: new Float32Array(samp(s)), r: new Float32Array(samp(s)) }
}

/** A voice-like buzz (harmonics + wobble) between `a` and `b` seconds. */
function speak(x: Stereo, a: number, b: number) {
  let ph = 0
  for (let i = samp(a); i < samp(b); i++) {
    const t = i / SAMPLE_RATE
    const f = 180 + 30 * Math.sin(2 * Math.PI * 3 * t)
    ph += (2 * Math.PI * f) / SAMPLE_RATE
    const env = 0.5 + 0.5 * Math.sin(2 * Math.PI * 6 * t)
    const v = 0.3 * env * (Math.sin(ph) + 0.5 * Math.sin(2 * ph) + 0.3 * Math.sin(3 * ph))
    x.l[i] += v
    x.r[i] += v
  }
}

/** Steady music bed with beats; optional dip and a big hit. */
function beats(x: Stereo, from: number, to: number, level: number) {
  for (let t = from; t < to; t += 0.5) {
    for (let i = 0; i < samp(0.12); i++) {
      const d = samp(t) + i
      if (d >= x.l.length) break
      const v = level * Math.exp(-i / samp(0.04)) * Math.sin((2 * Math.PI * 110 * i) / SAMPLE_RATE)
      x.l[d] += v
      x.r[d] += v
    }
  }
  for (let i = samp(from); i < Math.min(x.l.length, samp(to)); i++) {
    const v = level * 0.25 * Math.sin((2 * Math.PI * 330 * i) / SAMPLE_RATE)
    x.l[i] += v
    x.r[i] += v
  }
}
function hitAt(x: Stereo, t: number, len: number) {
  for (let i = 0; i < samp(len); i++) {
    const d = samp(t) + i
    if (d >= x.l.length) break
    const v = 0.7 * Math.exp(-i / samp(0.6)) * (Math.sin((2 * Math.PI * 220 * i) / SAMPLE_RATE) + 0.5 * Math.sin((2 * Math.PI * 277 * i) / SAMPLE_RATE))
    x.l[d] += v
    x.r[d] += v
  }
}

const dir = mkdtempSync(join(tmpdir(), 'catty-sync-'))
const VOICE = join(dir, 'voice.wav')
const INTRO = join(dir, 'intro.wav')
const PUNCH = join(dir, 'punch.wav')
const PIC = join(dir, 'character.png')
const INTRO_HIT = 5.8

let plan: AudioPlan

beforeAll(async () => {
  const v = silence(4)
  speak(v, 0.5, 1.3)
  speak(v, 1.6, 2.0)
  speak(v, 2.4, 3.2) // the punch line
  writeFileSync(VOICE, encodeWav(v))

  const intro = silence(6)
  beats(intro, 0, 5.5, 0.15) // bed, then a dip from 5.5 to 5.8
  hitAt(intro, INTRO_HIT, 0.2)
  writeFileSync(INTRO, encodeWav(intro))
  const punch = silence(8)
  beats(punch, 0, 8, 0.3)
  writeFileSync(PUNCH, encodeWav(punch))

  await runTool(ff, ['-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=800x1000:d=1', '-frames:v', '1', PIC])

  plan = await buildAudio({
    ffmpeg: ff,
    workDir: join(dir, 'work'),
    voice: VOICE,
    music: [{ path: INTRO, role: 'intro' }, { path: PUNCH, role: 'punchline' }],
    pauseSec: 2,
    punchIndex: null
  })
}, 120_000)

describe('timeline math', () => {
  it('puts the bed hit exactly on the punch line, with the chosen pause', () => {
    const phrases = [{ start: samp(0.5), end: samp(1.3) }, { start: samp(2.4), end: samp(3.2) }]
    const tl = planTimeline({ phrases, punchIndex: 1, pauseSec: 2, leadInSec: 0.4, tailSec: 2, maxGapSec: 0.6, bedLength: samp(14), hitAt: samp(5.8) })
    expect(tl.punchAt).toBe(samp(0.4) + samp(0.8) + samp(2))
    expect(tl.hitOnTimeline).toBe(tl.punchAt)
    const m = tl.music[0]
    expect(m.srcStart + (tl.punchAt - m.dst)).toBe(samp(5.8))
  })
  it('lengthens the music when the punch line comes after the hit', () => {
    const phrases = [{ start: samp(0.5), end: samp(4) }, { start: samp(5), end: samp(6) }]
    const tl = planTimeline({ phrases, punchIndex: 1, pauseSec: 3, leadInSec: 0.4, tailSec: 2, maxGapSec: 0.6, bedLength: samp(10), hitAt: samp(1) })
    const main = tl.music[tl.music.length - 1]
    expect(main.dst + samp(1)).toBe(tl.punchAt)
    expect(tl.music[0].dst).toBe(0)
  })
})

describe('audio brain on generated sounds', () => {
  it('finds the three phrases and guesses the last as the punch line', () => {
    expect(plan.phrases).toHaveLength(3)
    expect(plan.punchIndex).toBe(2)
    expect(plan.punchGuessed).toBe(true)
  })
  it('finds the intro hit within 10 ms', () => {
    expect(Math.abs(plan.hits[0].atSec - INTRO_HIT)).toBeLessThan(0.01)
  })
  it('punch-line onset and music hit are within ±1 frame (30 fps)', () => {
    expect(plan.syncErrorMs).not.toBeNull()
    expect(Math.abs(plan.syncErrorMs!)).toBeLessThanOrEqual(FRAME_MS)
  })
  it('keeps the voice about 8 dB above the music', () => {
    expect(plan.voiceOverMusicDb!).toBeGreaterThan(6)
    expect(plan.voiceOverMusicDb!).toBeLessThan(10)
  })
  it('hits the loudness target with a safe true peak', async () => {
    const l = await measureLoudness(ff, plan.mixWav)
    expect(l.lufs).toBeGreaterThan(-16.5)
    expect(l.lufs).toBeLessThan(-12.5)
    expect(l.truePeakDb).toBeLessThan(-1)
  })
  it('the finished mix really has a hit on the punch line (re-measured from the file)', async () => {
    const mix = toMono(await decodeAudio(ff, plan.mixWav))
    const hits = findHits(mix, { from: samp(plan.punchAtSec - 0.6), to: samp(plan.punchAtSec + 0.6), count: 1 })
    expect(Math.abs(sec(hits[0].at) - plan.punchAtSec) * 1000).toBeLessThanOrEqual(FRAME_MS)
    const voiceOn = findPhrases(mix, { thresholdDb: -60 })
    expect(voiceOn.length).toBeGreaterThan(0)
  })
})

describe('draft render in both shapes', () => {
  for (const fmt of [FORMATS.vertical, FORMATS.landscape]) {
    it(`renders ${fmt.label} natively at ${fmt.width}×${fmt.height}, sound in sync`, async () => {
      const out = join(dir, `out-${fmt.id}.mp4`)
      const r = await renderDraft({ ffmpeg: ff, workDir: join(dir, 'work'), outFile: out, plan, visual: { type: 'picture', path: PIC }, fmt })
      const info = await runTool(ff, ['-i', out]).catch((e: Error) => ({ stderr: e.message }))
      expect(info.stderr).toContain(`${fmt.width}x${fmt.height}`)
      const dur = info.stderr.match(/Duration: (\d+):(\d+):([\d.]+)/)!
      expect(Math.abs(Number(dur[3]) + 60 * Number(dur[2]) - plan.durationSec)).toBeLessThan(0.1)
      expect(Math.abs(r.encoderOffsetMs!)).toBeLessThanOrEqual(FRAME_MS / 2)
      expect(r.qa.every((q) => q.ok)).toBe(true)
    }, 300_000)
  }
})
