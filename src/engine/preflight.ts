// Preflight gate (FIX_PROMPT §2.5 + §3): measured on the FINISHED mp4, plain-English PASS/FAIL with the
// measured number. A failed check is never hidden.
import { runTool, decodeAudio, toMono, SAMPLE_RATE } from './ffmpeg'
import { measureLoudness } from './loudness'
import type { Timeline } from './audio/brain'
import type { FrameLog } from './draw/render'

export interface Check { id: string; ok: boolean; text: string; measured: string }

const FPS = 30

/** Grayscale thumbnails of every frame (w×h bytes each). */
export async function grayFrames(ffmpeg: string, video: string, w = 72, h = 128): Promise<Uint8Array[]> {
  const { stdout } = await runTool(ffmpeg, ['-v', 'error', '-i', video, '-vf', `scale=${w}:${h},format=gray`, '-f', 'rawvideo', 'pipe:1'])
  const n = Math.floor(stdout.length / (w * h))
  return Array.from({ length: n }, (_, i) => new Uint8Array(stdout.buffer, stdout.byteOffset + i * w * h, w * h))
}

export const meanOf = (a: Uint8Array) => { let s = 0; for (const v of a) s += v; return s / a.length }
const mad = (a: Uint8Array, b: Uint8Array) => { let s = 0; for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]); return s / a.length }

/** Frames that are a white flash: much brighter than the frames around them. */
export function flashFrames(frames: Uint8Array[]): number[] {
  const m = frames.map(meanOf)
  const out: number[] = []
  for (let i = 0; i < m.length; i++) {
    const around = [m[i - 4], m[i - 5], m[i + 6], m[i + 7]].filter((x) => x !== undefined) as number[]
    const base = around.length ? Math.min(...around) : 0
    if (m[i] > base + 45 && m[i] > 150 && !(m[i - 1] > base + 45 && m[i - 1] > 150)) out.push(i)
  }
  return out
}

/** Share of (t, t+4 s) frame pairs that are near-identical — a repeating loop scores high. */
export function loopScore(frames: Uint8Array[], lagSec = 4, thr = 2.0): number {
  const lag = Math.round(lagSec * FPS)
  let same = 0
  let n = 0
  for (let i = 0; i + lag < frames.length; i++) {
    n++
    if (mad(frames[i], frames[i + lag]) < thr) same++
  }
  return n ? same / n : 0
}

export async function preflight(opts: {
  ffmpeg: string
  video: string
  plannedMix: string
  timeline: Timeline
  pauseWanted: number
  syncErrorMs: number | null
  renderLog?: FrameLog[]
  voiceTrack?: Float32Array // vo.wav mono, to know where the voice is silent
}): Promise<Check[]> {
  const { ffmpeg, timeline: tl } = opts
  const checks: Check[] = []
  const add = (id: string, ok: boolean, text: string, measured: string) => checks.push({ id, ok, text, measured })
  const P = tl.punch_time

  // Audio timing (re-measured from the placed audio during Check timing).
  if (opts.syncErrorMs !== null)
    add('downbeat', Math.abs(opts.syncErrorMs) <= 20, 'The music’s beat lands on the punch line (within 0.02 s)', `${opts.syncErrorMs} ms`)
  const punchStart = Math.min(...tl.placed.filter((p) => tl.punch_units.includes(p.unit)).map((p) => p.dest[0]))
  add('punch_voice', Math.abs(punchStart - P) <= 0.04, 'Your punch line starts on the punch time (within 0.04 s)', `${((punchStart - P) * 1000).toFixed(0)} ms`)
  add('pause', Math.abs(tl.pause_before_punch - opts.pauseWanted) <= 0.05, `Pause before the punch line is ${opts.pauseWanted.toFixed(1)} s (within 0.05 s)`, `${tl.pause_before_punch.toFixed(2)} s`)
  if (tl.music_clips.length) add('vom', tl.voice_over_music_db >= 8, 'Your voice is at least 8 dB above the music while you speak', `${tl.voice_over_music_db.toFixed(1)} dB`)

  // The finished file.
  const L = await measureLoudness(ffmpeg, opts.video)
  add('lufs', L.lufs >= -16.5 && L.lufs <= -14, 'Loudness between −16.5 and −14 LUFS', `${L.lufs.toFixed(1)} LUFS`)
  add('peak', L.truePeakDb <= -1, 'Peaks stay below −1 dB (no distortion)', `${L.truePeakDb.toFixed(1)} dB`)
  const info = await runTool(ffmpeg, ['-i', opts.video]).catch((e: Error) => ({ stderr: e.message }))
  const d = info.stderr.match(/Duration: (\d+):(\d+):([\d.]+)/)
  const dur = d ? Number(d[1]) * 3600 + Number(d[2]) * 60 + Number(d[3]) : 0
  add('length', Math.abs(dur - tl.duration) <= 1 / FPS + 0.02, `Video is ${tl.duration.toFixed(1)} s long`, `${dur.toFixed(2)} s`)

  // Sound in the mp4 vs the planned mix (encoder delay).
  const planned = toMono(await decodeAudio(ffmpeg, opts.plannedMix))
  const got = toMono(await decodeAudio(ffmpeg, opts.video))
  const { measureShift } = await import('./project')
  const off = Math.round((measureShift(planned, got, Math.round(P * SAMPLE_RATE), Math.round(0.05 * SAMPLE_RATE)) / SAMPLE_RATE) * 1000)
  add('av', Math.abs(off) <= 17, 'Sound in the video is in sync with the picture plan', `${off} ms`)

  // Picture: flashes on every cut and on the punch line; no loop.
  const frames = await grayFrames(ffmpeg, opts.video)
  const flashes = flashFrames(frames)
  const cutFrames = [P, ...tl.cuts].map((c) => Math.round(c * FPS))
  const missing = cutFrames.filter((c) => !flashes.some((f) => Math.abs(f - c) <= 1))
  add('flashes', missing.length === 0, 'A white flash on the punch line and on every cut (within 1 frame)',
    missing.length ? `missing at ${missing.map((c) => (c / FPS).toFixed(2) + ' s').join(', ')}` : `${cutFrames.length}/${cutFrames.length} found`)
  const loop = loopScore(frames)
  add('noloop', loop <= 0.3, 'No repeating loop (frames 4 s apart are different)', `${Math.round(loop * 100)}% look the same`)

  // Mouth closed when the voice is silent (from the renderer's per-frame log, checked against vo.wav).
  if (opts.renderLog?.length && opts.voiceTrack) {
    const vo = opts.voiceTrack
    const hop = Math.floor(SAMPLE_RATE / FPS)
    const rms = (f: number) => { let s = 0; for (let i = f * hop; i < (f + 1) * hop && i < vo.length; i++) s += vo[i] * vo[i]; return Math.sqrt(s / hop) }
    const all = opts.renderLog.map((l) => rms(l.f)).sort((a, b) => a - b)
    const p95 = all[Math.floor(all.length * 0.95)] || 1e-9
    const silent = (f: number) => [f - 2, f - 1, f, f + 1, f + 2].every((k) => rms(k) < 0.12 * p95)
    const pre = tl.placed.filter((p) => !tl.punch_units.includes(p.unit)).map((p) => p.dest[1])
    const lastVoice = Math.max(...tl.placed.map((p) => p.dest[1]))
    const windows: [number, number][] = [[Math.max(...pre) + 0.25, P - 0.05], [lastVoice + 0.3, tl.duration]]
    let worst = 0
    let n = 0
    for (const l of opts.renderLog) {
      const t = l.f / FPS
      if (!windows.some(([a, b]) => t >= a && t <= b) || !silent(l.f)) continue
      n++
      worst = Math.max(worst, l.talk)
    }
    add('mouth', worst < 0.1, 'Mouth stays closed when the voice is silent (pause and the end)', `max opening ${worst.toFixed(2)} over ${n} silent frames`)
  }
  return checks
}

/** Per-second loudness curve (dB RMS) — used to compare a video with the golden reference. */
export async function loudnessCurve(ffmpeg: string, video: string): Promise<number[]> {
  const a = toMono(await decodeAudio(ffmpeg, video))
  const out: number[] = []
  for (let s = 0; s * SAMPLE_RATE < a.length; s++) {
    let e = 0
    const b = Math.min(a.length, (s + 1) * SAMPLE_RATE)
    for (let i = s * SAMPLE_RATE; i < b; i++) e += a[i] * a[i]
    out.push(Math.round(10 * Math.log10(e / (b - s * SAMPLE_RATE) + 1e-12) * 10) / 10)
  }
  return out
}
