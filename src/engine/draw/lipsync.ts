// Lip-sync from the VOICE-ONLY track (vo.wav) — never from the mix. Port of cat_core.py:
// per-frame RMS, normalised to the 95th percentile, clipped 0..1, anything under 0.12 = closed,
// then fast attack (0.7) / slow release (0.35). Width from the spectral centroid (800–3300 Hz → 0..1),
// smoothed over 5 frames.
import { SAMPLE_RATE, type Stereo } from '../ffmpeg'
import { _Bluestein as Bluestein } from '../audio/mdx'

const dfts = new Map<number, Bluestein>()

export interface MouthFrame {
  open: number // 0..1 ("talk")
  wide: number // 0..1 (centroid)
}

function centroid(seg: Float64Array): number {
  const n = seg.length
  if (n < 64) return 1500
  // Exact-length DFT (n = 1470 at 30 fps) of the Hann-windowed segment, like np.fft.rfft(seg*np.hanning(n)).
  let F = dfts.get(n)
  if (!F) { F = new Bluestein(n); dfts.set(n, F) }
  const re = new Float64Array(n)
  const im = new Float64Array(n)
  for (let i = 0; i < n; i++) re[i] = seg[i] * (0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1)))
  F.forward(re, im)
  const bins = Math.floor(n / 2) + 1
  let num = 0
  let den = 0
  for (let k = 0; k < bins; k++) {
    const mag = Math.hypot(re[k], im[k])
    num += mag * ((k * SAMPLE_RATE) / n)
    den += mag
  }
  return num / (den + 1e-9)
}

export function mouthTrack(voice: Stereo, fps: number, frames: number): MouthFrame[] {
  const hop = Math.floor(SAMPLE_RATE / fps)
  const mono = (k: number) => (k < voice.l.length ? 0.5 * (voice.l[k] + voice.r[k]) : 0)
  const env = new Float64Array(frames)
  const cen = new Float64Array(frames)
  const sorted: number[] = []
  for (let f = 0; f < frames; f++) {
    let s = 0
    const seg = new Float64Array(hop)
    for (let i = 0; i < hop; i++) { const v = mono(f * hop + i); seg[i] = v; s += v * v }
    env[f] = f * hop < voice.l.length ? Math.sqrt(s / hop) : 0
    sorted.push(env[f])
    // centroid only where there is sound (silent frames are closed anyway)
    cen[f] = env[f] > 1e-5 ? Math.min(1, Math.max(0, (centroid(seg) - 800) / 2500)) : 0
  }
  sorted.sort((a, b) => a - b)
  const p95 = percentile(sorted, 95)
  let v = 0
  const out: MouthFrame[] = []
  const cs = new Float64Array(frames)
  for (let f = 0; f < frames; f++) {
    let k = 0, c = 0
    for (let j = f - 2; j <= f + 2; j++) if (j >= 0 && j < frames) { k += cen[j]; c++ }
    cs[f] = k / 5 // np.convolve(.., ones(5)/5, "same")
    void c
  }
  for (let f = 0; f < frames; f++) {
    let e = Math.min(1, Math.max(0, env[f] / (p95 + 1e-9)))
    if (e < 0.12) e = 0
    v = v + (e - v) * (e > v ? 0.7 : 0.35)
    out.push({ open: v, wide: cs[f] })
  }
  return out
}

/** numpy-style linear-interpolated percentile on a sorted array. */
function percentile(sorted: number[], q: number): number {
  if (!sorted.length) return 0
  const pos = ((sorted.length - 1) * q) / 100
  const lo = Math.floor(pos)
  const hi = Math.min(sorted.length - 1, lo + 1)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo)
}
