// The audio brain — a faithful port of reference_kit/tools/audio_brain.py (same numbers, same order).
// "Do not simplify it: every step exists because a video went wrong without it."
// Output: vo.wav (voice only, placed — drives the mouth), mix_final.wav, timeline.json.
import { join } from 'node:path'
import { promises as fs } from 'node:fs'
import { SAMPLE_RATE as SR, encodeWav, runTool, type Stereo } from '../ffmpeg'
import { writeFileAtomic } from '../atomic'
import { measureLoudness, type Loudness } from '../loudness'
import { placeClips, peaks, type MusicClip } from './clips'

export const CLEAN =
  'highpass=f=85,lowpass=f=10500,afftdn=nr=12:nf=-45,agate=threshold=0.008:ratio=3:attack=4:release=120,' +
  'equalizer=f=220:t=q:w=1:g=1.5,equalizer=f=3000:t=q:w=1.2:g=2.5,' +
  'acompressor=threshold=0.05:ratio=3:attack=5:release=90:makeup=2,loudnorm=I=-13:TP=-1.5'

/** The cut offsets after the punch line, from the reference (a cut + flash + whoosh on each). */
export const CUT_OFFSETS = [1.0, 2.0, 3.0, 4.2, 5.2, 6.3, 7.4]

export type Seg = [number, number]

// ───────────────────────── 2. phrases → units ─────────────────────────
/** Same result as ffmpeg silencedetect=noise=-38dB:d=0.18 on the ISOLATED stem (before loudnorm). */
export function findPhrases(voc: Stereo, thrDb = -38, minGap = 0.18, minLen = 0.06): Seg[] {
  const hop = Math.round(0.01 * SR)
  const n = Math.floor(voc.l.length / hop)
  const thr = Math.pow(10, thrDb / 20)
  const act: boolean[] = new Array(n)
  for (let i = 0; i < n; i++) {
    let pk = 0
    for (let k = i * hop; k < (i + 1) * hop; k++) pk = Math.max(pk, Math.abs(voc.l[k]), Math.abs(voc.r[k]))
    act[i] = pk >= thr
  }
  const segs: Seg[] = []
  for (let i = 0; i < n; ) {
    if (act[i]) {
      let j = i
      while (j < n && act[j]) j++
      segs.push([i * 0.01, j * 0.01])
      i = j
    } else i++
  }
  const merged: Seg[] = []
  for (const s of segs) {
    const last = merged[merged.length - 1]
    if (last && s[0] - last[1] < minGap) last[1] = s[1]
    else merged.push([s[0], s[1]])
  }
  return merged.filter((s) => s[1] - s[0] >= minLen)
}

/** A "unit" = words said together. A gap of ≥ 0.9 s is a deliberate pause between units. */
export function groupUnits(phrases: Seg[], unitGap = 0.9): Seg[] {
  const units: Seg[] = []
  for (const p of phrases) {
    const last = units[units.length - 1]
    if (last && p[0] - last[1] < unitGap) units[units.length - 1] = [last[0], p[1]]
    else units.push([p[0], p[1]])
  }
  return units
}

// ───────────────────────── 3. music ─────────────────────────
/** Strongest rise in the first `search` s of the chorus = its first downbeat (~0.10 s for chorus_2). */
export function firstDownbeat(chorus: Stereo, search = 0.5): number {
  const h = Math.round(0.01 * SR)
  const n = Math.floor((search * SR) / h)
  const r: number[] = []
  for (let i = 0; i < n; i++) {
    let s = 0
    let c = 0
    for (let k = i * h; k < i * h + 2 * h && k < chorus.l.length; k++) {
      const m = 0.5 * (chorus.l[k] + chorus.r[k])
      s += m * m
      c++
    }
    r.push(Math.sqrt(s / Math.max(1, c)))
  }
  let best = 0
  let bi = 0
  for (let i = 0; i < r.length - 1; i++) {
    const d = r[i + 1] - r[i]
    if (i === 0 || d > best) { best = d; bi = i }
  }
  return (bi + 1) * 0.01
}

// Deterministic noise (so renders are reproducible).
function noise(n: number, seed: number): Float64Array {
  const out = new Float64Array(n)
  let s = seed >>> 0 || 1
  for (let i = 0; i < n; i += 2) {
    s = (s * 1664525 + 1013904223) >>> 0
    const u1 = (s + 1) / 4294967297
    s = (s * 1664525 + 1013904223) >>> 0
    const u2 = s / 4294967296
    const r = Math.sqrt(-2 * Math.log(u1))
    out[i] = r * Math.cos(2 * Math.PI * u2)
    if (i + 1 < n) out[i + 1] = r * Math.sin(2 * Math.PI * u2)
  }
  return out
}

/** 2nd-order Butterworth band-pass (500–6000 Hz), as scipy butter(2, ..., btype="band") → sosfilt. */
function bandpass(x: Float64Array, lo = 500, hi = 6000): Float64Array {
  // Two cascaded biquads: high-pass at lo and low-pass at hi (Butterworth, Q = 1/√2) ≈ butter(2, band).
  const biquad = (inp: Float64Array, type: 'hp' | 'lp', f0: number) => {
    const w0 = (2 * Math.PI * f0) / SR
    const cs = Math.cos(w0), sn = Math.sin(w0)
    const alpha = sn / (2 * Math.SQRT1_2)
    let b0, b1, b2
    if (type === 'lp') { b0 = (1 - cs) / 2; b1 = 1 - cs; b2 = (1 - cs) / 2 } else { b0 = (1 + cs) / 2; b1 = -(1 + cs); b2 = (1 + cs) / 2 }
    const a0 = 1 + alpha, a1 = -2 * cs, a2 = 1 - alpha
    const y = new Float64Array(inp.length)
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0
    for (let i = 0; i < inp.length; i++) {
      const v = (b0 * inp[i] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0
      x2 = x1; x1 = inp[i]; y2 = y1; y1 = v; y[i] = v
    }
    return y
  }
  return biquad(biquad(x, 'hp', lo), 'lp', hi)
}

export function whoosh(dur: number, peak: number, seed = 3): Float64Array {
  const n = Math.round(SR * dur)
  let x = bandpass(noise(n, seed))
  let mx = 0
  for (let i = 0; i < n; i++) {
    x[i] *= Math.pow(n > 1 ? i / (n - 1) : 1, 2.2)
    mx = Math.max(mx, Math.abs(x[i]))
  }
  if (mx > 0) x = x.map((v) => (v / mx) * peak)
  return x
}

export function impact(peak: number, seed = 5): Float64Array {
  const n = Math.round(SR * 0.7)
  const nz = noise(n, seed)
  const out = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    const t = i / SR
    const thump = Math.sin(2 * Math.PI * (48 + 60 * Math.exp(-t * 18)) * t) * Math.exp(-t * 7)
    const snap = nz[i] * Math.exp(-t * 40) * 0.3
    out[i] = ((thump + snap) / 1.3) * peak
  }
  return out
}

function movingAvg(x: Float64Array, w: number): Float64Array {
  // np.convolve(x, ones(w)/w, "same")
  const n = x.length
  const out = new Float64Array(n)
  const half = Math.floor((w - 1) / 2)
  let s = 0
  const pre = new Float64Array(n + 1)
  for (let i = 0; i < n; i++) { s += x[i]; pre[i + 1] = s }
  for (let i = 0; i < n; i++) {
    const a = Math.max(0, i - (w - 1 - half))
    const b = Math.min(n, i + half + 1)
    out[i] = (pre[b] - pre[a]) / w
  }
  return out
}

export interface PlacedUnit { unit: number; src: Seg; dest: Seg; gain: number }

export interface BrainInput {
  ffmpeg: string
  workDir: string
  /** Isolated vocal stem (output of the MDX model) and the cleaned mono voice (CLEAN chain). */
  voc: Stereo
  vClean: Float32Array
  intro: Stereo | null
  chorus: Stereo | null
  introPath: string | null
  chorusPath: string | null
  punchTime?: number // default 8.24 (raised automatically if the words before the punch need more room)
  pause?: number // default 2.0
  duration?: number // default 18.0
  punchUnits?: number[] // default = last unit. THE USER MUST CONFIRM THIS.
  targetLufs?: number // default −15.5
  /** Use these as the units instead of grouping (e.g. phrases, when the voice has no 0.9 s pause). */
  unitsOverride?: Seg[]
  /** One music file with no separate punch-line part: its strongest hit (seconds into the file) lands on the punch line. */
  singleHitSec?: number | null
  /** Music placed by hand in the timeline editor (relative to the punch line). Overrides the automatic music. */
  manualMusic?: { path: string; dstFromPunchSec: number; inSec: number; outSec: number | null; audio: Stereo }[]
}

export interface Timeline {
  punch_time: number
  units: Seg[]
  phrases: Seg[]
  punch_units: number[]
  placed: PlacedUnit[]
  chorus_start: number | null
  chorus_downbeat: number | null
  intro_offset: number | null
  cuts: number[]
  duration: number
  lufs: number
  peak_dbfs: number
  voice_over_music_db: number
  voice_onset: number
  pause_before_punch: number
  notes: string[]
  /** What the music is doing, as clips (shown in the timeline editor). */
  music_clips: MusicClip[]
  manual_music: boolean
}

export interface BrainResult {
  timeline: Timeline
  voWav: string
  mixWav: string
  timelineJson: string
  vo: Float64Array
  loudness: Loudness
  voicePeaks: number[]
}

export async function runBrain(inp: BrainInput): Promise<BrainResult> {
  const notes: string[] = []
  const pause = inp.pause ?? 2.0
  const phrases = findPhrases(inp.voc)
  const units = inp.unitsOverride ?? groupUnits(phrases)
  if (units.length < 2) throw new Error('I need at least two parts in your voice: the set-up, then the punch line. I only found one.')
  const pu = (inp.punchUnits?.length ? inp.punchUnits : [units.length - 1]).filter((i) => i >= 0 && i < units.length).sort((a, b) => a - b)
  if (!pu.length) throw new Error('Please choose which part is the punch line.')
  const pre = units.map((_, i) => i).filter((i) => i < Math.min(...pu))
  if (!pre.length) throw new Error('The punch line can’t be the very first part: there must be at least one part before it.')

  // Punch time: 8.24 s like the reference, unless the words before the punch line need more room.
  const preLen = units[Math.max(...pre)][1] - units[pre[0]][0]
  let P = inp.punchTime ?? 8.24
  const needed = pause + preLen + 0.35
  if (P < needed) {
    P = Math.round(needed * 100) / 100
    notes.push(`Moved the punch line to ${P.toFixed(2)} s so all your words before it fit.`)
  }
  const lastPunchEnd = units[Math.max(...pu)][1] - units[Math.min(...pu)][0] + P
  let duration = inp.duration ?? 18.0
  if (duration < lastPunchEnd + 2.5) {
    duration = Math.ceil((lastPunchEnd + 2.5) * 10) / 10
    notes.push(`Made the video ${duration.toFixed(1)} s long so the punch line can finish.`)
  }
  const N = Math.round(SR * duration)
  const v = inp.vClean

  // --- levels: bring the punch line to the average level of the pre-punch units (cap +6 dB) so it is never the quietest
  const rms = (s0: number, s1: number) => {
    const a = Math.round(s0 * SR), b = Math.min(v.length, Math.round(s1 * SR))
    let s = 0
    for (let i = a; i < b; i++) s += v[i] * v[i]
    return Math.sqrt(s / Math.max(1, b - a) + 1e-12)
  }
  const target = pre.reduce((s, i) => s + rms(...units[i]), 0) / pre.length
  // --- placement: punch unit starts exactly on the punch time; pre-punch units keep their natural gaps and end `pause` s before it
  const prms = Math.sqrt(pu.reduce((s, i) => s + rms(...units[i]) ** 2, 0) / pu.length)
  const shiftPre = P - pause - units[Math.max(...pre)][1]
  const shiftPunch = P - units[Math.min(...pu)][0]
  const placed: PlacedUnit[] = []
  const vo = new Float64Array(N)
  const f = Math.round(0.015 * SR)
  units.forEach(([s0, s1], i) => {
    let sh: number, g: number
    if (pu.includes(i)) { sh = shiftPunch; g = Math.min(2.0, Math.max(1.0, target / prms)) }
    else if (pre.includes(i)) { sh = shiftPre; g = 1.0 }
    else return
    const p0 = Math.max(0, s0 - 0.05), p1 = s1 + 0.05
    const a = Math.round(p0 * SR), b = Math.min(v.length, Math.round(p1 * SR))
    const len = b - a
    const o = Math.round((p0 + sh) * SR)
    for (let k = 0; k < len; k++) {
      let x = v[a + k] * g
      if (k < f) x *= k / (f - 1)
      if (k >= len - f) x *= (len - 1 - k) / (f - 1)
      const d = o + k
      if (d >= 0 && d < N) vo[d] += x
    }
    placed.push({ unit: i, src: [s0, s1], dest: [s0 + sh, s1 + sh], gain: Math.round(g * 1000) / 1000 })
  })
  let vmax = 1e-9
  for (let i = 0; i < N; i++) vmax = Math.max(vmax, Math.abs(vo[i]))
  const voWav = join(inp.workDir, 'vo.wav')
  const voScaled = new Float32Array(N)
  for (let i = 0; i < N; i++) voScaled[i] = (vo[i] * 0.95) / vmax
  await writeFileAtomic(voWav, encodeWav({ l: voScaled, r: voScaled }))

  // --- music: chorus downbeat lands ON the punch time; intro is trimmed so it ends exactly where the chorus starts
  let clips: MusicClip[] = []
  let chorusStart: number | null = null
  let db: number | null = null
  let introOffset: number | null = null
  const decoded = new Map<string, Stereo>()
  const manual = !!inp.manualMusic?.length
  if (manual) {
    for (const m of inp.manualMusic!) {
      decoded.set(m.path, m.audio)
      const dur = m.audio.l.length / SR
      const inS = Math.max(0, Math.min(m.inSec, dur))
      clips.push({ path: m.path, dstSec: P + m.dstFromPunchSec, inSec: inS, outSec: Math.max(inS, Math.min(m.outSec ?? dur, dur)), fadeInSec: 0.015 })
    }
    notes.push('You placed the music by hand in the timeline.')
  } else if (inp.chorus && inp.chorusPath) {
    db = firstDownbeat(inp.chorus)
    chorusStart = P - db
    decoded.set(inp.chorusPath, inp.chorus)
    if (inp.intro && inp.introPath) {
      decoded.set(inp.introPath, inp.intro)
      const introLen = inp.intro.l.length / SR
      if (introLen >= chorusStart + 0.01) {
        introOffset = introLen - chorusStart
        clips.push({ path: inp.introPath, dstSec: 0, inSec: introOffset, outSec: introLen, fadeInSec: 0, fadeOutSec: 0 })
      } else {
        // stutter edit: repeat the last 2 s to lengthen the bed, so the intro still ends where the chorus starts
        let len = introLen
        const reps: number[] = []
        while (len < chorusStart + 0.01) { reps.push(len); len += 2 }
        introOffset = len - chorusStart
        // the extended intro = original + k copies of its last 2 s; express it as clips
        const tail0 = Math.max(0, introLen - 2)
        let cursor = -introOffset
        clips.push({ path: inp.introPath, dstSec: cursor, inSec: 0, outSec: introLen, fadeInSec: 0, fadeOutSec: 0 })
        cursor += introLen
        for (let k = 0; k < reps.length; k++) {
          clips.push({ path: inp.introPath, dstSec: cursor, inSec: tail0, outSec: introLen, fadeInSec: 0, fadeOutSec: 0 })
          cursor += introLen - tail0
        }
        // anything before t=0 is cut by placeClips; give the first audible part a fade-in
        notes.push('The intro was too short, so I repeated its last 2 seconds to make it longer.')
      }
      notes.push(`The intro starts ${introOffset.toFixed(2)} s in and ends exactly where the punch-line music starts.`)
    } else {
      notes.push('No intro was given: the music starts with the punch-line music.')
    }
    const chorusLen = inp.chorus.l.length / SR
    clips.push({ path: inp.chorusPath, dstSec: chorusStart, inSec: 0, outSec: Math.min(chorusLen, duration - chorusStart), fadeInSec: 0, fadeOutSec: 0 })
    notes.push(`The punch-line music’s first beat (${db.toFixed(2)} s into it) lands exactly on your punch line at ${P.toFixed(2)} s.`)
  } else if (inp.intro && inp.introPath) {
    decoded.set(inp.introPath, inp.intro)
    const len = inp.intro.l.length / SR
    if (inp.singleHitSec != null) {
      // One music file: put its strongest hit on the punch line (start inside the song if needed).
      const dst = P - inp.singleHitSec
      clips.push({ path: inp.introPath, dstSec: Math.max(0, dst), inSec: Math.max(0, -dst), outSec: len, fadeInSec: 0 })
      db = inp.singleHitSec
      notes.push(`One music file: its strongest hit (${inp.singleHitSec.toFixed(2)} s into the song) lands on your punch line.`)
      if (dst > 0) notes.push(`The song only starts at ${dst.toFixed(2)} s, so the first part has no music. Add an intro for music from the start.`)
    } else {
      clips.push({ path: inp.introPath, dstSec: 0, inSec: 0, outSec: len, fadeInSec: 0 })
      notes.push('Only one music file was given, so it simply plays from the start. Add the punch-line music for a hit on the punch line.')
    }
  }
  const mus = placeClips(decoded, clips, N)
  const fi = Math.round(0.35 * SR) // fade the music in over the first 0.35 s of the video
  for (let i = 0; i < fi && i < N; i++) { const g = i / (fi - 1); mus.l[i] *= g; mus.r[i] *= g }
  const fo = Math.round(1.9 * SR)
  for (let i = 0; i < fo && i < N; i++) {
    const g = 1 - i / fo
    mus.l[N - fo + i] *= g
    mus.r[N - fo + i] *= g
  }

  // --- cuts + sfx
  const cuts = CUT_OFFSETS.map((d) => Math.round((P + d) * 100) / 100).filter((c) => c < duration - 0.5)
  const sfx = new Float64Array(N)
  const put = (x: Float64Array, at: number, maxLen = x.length) => {
    const o = Math.round(at * SR)
    for (let i = 0; i < Math.min(maxLen, x.length); i++) if (o + i >= 0 && o + i < N) sfx[o + i] += x[i]
  }
  put(impact(0.55), P)
  for (const c of cuts) {
    put(whoosh(0.28, 0.22), c - 0.28)
    put(impact(0.22), c, Math.round(SR * 0.35))
  }

  // --- mix: music ducked 50% by the voice envelope, voice ×1.45, then loudness to target
  const absVo = vo.map(Math.abs)
  let env = movingAvg(absVo, Math.round(0.06 * SR))
  env = movingAvg(env.map((e) => Math.min(e / 0.12, 1)), Math.round(0.25 * SR))
  const mixL = new Float32Array(N)
  const mixR = new Float32Array(N)
  const M0 = new Float64Array(N)
  let pk = 0
  for (let i = 0; i < N; i++) {
    const duck = 0.85 * (1 - 0.5 * env[i])
    const ml = mus.l[i] * duck
    const mr = mus.r[i] * duck
    M0[i] = ml
    const V = vo[i] * 1.45
    mixL[i] = ml + V + sfx[i] * 0.9
    mixR[i] = mr + V + sfx[i] * 0.9
    pk = Math.max(pk, Math.abs(mixL[i]), Math.abs(mixR[i]))
  }
  if (pk > 0.93) for (let i = 0; i < N; i++) { mixL[i] *= 0.93 / pk; mixR[i] *= 0.93 / pk }
  const rawWav = join(inp.workDir, 'mix_raw.wav')
  const mixWav = join(inp.workDir, 'mix_final.wav')
  await writeFileAtomic(rawWav, encodeWav({ l: mixL, r: mixR }))
  // loudness: measure, correct, limit — 3 rounds (loudnorm alone undershoots short clips).
  // Limiting also at 4× resolution so in-between ("true") peaks stay under −1 dBFS.
  const target2 = inp.targetLufs ?? -15.5
  let gain = 0
  let L: Loudness = { lufs: -70, truePeakDb: -70 }
  const tmp = mixWav + '.partial.wav'
  for (let k = 0; k < 3; k++) {
    await runTool(inp.ffmpeg, ['-y', '-v', 'error', '-i', rawWav, '-af',
      `volume=${gain.toFixed(2)}dB,alimiter=limit=0.8:level=disabled:latency=1,aresample=176400,alimiter=limit=0.8:level=disabled:latency=1,aresample=44100`,
      '-c:a', 'pcm_s16le', tmp])
    L = await measureLoudness(inp.ffmpeg, tmp)
    gain += target2 - L.lufs
  }
  await fs.rename(tmp, mixWav)

  // --- self-checks (a failed check must be shown to the user, never hidden)
  const act = movingAvg(absVo, Math.round(0.05 * SR)).map((x) => (x > 0.02 ? 1 : 0))
  let sv = 0, sm = 0, cnt = 0
  for (let i = 0; i < N; i++) if (act[i]) { const V = vo[i] * 1.45; sv += V * V; sm += M0[i] * M0[i]; cnt++ }
  const vdb = 20 * Math.log10(Math.sqrt(sv / Math.max(1, cnt)) + 1e-9)
  const mdb = 20 * Math.log10(Math.sqrt(sm / Math.max(1, cnt)) + 1e-9)
  let onset = P
  for (let i = Math.round((P - 0.3) * SR); i < N; i++) if (Math.abs(vo[i]) > 0.01) { onset = i / SR; break }
  const gapBefore = P - Math.max(...placed.filter((d) => pre.includes(d.unit)).map((d) => d.dest[1]))

  const r3 = (x: number) => Math.round(x * 1000) / 1000
  const timeline: Timeline = {
    punch_time: P, units, phrases, punch_units: pu, placed,
    chorus_start: chorusStart === null ? null : r3(chorusStart), chorus_downbeat: db === null ? null : r3(db),
    intro_offset: introOffset === null ? null : r3(introOffset), cuts, duration,
    lufs: L.lufs, peak_dbfs: L.truePeakDb, voice_over_music_db: Math.round((vdb - mdb) * 10) / 10,
    voice_onset: r3(onset), pause_before_punch: Math.round(gapBefore * 100) / 100,
    notes, music_clips: clips, manual_music: manual
  }
  const timelineJson = join(inp.workDir, 'timeline.json')
  await writeFileAtomic(timelineJson, JSON.stringify(timeline, null, 1))
  return { timeline, voWav, mixWav, timelineJson, vo, loudness: L, voicePeaks: peaks({ l: voScaled, r: voScaled }, 100) }
}
