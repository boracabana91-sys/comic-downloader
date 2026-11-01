// The whole "check timing" + render pipeline. No Electron here: the app passes in paths, ffmpeg and onnxruntime.
// Design (FIX_PROMPT): measure → timeline.json → render → verify. Nothing about timing is hard-coded.
import { promises as fs } from 'node:fs'
import { join } from 'node:path'
import { decodeAudio, decodeMono, encodeWav, toMono, SAMPLE_RATE, type Stereo } from './ffmpeg'
import { findHits, sec, samp } from './audio/analysis'
import { runBrain, findPhrases as brainPhrases, groupUnits, CLEAN, type Timeline } from './audio/brain'
import { isolateVocals, type OrtLike } from './audio/mdx'
import { peaks, type MusicClip } from './audio/clips'
import { describeLoudness, type Loudness } from './loudness'
import { makeCanvas, renderVideo, grabFrame, FPS, type Visual } from './video'
import type { FormatPreset } from './formats'
import type { MusicRole } from './classify'
import { writeFileAtomic } from './atomic'
import { tempNameFor } from './paths'

export interface ProjectInput {
  ffmpeg: string
  workDir: string
  voice: string
  music: { path: string; role: MusicRole }[]
  pauseSec: number
  /** Which units are the punch line (0-based). null = Cattyfied's guess (the last unit), which the owner must confirm. */
  punchUnits: number[] | null
  /**
   * Vocal isolation (UVR-MDX): reads a 44.1 kHz stereo WAV, writes the vocal stem WAV.
   * null = not available (e.g. Intel Macs): the voice is used as it is, with a warning.
   */
  mdx: Isolator | null
  punchTime?: number
  duration?: number
  targetLufs?: number
  /** 'draw' = animated cartoon. (The reference timing is the same for every style.) */
  style?: 'draw' | 'frame'
  /** Music placed by hand in the timeline editor (relative to the punch line). */
  manualMusic?: { path: string; dstFromPunchSec: number; inSec: number; outSec: number | null }[]
}

export type Isolator = (inWav: string, outWav: string, onProgress: (f: number) => void) => Promise<void>

/** In-process isolator (plain Node: tests, CLI). The app uses a helper process instead (see main/mdx-worker). */
export function inProcessIsolator(ffmpeg: string, ort: OrtLike, modelPath: string): Isolator {
  return async (inWav, outWav, onProgress) => {
    const voc = await isolateVocals(ort, modelPath, await decodeAudio(ffmpeg, inWav), onProgress)
    await writeFileAtomic(outWav, encodeWav(voc))
  }
}

export interface EditorData {
  pps: number
  voicePeaks: number[]
  files: { path: string; durSec: number; peaks: number[]; hitsSec: number[] }[]
  clips: MusicClip[]
  manual: boolean
}

export interface AudioPlan {
  /** The units of the voice (what the owner picks the punch line from), with a clip each to listen to. */
  phrases: { index: number; startSec: number; endSec: number; clip: string }[]
  punchUnits: number[]
  punchGuessed: boolean
  /** True when the voice had no 0.9 s pause, so smaller phrases are offered instead of units. */
  unitsFromPhrases: boolean
  musicSummary: string
  punchAtSec: number
  durationSec: number
  mixWav: string
  /** Voice only, placed on the timeline (vo.wav) — the mouth is driven by THIS, never by the mix. */
  voiceTrackWav: string
  timelineJson: string
  timeline: Timeline
  loudness: Loudness
  loudnessText: string
  voiceOverMusicDb: number | null
  /** Independent re-measurement: music hit near the punch line vs the punch-line voice start, in ms. */
  syncErrorMs: number | null
  isolated: boolean
  notes: string[]
  warnings: string[]
  /** Units placed on the timeline (seconds), for the director. */
  timelinePhrases: { start: number; end: number; unit: number; punch: boolean }[]
  cutsSec: number[]
  editor: EditorData
  /** The pause the owner asked for (the preflight checks the timeline matches it). */
  pauseWanted: number
}

function pickByRole(music: ProjectInput['music'], role: MusicRole) {
  return music.find((m) => m.role === role)?.path ?? null
}

/** Check timing: isolate + clean the voice, find units, place them, align the music, mix, verify. */
export async function buildAudio(inp: ProjectInput, onStep?: (s: string, f?: number | null) => void): Promise<AudioPlan> {
  const { ffmpeg } = inp
  const warnings: string[] = []
  await fs.mkdir(join(inp.workDir, 'phrases'), { recursive: true })

  onStep?.('Reading your voice…')
  const voice = await decodeAudio(ffmpeg, inp.voice)
  const vocWav = join(inp.workDir, 'voc.wav')
  let isolated = false
  if (inp.mdx) {
    const voice44 = join(inp.workDir, 'voice44.wav')
    await writeFileAtomic(voice44, encodeWav(voice))
    onStep?.('Separating your voice from any music in the file…', 0)
    await inp.mdx(voice44, vocWav, (f) => onStep?.('Separating your voice from any music in the file…', f))
    isolated = true
  } else {
    warnings.push('Music removal from the voice isn’t available on this Mac, so the voice file is used as it is. If it has music in it, the timing and mouth may be off.')
    await writeFileAtomic(vocWav, encodeWav(voice))
  }
  const vocQ = await decodeAudio(ffmpeg, vocWav) // same 16-bit rounding as the reference
  onStep?.('Cleaning your voice…')
  const vClean = await decodeMono(ffmpeg, vocWav, CLEAN)

  onStep?.('Finding the parts of your voice…')
  const phrases = brainPhrases(vocQ)
  if (!phrases.length) throw new Error('I couldn’t hear any speech in the voice file. Is it the right file?')
  let units = groupUnits(phrases)
  let unitsFromPhrases = false
  if (units.length < 2 && phrases.length >= 2) {
    units = phrases
    unitsFromPhrases = true
    warnings.push('Your voice has no clear pause (0.9 s or more) between lines, so I split it at the shorter pauses instead. Please check which part is the punch line.')
  }
  const covered = phrases.reduce((a, p) => a + (p[1] - p[0]), 0) / (vocQ.l.length / SAMPLE_RATE)
  if (units.length < 2 && covered > 0.85) warnings.push('Your voice file has almost no pauses. If it still has music in it, the timing may be off.')

  const punchGuessed = !inp.punchUnits?.length
  const punchUnits = punchGuessed ? [units.length - 1] : inp.punchUnits!.filter((i) => i >= 0 && i < units.length)

  const clips: AudioPlan['phrases'] = []
  for (let i = 0; i < units.length; i++) {
    const [s0, s1] = units[i]
    const a = Math.max(0, Math.round((s0 - 0.05) * SAMPLE_RATE))
    const b = Math.min(vClean.length, Math.round((s1 + 0.05) * SAMPLE_RATE))
    const clip = join(inp.workDir, 'phrases', `part-${i + 1}.wav`)
    const seg = vClean.subarray(a, b)
    await writeFileAtomic(clip, encodeWav({ l: seg, r: seg }))
    clips.push({ index: i, startSec: s0, endSec: s1, clip })
  }

  onStep?.('Listening to the music…')
  const cache = new Map<string, Stereo>()
  const dec = async (p: string) => {
    let a = cache.get(p)
    if (!a) { a = await decodeAudio(ffmpeg, p); cache.set(p, a) }
    return a
  }
  const introPath = pickByRole(inp.music, 'intro') ?? pickByRole(inp.music, 'main')
  const chorusPath = pickByRole(inp.music, 'punchline')
  let singleHitSec: number | null = null
  if (introPath && !chorusPath) {
    const h = findHits(toMono(await dec(introPath)), { count: 1 })
    singleHitSec = h.length ? sec(h[0].at) : null
  }
  const manualMusic = inp.manualMusic?.length
    ? await Promise.all(inp.manualMusic.map(async (m) => ({ ...m, audio: await dec(m.path) })))
    : undefined

  onStep?.('Lining up the punch line with the music…')
  const brain = await runBrain({
    ffmpeg, workDir: inp.workDir, voc: vocQ, vClean,
    intro: introPath ? await dec(introPath) : null, introPath,
    chorus: chorusPath ? await dec(chorusPath) : null, chorusPath,
    punchTime: inp.punchTime, pause: inp.pauseSec, duration: inp.duration, punchUnits,
    targetLufs: inp.targetLufs, unitsOverride: units, singleHitSec, manualMusic
  })
  const tl = brain.timeline
  if (!inp.music.length && !manualMusic) warnings.push('No music was dropped, so the video has only your voice.')

  // Independent check, re-measured from the PLACED audio (not from the plan's numbers):
  // with a punch-line track, its first downbeat must sit on the punch time (reference: ±0.02 s);
  // otherwise (one song / hand placement) the strongest hit near the punch line is measured.
  let syncErrorMs: number | null = null
  if (tl.music_clips.length) {
    const { placeClips } = await import('./audio/clips')
    const { firstDownbeat } = await import('./audio/brain')
    const N = Math.round(tl.duration * SAMPLE_RATE)
    const P = tl.punch_time
    const chorusClip = !tl.manual_music && chorusPath ? tl.music_clips.find((c) => c.path === chorusPath) : undefined
    if (chorusClip) {
      const only = placeClips(new Map([[chorusPath!, await dec(chorusPath!)]]), [chorusClip], N)
      const a = Math.max(0, Math.round(chorusClip.dstSec * SAMPLE_RATE))
      const db = firstDownbeat({ l: only.l.subarray(a), r: only.r.subarray(a) })
      syncErrorMs = Math.round((a / SAMPLE_RATE + db - P) * 1000)
    } else {
      const decoded = new Map<string, Stereo>()
      for (const c of tl.music_clips) decoded.set(c.path, await dec(c.path))
      const mus = toMono(placeClips(decoded, tl.music_clips, N))
      const Ps = samp(P)
      const h = findHits(mus, { from: Math.max(0, Ps - samp(0.6)), to: Ps + samp(0.6), count: 1 })
      if (h.length) syncErrorMs = Math.round(((h[0].at - Ps) / SAMPLE_RATE) * 1000)
    }
  }

  const files: EditorData['files'] = []
  for (const p of [...new Set([...inp.music.map((m) => m.path), ...tl.music_clips.map((c) => c.path)])]) {
    const a = await dec(p)
    files.push({ path: p, durSec: sec(a.l.length), peaks: peaks(a, 100), hitsSec: findHits(toMono(a), { count: 6 }).map((h) => sec(h.at)).sort((x, y) => x - y) })
  }

  return {
    phrases: clips,
    punchUnits: tl.punch_units,
    punchGuessed,
    unitsFromPhrases,
    musicSummary: tl.chorus_downbeat != null ? `The music’s beat lands exactly on the punch line at ${tl.punch_time.toFixed(2)} s.` : tl.music_clips.length ? 'Music placed.' : 'No music.',
    punchAtSec: tl.punch_time,
    durationSec: tl.duration,
    mixWav: brain.mixWav,
    voiceTrackWav: brain.voWav,
    timelineJson: brain.timelineJson,
    timeline: tl,
    loudness: brain.loudness,
    loudnessText: describeLoudness(brain.loudness),
    voiceOverMusicDb: tl.music_clips.length ? tl.voice_over_music_db : null,
    syncErrorMs,
    isolated,
    notes: tl.notes.concat([`Put a ${tl.pause_before_punch.toFixed(2)} s pause before the punch line; the music keeps playing through it.`]),
    warnings,
    timelinePhrases: tl.placed.map((p) => ({ start: p.dest[0], end: p.dest[1], unit: p.unit, punch: tl.punch_units.includes(p.unit) })),
    cutsSec: [tl.punch_time, ...tl.cuts],
    editor: { pps: 100, voicePeaks: brain.voicePeaks, files, clips: tl.music_clips, manual: tl.manual_music },
    pauseWanted: inp.pauseSec
  }
}

export interface RenderResult {
  video: string
  frames: { label: string; path: string }[]
  /** Offset between the finished MP4's sound and the planned mix (encoder delay check), in ms. */
  encoderOffsetMs: number | null
  qa: { ok: boolean; text: string }[]
  allOk: boolean
}

/** Cross-correlate two mono signals near `center` to find a small time shift (±maxLag samples). */
export function measureShift(a: Float32Array, b: Float32Array, center: number, maxLag: number): number {
  const half = samp(0.75)
  const s0 = Math.max(maxLag, center - half)
  const s1 = Math.min(a.length - maxLag, b.length - maxLag, center + half)
  let best = 0
  let bestLag = 0
  for (let lag = -maxLag; lag <= maxLag; lag += 4) {
    let s = 0
    for (let i = s0; i < s1; i += 2) s += a[i] * b[i + lag]
    if (s > best) { best = s; bestLag = lag }
  }
  for (let lag = bestLag - 4; lag <= bestLag + 4; lag++) {
    let s = 0
    for (let i = s0; i < s1; i += 2) s += a[i] * b[i + lag]
    if (s > best) { best = s; bestLag = lag }
  }
  return bestLag
}

export async function renderDraft(opts: {
  ffmpeg: string
  workDir: string
  outFile: string
  plan: AudioPlan
  visual: Visual
  fmt: FormatPreset
  onProgress?: (f: number) => void
}): Promise<RenderResult> {
  const { ffmpeg, plan, fmt } = opts
  let canvas: string | undefined
  const renderLog: import('./draw/render').FrameLog[] = []
  if (opts.visual.type === 'drawn') {
    const partial0 = tempNameFor(opts.outFile)
    try {
      const { renderDrawn } = await import('./draw/render')
      await renderDrawn({
        log: renderLog,
        ffmpeg, fmt, timeline: plan.timeline,
        voiceTrack: await decodeAudio(ffmpeg, plan.voiceTrackWav), audioWav: plan.mixWav, outPartial: partial0, onProgress: opts.onProgress
      })
      await fs.rename(partial0, opts.outFile)
    } catch (e) {
      await fs.rm(partial0, { force: true })
      throw e
    }
    return finishQa(ffmpeg, opts.workDir, opts.outFile, plan, fmt, renderLog)
  }
  if (opts.visual.type === 'picture') {
    canvas = join(opts.workDir, `canvas-${fmt.id}.png`)
    await makeCanvas(ffmpeg, opts.visual.path, fmt, canvas)
  }
  const partial = tempNameFor(opts.outFile)
  try {
    await renderVideo({
      ffmpeg, visual: opts.visual, canvas, fmt, audioWav: plan.mixWav,
      durationSec: plan.durationSec, punchSec: plan.punchAtSec, outPartial: partial, onProgress: opts.onProgress
    })
    await fs.rename(partial, opts.outFile)
  } catch (e) {
    await fs.rm(partial, { force: true })
    throw e
  }
  return finishQa(ffmpeg, opts.workDir, opts.outFile, plan, fmt)
}

async function finishQa(ffmpeg: string, workDir: string, outFile: string, plan: AudioPlan, fmt: FormatPreset, renderLog?: import('./draw/render').FrameLog[]): Promise<RenderResult> {
  // Preflight: re-open the finished file and check it (FIX_PROMPT §3). Failed checks are never hidden.
  const frames: RenderResult['frames'] = []
  const P = plan.punchAtSec
  for (const [label, t] of [['Just before the punch line', P - 0.4], ['The punch line', P + 0.1], ['Right after', P + 0.6]] as const) {
    const f = join(workDir, `frame-${fmt.id}-${label.replace(/\W+/g, '-').toLowerCase()}.jpg`)
    await grabFrame(ffmpeg, outFile, Math.max(0, t), f)
    frames.push({ label, path: f })
  }
  const { preflight } = await import('./preflight')
  const voiceTrack = toMono(await decodeAudio(ffmpeg, plan.voiceTrackWav))
  const checks = await preflight({
    ffmpeg, video: outFile, plannedMix: plan.mixWav, timeline: plan.timeline, pauseWanted: plan.pauseWanted,
    syncErrorMs: plan.syncErrorMs, renderLog: renderLog?.length ? renderLog : undefined, voiceTrack
  })
  await writeFileAtomic(join(workDir, 'preflight.json'), JSON.stringify(checks, null, 1))
  const qa = checks.map((c) => ({ ok: c.ok, text: `${c.text}: ${c.measured}` }))
  return { video: outFile, frames, encoderOffsetMs: null, qa, allOk: checks.every((c) => c.ok) }
}
