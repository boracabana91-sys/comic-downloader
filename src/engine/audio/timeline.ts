// Where everything goes on the final timeline. Pure math, all in samples, fully testable.
import { samp, type Phrase } from './analysis'

export interface TimelineInput {
  phrases: Phrase[]
  punchIndex: number
  /** Silence before the punch line (brief default 2.0 s). The music keeps playing through it. */
  pauseSec: number
  /** Silence before the first phrase. */
  leadInSec: number
  /** Music that rings out after the punch line ends. */
  tailSec: number
  /** Gaps between ordinary phrases are kept natural but capped so the pacing stays tight. */
  maxGapSec: number
  /** Length of the music bed (intro + punch-line track joined), or 0 if there is no music. */
  bedLength: number
  /** The hit inside the bed that must land on the punch line. */
  hitAt: number | null
}

export interface PlacedPhrase {
  index: number
  /** Where the padded clip is cut from the cleaned voice. */
  srcStart: number
  srcEnd: number
  /** Where the padded clip starts on the timeline. */
  dstStart: number
  /** Where the actual sound (not padding) starts on the timeline. */
  soundAt: number
}

export interface MusicPiece {
  /** Timeline position. */
  dst: number
  /** Range in the bed. */
  srcStart: number
  srcEnd: number
  fadeInSamples: number
}

export interface Timeline {
  phrases: PlacedPhrase[]
  /** Timeline sample where the punch line's first sound is. */
  punchAt: number
  music: MusicPiece[]
  /** Timeline sample where the music hit plays (should equal punchAt). */
  hitOnTimeline: number | null
  length: number
  /** Human-readable notes about choices made, shown in "What Cattyfied did". */
  notes: string[]
}

export const PAD = samp(0.05)

export function planTimeline(inp: TimelineInput): Timeline {
  const notes: string[] = []
  const placed: PlacedPhrase[] = []
  let cursor = samp(inp.leadInSec)
  let prevEnd = -1

  inp.phrases.forEach((p, i) => {
    if (i > 0) {
      const naturalGap = p.start - prevEnd
      const gap = i === inp.punchIndex ? samp(inp.pauseSec) : Math.min(naturalGap, samp(inp.maxGapSec))
      cursor += gap
    }
    const srcStart = Math.max(0, p.start - PAD)
    const lead = p.start - srcStart
    placed.push({ index: i, srcStart, srcEnd: p.end + PAD, dstStart: cursor - lead, soundAt: cursor })
    cursor += p.end - p.start
    prevEnd = p.end
  })

  const punch = placed[inp.punchIndex]
  const punchAt = punch.soundAt
  const punchEnd = punchAt + (inp.phrases[inp.punchIndex].end - inp.phrases[inp.punchIndex].start)
  const voiceEnd = cursor
  let length = Math.max(voiceEnd, punchEnd) + samp(inp.tailSec)

  const music: MusicPiece[] = []
  let hitOnTimeline: number | null = null
  if (inp.bedLength > 0 && inp.hitAt !== null) {
    // Bed sample `hitAt` must play at timeline sample `punchAt`.
    const bedStartOnTimeline = punchAt - inp.hitAt
    if (bedStartOnTimeline <= 0) {
      // Start inside the bed: skip its first part. Short fade-in so it doesn't start with a click.
      music.push({ dst: 0, srcStart: -bedStartOnTimeline, srcEnd: inp.bedLength, fadeInSamples: samp(0.3) })
      if (-bedStartOnTimeline > 0) notes.push(`Started the music ${(-bedStartOnTimeline / 44100).toFixed(2)} s in, so its hit lands on the punch line.`)
    } else {
      // The punch line comes later than the hit would: lengthen the start by repeating the opening
      // (stutter edit), then play the bed so the hit still lands exactly on the punch line.
      const loopLen = Math.max(samp(0.5), Math.min(samp(2), Math.floor(inp.hitAt * 0.8)))
      let need = bedStartOnTimeline
      const pre: MusicPiece[] = []
      while (need > 0) {
        const take = Math.min(loopLen, need)
        need -= take
        pre.unshift({ dst: need, srcStart: loopLen - take, srcEnd: loopLen, fadeInSamples: samp(0.02) })
      }
      pre[0].fadeInSamples = samp(0.3)
      music.push(...pre, { dst: bedStartOnTimeline, srcStart: 0, srcEnd: inp.bedLength, fadeInSamples: samp(0.02) })
      notes.push(`Repeated the start of the music to make it longer, so its hit still lands on the punch line.`)
    }
    hitOnTimeline = punchAt
    const musicEnd = music[music.length - 1].dst + (music[music.length - 1].srcEnd - music[music.length - 1].srcStart)
    if (musicEnd < length) notes.push('The music ends before the video does; the last part has no music.')
  } else if (inp.bedLength > 0) {
    music.push({ dst: 0, srcStart: 0, srcEnd: inp.bedLength, fadeInSamples: samp(0.3) })
    notes.push('No clear music hit was found, so the music simply starts at the beginning.')
  }
  length = Math.max(length, 1)
  return { phrases: placed, punchAt, music, hitOnTimeline, length, notes }
}
