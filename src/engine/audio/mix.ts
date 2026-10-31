// Builds the final stereo mix from the cleaned voice, the music bed and the timeline.
import { SAMPLE_RATE, type Stereo } from '../ffmpeg'
import { rmsEnvelope, samp, toDb } from './analysis'
import type { Timeline } from './timeline'

export interface MixOptions {
  musicGain: number // brief: ~0.85
  voiceGain: number // brief: ~1.45
  duckDepth: number // brief: ~40 %
  /** Voice should sit this many dB above the music while speaking (brief: about 8 dB). */
  voiceOverMusicDb: number
  thump: boolean
  fadeOutSec: number
}

export const DEFAULT_MIX: MixOptions = {
  musicGain: 0.85,
  voiceGain: 1.45,
  duckDepth: 0.4,
  voiceOverMusicDb: 8,
  thump: true,
  fadeOutSec: 1.2
}

export interface MixResult {
  mix: Stereo
  voiceTrack: Stereo
  musicTrack: Stereo
  /** Measured: how many dB the voice sits above the music while speaking. */
  voiceOverMusicDb: number | null
}

function blank(n: number): Stereo {
  return { l: new Float32Array(n), r: new Float32Array(n) }
}

/** 15 ms fade in/out on each phrase clip (brief). */
function fadeGain(i: number, len: number, fade: number): number {
  if (i < fade) return i / fade
  if (i > len - fade) return Math.max(0, (len - i) / fade)
  return 1
}

export function placeVoice(voice: Stereo, tl: Timeline): Stereo {
  const out = blank(tl.length)
  const fade = samp(0.015)
  for (const p of tl.phrases) {
    const len = Math.min(p.srcEnd, voice.l.length) - p.srcStart
    for (let i = 0; i < len; i++) {
      const d = p.dstStart + i
      if (d < 0 || d >= out.l.length) continue
      const g = fadeGain(i, len, fade)
      out.l[d] += voice.l[p.srcStart + i] * g
      out.r[d] += voice.r[p.srcStart + i] * g
    }
  }
  return out
}

export function placeMusic(bed: Stereo, tl: Timeline): Stereo {
  const out = blank(tl.length)
  for (const m of tl.music) {
    const len = Math.min(m.srcEnd, bed.l.length) - m.srcStart
    for (let i = 0; i < len; i++) {
      const d = m.dst + i
      if (d >= out.l.length) break
      const g = i < m.fadeInSamples ? i / m.fadeInSamples : 1
      out.l[d] += bed.l[m.srcStart + i] * g
      out.r[d] += bed.r[m.srcStart + i] * g
    }
  }
  return out
}

/** Smoothed voice envelope 0..1 (brief: 60 ms RMS, 250 ms smoothing) used to duck the music. */
export function duckCurve(voice: Stereo): Float32Array {
  const n = voice.l.length
  const mono = new Float32Array(n)
  for (let i = 0; i < n; i++) mono[i] = 0.5 * (Math.abs(voice.l[i]) + Math.abs(voice.r[i]))
  const hop = samp(0.06)
  const env = rmsEnvelope(mono, hop)
  const peak = env.reduce((a, b) => Math.max(a, b), 1e-9)
  // One-pole smoothing with a 250 ms time constant, both directions so it starts before speech.
  const a = Math.exp(-0.06 / 0.25)
  const fwd = new Float32Array(env.length)
  let s = 0
  for (let i = 0; i < env.length; i++) { s = a * s + (1 - a) * Math.min(1, (env[i] / peak) * 2); fwd[i] = s }
  s = 0
  for (let i = env.length - 1; i >= 0; i--) { s = a * s + (1 - a) * Math.min(1, (env[i] / peak) * 2); fwd[i] = Math.max(fwd[i], s) }
  const curve = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const f = i / hop
    const k = Math.min(env.length - 1, Math.floor(f))
    const k2 = Math.min(env.length - 1, k + 1)
    const t = f - k
    curve[i] = fwd[k] * (1 - t) + fwd[k2] * t
  }
  return curve
}

/** Low "thump" on the punch line (brief: sine 48 Hz + 60 Hz sweep, decay 7/s). */
export function addThump(mix: Stereo, at: number, gain = 0.35): void {
  const len = samp(0.8)
  let phase2 = 0
  for (let i = 0; i < len; i++) {
    const d = at + i
    if (d >= mix.l.length) break
    const t = i / SAMPLE_RATE
    const f2 = 60 - 20 * Math.min(1, t / 0.4)
    phase2 += (2 * Math.PI * f2) / SAMPLE_RATE
    const attack = Math.min(1, i / samp(0.004))
    const v = gain * attack * Math.exp(-7 * t) * (Math.sin(2 * Math.PI * 48 * t) + 0.6 * Math.sin(phase2))
    mix.l[d] += v
    mix.r[d] += v
  }
}

function rmsWhere(x: Stereo, mask: Float32Array, minMask: number): number | null {
  let s = 0
  let n = 0
  for (let i = 0; i < x.l.length; i++) {
    if (mask[i] < minMask) continue
    s += 0.5 * (x.l[i] * x.l[i] + x.r[i] * x.r[i])
    n++
  }
  return n > 0 ? Math.sqrt(s / n) : null
}

export function mixTracks(voice: Stereo, bed: Stereo | null, tl: Timeline, opt: MixOptions = DEFAULT_MIX): MixResult {
  const v = placeVoice(voice, tl)
  for (let i = 0; i < v.l.length; i++) { v.l[i] *= opt.voiceGain; v.r[i] *= opt.voiceGain }

  const m = bed ? placeMusic(bed, tl) : blank(tl.length)
  const duck = duckCurve(v)
  for (let i = 0; i < m.l.length; i++) {
    const g = opt.musicGain * (1 - opt.duckDepth * duck[i])
    m.l[i] *= g
    m.r[i] *= g
  }

  // Keep the voice ~8 dB above the music while speaking: measure, then nudge the music level.
  let measured: number | null = null
  if (bed) {
    const vr = rmsWhere(v, duck, 0.6)
    const mr = rmsWhere(m, duck, 0.6)
    if (vr && mr && mr > 1e-6) {
      const diff = toDb(vr) - toDb(mr)
      const correction = Math.pow(10, (diff - opt.voiceOverMusicDb) / 20)
      const k = Math.max(0.25, Math.min(2.0, correction))
      for (let i = 0; i < m.l.length; i++) { m.l[i] *= k; m.r[i] *= k }
      const mr2 = rmsWhere(m, duck, 0.6)
      measured = mr2 ? toDb(vr) - toDb(mr2) : null
    }
    // Fade the music out at the end.
    const fo = samp(opt.fadeOutSec)
    for (let i = 0; i < fo; i++) {
      const d = m.l.length - fo + i
      if (d < 0) continue
      const g = 1 - i / fo
      m.l[d] *= g
      m.r[d] *= g
    }
  }

  const mix = blank(tl.length)
  for (let i = 0; i < mix.l.length; i++) {
    mix.l[i] = v.l[i] + m.l[i]
    mix.r[i] = v.r[i] + m.r[i]
  }
  if (opt.thump) addThump(mix, tl.punchAt)
  return { mix, voiceTrack: v, musicTrack: m, voiceOverMusicDb: measured }
}

export function concatStereo(a: Stereo, b: Stereo): Stereo {
  const l = new Float32Array(a.l.length + b.l.length)
  const r = new Float32Array(a.r.length + b.r.length)
  l.set(a.l); l.set(b.l, a.l.length)
  r.set(a.r); r.set(b.r, a.r.length)
  return { l, r }
}
