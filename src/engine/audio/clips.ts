// Music as clips on the timeline (like a video editor): each clip = a piece of one music file,
// placed at a time on the video. The automatic sync produces clips; the owner can move/trim them.
import { SAMPLE_RATE, type Stereo } from '../ffmpeg'
import { samp, sec } from './analysis'
import type { Timeline } from './timeline'

export interface MusicClip {
  /** The music file this clip plays. */
  path: string
  /** Where the clip starts on the video timeline (seconds). */
  dstSec: number
  /** Which part of the file plays: from inSec to outSec (seconds in the file). */
  inSec: number
  outSec: number
  /** Fade-in length at the clip start (seconds). */
  fadeInSec?: number
}

/**
 * Turn the automatic plan (music bed = files joined end to end) into per-file clips,
 * so the editor shows exactly what the automatic sync did.
 */
export function clipsFromTimeline(tl: Timeline, files: { path: string; length: number }[]): MusicClip[] {
  const out: MusicClip[] = []
  const starts: number[] = []
  let acc = 0
  for (const f of files) { starts.push(acc); acc += f.length }
  for (const piece of tl.music) {
    for (let k = 0; k < files.length; k++) {
      const fs = starts[k]
      const fe = fs + files[k].length
      const a = Math.max(piece.srcStart, fs)
      const b = Math.min(piece.srcEnd, fe)
      if (b <= a) continue
      out.push({
        path: files[k].path,
        dstSec: sec(piece.dst + (a - piece.srcStart)),
        inSec: sec(a - fs),
        outSec: sec(b - fs),
        fadeInSec: a === piece.srcStart ? sec(piece.fadeInSamples) : 0.01
      })
    }
  }
  return out
}

/** Place clips onto a silent track of `length` samples (15 ms fades at every clip edge). */
export function placeClips(decoded: Map<string, Stereo>, clips: MusicClip[], length: number): Stereo {
  const l = new Float32Array(length)
  const r = new Float32Array(length)
  const edge = samp(0.015)
  for (const c of clips) {
    const src = decoded.get(c.path)
    if (!src) continue
    const a = Math.max(0, Math.round(c.inSec * SAMPLE_RATE))
    const b = Math.min(src.l.length, Math.round(c.outSec * SAMPLE_RATE))
    const len = b - a
    if (len <= 0) continue
    const d0 = Math.round(c.dstSec * SAMPLE_RATE)
    const fin = Math.max(edge, samp(c.fadeInSec ?? 0.015))
    for (let i = 0; i < len; i++) {
      const d = d0 + i
      if (d < 0) continue
      if (d >= length) break
      let g = 1
      if (i < fin) g = i / fin
      if (i > len - edge) g = Math.min(g, (len - i) / edge)
      l[d] += src.l[a + i] * g
      r[d] += src.r[a + i] * g
    }
  }
  return { l, r }
}

/** Waveform for drawing: loudest level per bucket (0..1), `perSec` buckets per second. */
export function peaks(x: Stereo, perSec = 100): number[] {
  const hop = Math.max(1, Math.round(SAMPLE_RATE / perSec))
  const n = Math.ceil(x.l.length / hop)
  const out = new Array<number>(n)
  let max = 1e-6
  for (let k = 0; k < n; k++) {
    let m = 0
    const end = Math.min(x.l.length, (k + 1) * hop)
    for (let i = k * hop; i < end; i += 2) m = Math.max(m, Math.abs(x.l[i]), Math.abs(x.r[i]))
    out[k] = m
    if (m > max) max = m
  }
  return out.map((v) => Math.round((v / max) * 1000) / 1000)
}
