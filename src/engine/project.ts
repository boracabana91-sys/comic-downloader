// The "audio brain" + draft render, end to end. No Electron here: the app passes in paths and ffmpeg.
import { promises as fs } from 'node:fs'
import { join } from 'node:path'
import { decodeAudio, encodeWav, toMono, SAMPLE_RATE, type Stereo } from './ffmpeg'
import { findPhrases, findHits, refineOnset, sec, samp, estimateTempo, type Phrase } from './audio/analysis'
import { planTimeline, PAD, type Timeline } from './audio/timeline'
import { mixTracks, concatStereo, DEFAULT_MIX } from './audio/mix'
import { normalizeLoudness, describeLoudness, type Loudness } from './loudness'
import { makeCanvas, renderVideo, grabFrame, FPS, type Visual } from './video'
import type { FormatPreset } from './formats'
import type { MusicRole } from './classify'
import { writeFileAtomic } from './atomic'
import { tempNameFor } from './paths'

/** Voice clean-up chain from the brief (step 3). */
export const VOICE_CLEAN =
  'highpass=f=85,lowpass=f=10500,afftdn=nr=12:nf=-45,agate=threshold=0.008:ratio=3:attack=4:release=120,' +
  'equalizer=f=220:t=q:w=1:g=1.5,equalizer=f=3000:t=q:w=1:g=2.5,acompressor=threshold=0.05:ratio=3:makeup=2,loudnorm=I=-13:TP=-1.5'

export interface ProjectInput {
  ffmpeg: string
  workDir: string
  voice: string
  music: { path: string; role: MusicRole }[]
  pauseSec: number
  /** null = Cattyfied's guess (the last phrase), which the owner must confirm. */
  punchIndex: number | null
  /** Which music hit to use (index into the candidates); default the strongest. */
  hitIndex?: number
  targetLufs?: number
}

export interface AudioPlan {
  phrases: { index: number; startSec: number; endSec: number; clip: string }[]
  punchIndex: number
  punchGuessed: boolean
  hits: { atSec: number; strength: number }[]
  hitIndex: number
  musicSummary: string
  tempoBpm: number | null
  punchAtSec: number
  durationSec: number
  mixWav: string
  loudness: Loudness
  loudnessText: string
  voiceOverMusicDb: number | null
  /** Independent re-measurement on the placed tracks: voice onset vs music hit, in ms. */
  syncErrorMs: number | null
  notes: string[]
  warnings: string[]
}

function pickByRole(music: ProjectInput['music'], role: MusicRole) {
  return music.find((m) => m.role === role)?.path ?? null
}

async function buildBed(ffmpeg: string, music: ProjectInput['music']) {
  const introP = pickByRole(music, 'intro')
  const punchP = pickByRole(music, 'punchline')
  const mainP = pickByRole(music, 'main')
  const notes: string[] = []
  if (introP && punchP) {
    const intro = await decodeAudio(ffmpeg, introP)
    const punch = await decodeAudio(ffmpeg, punchP)
    const bed = concatStereo(intro, punch)
    notes.push('Intro plays first; the punch-line music starts exactly where the intro ends.')
    return { bed, from: Math.max(0, intro.l.length - samp(4)), to: Math.min(bed.l.length, intro.l.length + samp(1.5)), notes, firstSoundFallback: false }
  }
  if (introP) {
    const bed = await decodeAudio(ffmpeg, introP)
    return { bed, from: Math.max(0, bed.l.length - samp(4)), to: bed.l.length, notes, firstSoundFallback: false }
  }
  if (punchP) {
    const bed = await decodeAudio(ffmpeg, punchP)
    notes.push('Only punch-line music was given, so it starts on the punch line.')
    return { bed, from: 0, to: Math.min(bed.l.length, samp(3)), notes, firstSoundFallback: true }
  }
  if (mainP) {
    const bed = await decodeAudio(ffmpeg, mainP)
    return { bed, from: samp(0.5), to: Math.max(samp(0.5), bed.l.length - samp(1)), notes, firstSoundFallback: false }
  }
  return null
}

function firstSound(x: Float32Array, upTo: number): number {
  const lim = Math.min(x.length, upTo)
  let peak = 0
  for (let i = 0; i < lim; i++) peak = Math.max(peak, Math.abs(x[i]))
  for (let i = 0; i < lim; i++) if (Math.abs(x[i]) > peak * 0.1) return refineOnset(x, Math.max(0, i - samp(0.05)), i + samp(0.1))
  return 0
}

/** "Check timing": clean the voice, find phrases + the music hit, build the synced mix. */
export async function buildAudio(inp: ProjectInput, onStep?: (s: string) => void): Promise<AudioPlan> {
  const { ffmpeg } = inp
  const warnings: string[] = []
  await fs.mkdir(join(inp.workDir, 'phrases'), { recursive: true })

  onStep?.('Cleaning your voice…')
  const voice = await decodeAudio(ffmpeg, inp.voice, VOICE_CLEAN)
  const vMono = toMono(voice)

  onStep?.('Finding the phrases in your voice…')
  let phrases: Phrase[] = findPhrases(vMono)
  if (phrases.length === 0) throw new Error('I couldn’t hear any speech in the voice file. Is it the right file?')
  const covered = phrases.reduce((a, p) => a + (p.end - p.start), 0) / vMono.length
  if (phrases.length === 1 && covered > 0.85)
    warnings.push('Your voice file has almost no pauses. If it has music mixed in, the timing may be off (music removal comes in a later update).')
  phrases = phrases.slice(0, 40)

  const punchGuessed = inp.punchIndex === null || inp.punchIndex >= phrases.length
  const punchIndex = punchGuessed ? phrases.length - 1 : (inp.punchIndex as number)

  const clips: AudioPlan['phrases'] = []
  for (let i = 0; i < phrases.length; i++) {
    const p = phrases[i]
    const a = Math.max(0, p.start - PAD)
    const b = Math.min(voice.l.length, p.end + PAD)
    const clip = join(inp.workDir, 'phrases', `phrase-${i + 1}.wav`)
    await writeFileAtomic(clip, encodeWav({ l: voice.l.subarray(a, b), r: voice.r.subarray(a, b) }))
    clips.push({ index: i, startSec: sec(p.start), endSec: sec(p.end), clip })
  }

  onStep?.('Listening to the music for the hit…')
  const bedInfo = await buildBed(ffmpeg, inp.music)
  const notes: string[] = [...(bedInfo?.notes ?? [])]
  let hits: { at: number; strength: number }[] = []
  let hitAt: number | null = null
  let tempo: number | null = null
  let bed: Stereo | null = null
  if (bedInfo) {
    bed = bedInfo.bed
    const mono = toMono(bed)
    tempo = estimateTempo(mono)
    hits = findHits(mono, { from: bedInfo.from, to: bedInfo.to })
    if (hits.length === 0) hits = findHits(mono)
    if (bedInfo.firstSoundFallback && (hits.length === 0 || hits[0].strength < 2)) {
      hits.unshift({ at: firstSound(mono, samp(3)), strength: 0 })
    }
    const hi = Math.min(inp.hitIndex ?? 0, Math.max(0, hits.length - 1))
    hitAt = hits.length ? hits[hi].at : null
    if (!hits.length) warnings.push('I couldn’t find a clear hit in the music.')
  } else {
    warnings.push('No music was dropped, so the video has only your voice.')
  }

  onStep?.('Lining up the punch line with the music hit…')
  const tl: Timeline = planTimeline({
    phrases,
    punchIndex,
    pauseSec: inp.pauseSec,
    leadInSec: 0.4,
    tailSec: 2.5,
    maxGapSec: 0.6,
    bedLength: bed ? bed.l.length : 0,
    hitAt
  })
  notes.push(...tl.notes)
  notes.push(`Put a ${inp.pauseSec.toFixed(1)} s pause before the punch line; the music keeps playing through it.`)

  onStep?.('Mixing voice and music…')
  const mixed = mixTracks(voice, bed, tl, DEFAULT_MIX)

  // Independent check on the placed tracks: re-detect the voice onset and the music hit near the punch line.
  let syncErrorMs: number | null = null
  if (bed && hitAt !== null) {
    const win = samp(0.6)
    const vOn = findPhrases(toMono(mixed.voiceTrack)).map((p) => p.start).reduce((best, s) => (Math.abs(s - tl.punchAt) < Math.abs(best - tl.punchAt) ? s : best), Number.MAX_SAFE_INTEGER)
    const mHits = findHits(toMono(mixed.musicTrack), { from: Math.max(0, tl.punchAt - win), to: tl.punchAt + win, count: 1 })
    if (mHits.length && vOn !== Number.MAX_SAFE_INTEGER) syncErrorMs = Math.round(((mHits[0].at - vOn) / SAMPLE_RATE) * 1000)
  }

  onStep?.('Setting the loudness…')
  const rawWav = join(inp.workDir, 'mix-raw.wav')
  const finalWav = join(inp.workDir, 'mix.wav')
  await writeFileAtomic(rawWav, encodeWav(mixed.mix))
  const loud = await normalizeLoudness(ffmpeg, rawWav, tempNameFor(finalWav) + '.wav', inp.targetLufs ?? -14)
  await fs.rename(tempNameFor(finalWav) + '.wav', finalWav)

  return {
    phrases: clips,
    punchIndex,
    punchGuessed,
    hits: hits.map((h) => ({ atSec: sec(h.at), strength: h.strength })),
    hitIndex: Math.min(inp.hitIndex ?? 0, Math.max(0, hits.length - 1)),
    musicSummary: bed ? `Music hit at ${hitAt !== null ? sec(hitAt).toFixed(2) : '—'} s of the music${tempo ? `, about ${tempo} BPM` : ''}.` : 'No music.',
    tempoBpm: tempo,
    punchAtSec: sec(tl.punchAt),
    durationSec: sec(tl.length),
    mixWav: finalWav,
    loudness: loud,
    loudnessText: describeLoudness(loud),
    voiceOverMusicDb: mixed.voiceOverMusicDb,
    syncErrorMs,
    notes,
    warnings
  }
}

export interface RenderResult {
  video: string
  frames: { label: string; path: string }[]
  /** Offset between the finished MP4's sound and the planned mix (encoder delay check), in ms. */
  encoderOffsetMs: number | null
  qa: { ok: boolean; text: string }[]
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

  // QA: re-open the finished file and check it.
  const frames: RenderResult['frames'] = []
  const P = plan.punchAtSec
  for (const [label, t] of [['Just before the punch line', P - 0.4], ['The punch line', P + 0.1], ['Right after', P + 0.6]] as const) {
    const f = join(opts.workDir, `frame-${fmt.id}-${label.replace(/\W+/g, '-').toLowerCase()}.jpg`)
    await grabFrame(ffmpeg, opts.outFile, Math.max(0, t), f)
    frames.push({ label, path: f })
  }

  const planned = toMono(await decodeAudio(ffmpeg, plan.mixWav))
  const got = toMono(await decodeAudio(ffmpeg, opts.outFile))
  let encoderOffsetMs: number | null = null
  try {
    encoderOffsetMs = Math.round((measureShift(planned, got, samp(P), samp(0.05)) / SAMPLE_RATE) * 1000)
  } catch {
    encoderOffsetMs = null
  }
  const frameMs = 1000 / FPS
  const qa: RenderResult['qa'] = []
  if (plan.syncErrorMs !== null)
    qa.push({ ok: Math.abs(plan.syncErrorMs) <= frameMs, text: `Punch line vs music hit: ${plan.syncErrorMs} ms apart (must be within one frame, ${frameMs.toFixed(0)} ms).` })
  if (encoderOffsetMs !== null)
    qa.push({ ok: Math.abs(encoderOffsetMs) <= frameMs / 2, text: `Sound in the finished video is ${encoderOffsetMs} ms from the planned mix.` })
  qa.push({ ok: plan.loudness.truePeakDb < -1, text: plan.loudnessText })
  if (plan.voiceOverMusicDb !== null)
    qa.push({ ok: plan.voiceOverMusicDb >= 6 && plan.voiceOverMusicDb <= 10, text: `Your voice is ${plan.voiceOverMusicDb.toFixed(1)} dB above the music while you speak (goal: about 8).` })
  return { video: opts.outFile, frames, encoderOffsetMs, qa }
}
