// Pure signal analysis: no files, no ffmpeg. Everything works in SAMPLES so timing stays exact.
import { SAMPLE_RATE } from '../ffmpeg'

export const sec = (samples: number) => samples / SAMPLE_RATE
export const samp = (seconds: number) => Math.round(seconds * SAMPLE_RATE)

/** RMS level per window (hop = window). */
export function rmsEnvelope(x: Float32Array, windowSamples: number): Float32Array {
  const n = Math.ceil(x.length / windowSamples)
  const out = new Float32Array(n)
  for (let f = 0; f < n; f++) {
    const a = f * windowSamples
    const b = Math.min(x.length, a + windowSamples)
    let s = 0
    for (let i = a; i < b; i++) s += x[i] * x[i]
    out[f] = Math.sqrt(s / Math.max(1, b - a))
  }
  return out
}

export const toDb = (v: number) => 20 * Math.log10(Math.max(v, 1e-9))

export interface Phrase {
  /** First sample of actual sound (no padding). */
  start: number
  /** Last sample of actual sound (exclusive). */
  end: number
}

/**
 * Find spoken phrases: sound separated by silence (brief: silencedetect noise=-38dB, d=0.18).
 * Works on 5 ms frames, so phrase starts are accurate to 5 ms (a sixth of a video frame).
 */
export function findPhrases(
  voice: Float32Array,
  opts: { thresholdDb?: number; minSilenceSec?: number; minPhraseSec?: number } = {}
): Phrase[] {
  const thr = opts.thresholdDb ?? -38
  const minSil = opts.minSilenceSec ?? 0.18
  const minPhrase = opts.minPhraseSec ?? 0.08
  const hop = samp(0.005)
  const env = rmsEnvelope(voice, hop)
  const loud = Array.from(env, (v) => toDb(v) > thr)

  const raw: Phrase[] = []
  let i = 0
  while (i < loud.length) {
    if (!loud[i]) { i++; continue }
    const s = i
    while (i < loud.length && loud[i]) i++
    raw.push({ start: s * hop, end: Math.min(voice.length, i * hop) })
  }
  // Merge sounds separated by less than the minimum silence (gaps inside words / between words).
  const merged: Phrase[] = []
  for (const p of raw) {
    const last = merged[merged.length - 1]
    if (last && sec(p.start - last.end) < minSil) last.end = p.end
    else merged.push({ ...p })
  }
  return merged.filter((p) => sec(p.end - p.start) >= minPhrase)
}

export interface Hit {
  /** Sample where the hit starts (refined to ~5 ms). */
  at: number
  /** How strong the jump is: loudness after ÷ loudness before. */
  strength: number
}

/**
 * Find music hits (brief: 50 ms RMS envelope; score = mean(next 3–7 frames) / mean(previous 8–2 frames)).
 * Returns the best candidates, strongest first, each refined to ~5 ms with a fine envelope.
 */
export function findHits(
  music: Float32Array,
  opts: { from?: number; to?: number; count?: number } = {}
): Hit[] {
  const hop = samp(0.05)
  const env = rmsEnvelope(music, hop)
  const peak = env.reduce((a, b) => Math.max(a, b), 0)
  const fromF = Math.max(8, Math.floor((opts.from ?? 0) / hop))
  const toF = Math.min(env.length - 8, Math.ceil((opts.to ?? music.length) / hop))
  const floor = Math.max(peak * 0.01, 1e-4) // avoid "infinite" jumps after digital silence

  const scored: { f: number; s: number }[] = []
  for (let f = fromF; f < toF; f++) {
    let after = 0
    for (let k = 3; k <= 7; k++) after += env[f + k]
    after /= 5
    let before = 0
    for (let k = 2; k <= 8; k++) before += env[f - k]
    before /= 7
    if (after < peak * 0.25) continue // a hit must actually be loud afterwards
    scored.push({ f, s: after / Math.max(before, floor) })
  }
  scored.sort((a, b) => b.s - a.s)

  // Keep the best few, at least 1 s apart.
  const picked: { f: number; s: number }[] = []
  for (const c of scored) {
    if (picked.every((p) => Math.abs(p.f - c.f) * hop > SAMPLE_RATE)) picked.push(c)
    if (picked.length >= (opts.count ?? 5)) break
  }
  return picked.map((p) => ({ at: refineOnset(music, p.f * hop - hop, p.f * hop + 7 * hop), strength: p.s }))
}

/**
 * Inside [a, b), find where the sound jumps up: the first 5 ms frame that rises past halfway
 * between the quiet level before and the loud level after.
 */
export function refineOnset(x: Float32Array, a: number, b: number): number {
  const hop = samp(0.005)
  a = Math.max(0, a)
  b = Math.min(x.length, b)
  const env = rmsEnvelope(x.subarray(a, b), hop)
  if (env.length < 4) return a
  // Biggest single-step rise = the attack.
  let best = 1
  let bestRise = -Infinity
  for (let i = 1; i < env.length; i++) {
    const rise = env[i] - env[i - 1]
    if (rise > bestRise) { bestRise = rise; best = i }
  }
  // Walk back to where the attack began: the first frame clearly (~+10 dB) above the quiet level before it.
  const q0 = Math.max(0, best - 22)
  const q1 = Math.max(q0 + 1, best - 2)
  let quiet = 0
  for (let k = q0; k < q1; k++) quiet += env[k]
  quiet /= q1 - q0
  const thr = Math.min(quiet * 3.16, env[best] * 0.5)
  let i = best
  while (i > 0 && env[i - 1] > thr) i--
  return a + i * hop
}

/** Tempo estimate (BPM) from autocorrelation of the onset envelope. Informational. */
export function estimateTempo(music: Float32Array): number | null {
  const hop = samp(0.01)
  const env = rmsEnvelope(music, hop)
  const onset = new Float32Array(env.length)
  for (let i = 1; i < env.length; i++) onset[i] = Math.max(0, env[i] - env[i - 1])
  let best = 0
  let bestLag = 0
  for (let bpm = 60; bpm <= 180; bpm++) {
    const lag = Math.round(60 / bpm / 0.01)
    let s = 0
    for (let i = lag; i < onset.length; i++) s += onset[i] * onset[i - lag]
    if (s > best) { best = s; bestLag = lag }
  }
  return bestLag ? Math.round(60 / (bestLag * 0.01)) : null
}
