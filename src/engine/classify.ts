// Engine code: no Electron, no UI, no macOS-only calls. Must stay portable (Windows later).

export type AssetKind = 'voice' | 'music' | 'character' | 'background' | 'video' | 'notes' | 'unknown'

export const KIND_LABELS: Record<AssetKind, string> = {
  voice: 'Voice',
  music: 'Music',
  character: 'Character picture',
  background: 'Background picture',
  video: 'Video clip',
  notes: 'Notes',
  unknown: 'Not sure'
}

export interface Guess {
  kind: AssetKind
  /** true when we are not confident and must ask the user (voice vs music, character vs background). */
  ambiguous: boolean
  reason: string
}

/**
 * When a music file is part of an intro→punch-line pair (see the brief, section 5.5): the intro
 * plays first and ends on a hit; the punch-line track then starts right at that hit, timed to the
 * character's line. "main" = a single, standalone bed with no separate intro.
 */
export type MusicRole = 'intro' | 'punchline' | 'main'

const INTRO_WORDS = ['intro', 'into', 'lead-in', 'leadin', 'open', 'opening', 'buildup', 'build-up']
const PUNCHLINE_WORDS = ['chorus', 'hook', 'drop', 'main', 'loop', 'punch', 'punchline']

/** Guess whether a music file is the intro or the punch-line part, from its file name only. */
export function guessMusicRole(fileName: string): { role: MusicRole; ambiguous: boolean } {
  const ws = words(fileName)
  const i = hits(ws, INTRO_WORDS)
  const p = hits(ws, PUNCHLINE_WORDS)
  if (i > p) return { role: 'intro', ambiguous: false }
  if (p > i) return { role: 'punchline', ambiguous: false }
  return { role: 'main', ambiguous: true }
}

const AUDIO = ['wav', 'mp3', 'm4a', 'aac', 'aif', 'aiff', 'flac', 'ogg', 'opus', 'caf']
const IMAGE = ['png', 'jpg', 'jpeg', 'webp', 'heic', 'gif', 'bmp', 'tif', 'tiff']
const VIDEO = ['mp4', 'mov', 'm4v', 'webm', 'mkv', 'avi']
const NOTES = ['txt', 'md', 'rtf', 'doc', 'docx', 'pages']

const VOICE_WORDS = ['voice', 'vo', 'voiceover', 'narration', 'dialog', 'dialogue', 'line', 'speech', 'boses', 'eleven', 'elevenlabs', 'tts']
const MUSIC_WORDS = ['music', 'bgm', 'song', 'beat', 'track', 'instrumental', 'chorus', 'intro', 'tugtog', 'kanta', 'bed', 'loop']
const BG_WORDS = ['background', 'bg', 'scene', 'location', 'room', 'rooftop', 'limo', 'city', 'backdrop', 'setting']
const CHAR_WORDS = ['character', 'char', 'casanova', 'face', 'pose', 'cat', 'catty', 'hero', 'portrait']

function ext(name: string): string {
  const i = name.lastIndexOf('.')
  return i < 0 ? '' : name.slice(i + 1).toLowerCase()
}

function words(name: string): string[] {
  const base = name.replace(/\.[^.]+$/, '').toLowerCase()
  return base.split(/[^a-z0-9]+/).filter(Boolean)
}

function hits(ws: string[], dict: string[]): number {
  return ws.filter((w) => dict.includes(w)).length
}

/**
 * First-pass guess from the file name and type only.
 * Phase 2 adds real audio analysis (speech vs music, music baked into voice).
 * Rule from the owner: if unsure, ASK. Voice vs music was mislabelled once already.
 */
export function guessKind(fileName: string): Guess {
  const e = ext(fileName)
  const ws = words(fileName)

  if (AUDIO.includes(e)) {
    const v = hits(ws, VOICE_WORDS)
    const m = hits(ws, MUSIC_WORDS)
    if (v > m) return { kind: 'voice', ambiguous: false, reason: 'The file name sounds like a voiceover.' }
    if (m > v) return { kind: 'music', ambiguous: false, reason: 'The file name sounds like music.' }
    return { kind: 'voice', ambiguous: true, reason: 'This is a sound file, but I can’t tell if it is your voice or music. Please tell me.' }
  }
  if (VIDEO.includes(e)) return { kind: 'video', ambiguous: false, reason: 'This is a video file.' }
  if (IMAGE.includes(e)) {
    const c = hits(ws, CHAR_WORDS)
    const b = hits(ws, BG_WORDS)
    if (b > c) return { kind: 'background', ambiguous: false, reason: 'The file name sounds like a background.' }
    if (c > b) return { kind: 'character', ambiguous: false, reason: 'The file name sounds like a character.' }
    return { kind: 'character', ambiguous: true, reason: 'This is a picture. Is it your character or a background?' }
  }
  if (NOTES.includes(e)) return { kind: 'notes', ambiguous: false, reason: 'This looks like notes or a script.' }
  return { kind: 'unknown', ambiguous: true, reason: 'I don’t know this file type. What is it?' }
}

/** Which labels the user may switch a card to, given the file type. */
export function allowedKinds(fileName: string): AssetKind[] {
  const e = ext(fileName)
  if (AUDIO.includes(e)) return ['voice', 'music']
  if (IMAGE.includes(e)) return ['character', 'background']
  if (VIDEO.includes(e)) return ['video']
  if (NOTES.includes(e)) return ['notes']
  return ['unknown']
}
