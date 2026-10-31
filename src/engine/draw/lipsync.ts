// Mouth movement from the voice-only track (brief: per-frame RMS, fast attack 0.7, slow release 0.35;
// mouth width from the spectral centroid).
import { SAMPLE_RATE, type Stereo } from '../ffmpeg'

export interface MouthFrame {
  open: number // 0..1
  wide: number // 0..1
}

function fftMag(re: Float32Array): Float32Array {
  const n = re.length
  const im = new Float32Array(n)
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1
    for (; j & bit; bit >>= 1) j ^= bit
    j ^= bit
    if (i < j) { const t = re[i]; re[i] = re[j]; re[j] = t }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len
    for (let i = 0; i < n; i += len) {
      for (let k = 0; k < len / 2; k++) {
        const wr = Math.cos(ang * k)
        const wi = Math.sin(ang * k)
        const ur = re[i + k], ui = im[i + k]
        const vr = re[i + k + len / 2] * wr - im[i + k + len / 2] * wi
        const vi = re[i + k + len / 2] * wi + im[i + k + len / 2] * wr
        re[i + k] = ur + vr; im[i + k] = ui + vi
        re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi
      }
    }
  }
  const mag = new Float32Array(n / 2)
  for (let i = 0; i < n / 2; i++) mag[i] = Math.hypot(re[i], im[i])
  return mag
}

export function mouthTrack(voice: Stereo, fps: number, frames: number): MouthFrame[] {
  const hop = SAMPLE_RATE / fps
  const N = 1024
  const rms: number[] = []
  const cen: number[] = []
  for (let f = 0; f < frames; f++) {
    const a = Math.floor(f * hop)
    let s = 0
    const buf = new Float32Array(N)
    for (let i = 0; i < N; i++) {
      const k = a + i
      const v = k < voice.l.length ? 0.5 * (voice.l[k] + voice.r[k]) : 0
      if (i < hop) s += v * v
      buf[i] = v * (0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (N - 1)))
    }
    rms.push(Math.sqrt(s / hop))
    const mag = fftMag(buf)
    let num = 0, den = 0
    for (let i = 1; i < mag.length; i++) { num += i * mag[i]; den += mag[i] }
    cen.push(den > 1e-9 ? (num / den) * (SAMPLE_RATE / N) : 0)
  }
  const sorted = [...rms].sort((x, y) => x - y)
  const ref = Math.max(1e-6, sorted[Math.floor(sorted.length * 0.95)] ?? 1e-6)
  const out: MouthFrame[] = []
  let open = 0
  let wide = 0.5
  for (let f = 0; f < frames; f++) {
    const target = Math.min(1, Math.max(0, (rms[f] / ref - 0.06) * 1.15))
    open += (target - open) * (target > open ? 0.7 : 0.35)
    // Brighter sounds (ee, s) = wider mouth; darker (oo, o) = rounder.
    const w = Math.min(1, Math.max(0, (cen[f] - 600) / 2400))
    if (open > 0.05) wide += (w - wide) * 0.5
    out.push({ open: open < 0.04 ? 0 : open, wide })
  }
  return out
}
