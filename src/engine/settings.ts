import type { FormatId } from './formats'
import { DEFAULT_FORMAT } from './formats'

export const SETTINGS_SCHEMA_VERSION = 1

export interface ChannelProfile {
  id: string
  name: string
  template: 'casanova' | 'what-if' | 'custom'
  language: 'tl' | 'en'
  format: FormatId
}

export interface Settings {
  schemaVersion: number
  firstRunDone: boolean
  activeChannelId: string | null
  channels: ChannelProfile[]
  format: FormatId
  largeText: boolean
  punchPauseSec: number
  showOnScreenText: boolean
  checkForUpdates: boolean
}

export const DEFAULT_CHANNELS: ChannelProfile[] = [
  { id: 'casanova', name: 'Casanova', template: 'casanova', language: 'tl', format: 'vertical' },
  { id: 'anachron', name: 'Anachron (what-if)', template: 'what-if', language: 'en', format: 'vertical' }
]

export function defaultSettings(): Settings {
  return {
    schemaVersion: SETTINGS_SCHEMA_VERSION,
    firstRunDone: false,
    activeChannelId: null,
    channels: DEFAULT_CHANNELS.map((c) => ({ ...c })),
    format: DEFAULT_FORMAT,
    largeText: false,
    punchPauseSec: 2.0,
    showOnScreenText: false, // owner rule: no on-screen text unless switched on
    checkForUpdates: false // owner rule: off by default
  }
}

/**
 * Accept whatever is on disk (maybe old, maybe damaged) and return valid settings.
 * Unknown/missing fields fall back to defaults; never throws.
 */
export function migrateSettings(raw: unknown): Settings {
  const d = defaultSettings()
  if (!raw || typeof raw !== 'object') return d
  const r = raw as Partial<Settings>
  const pick = <K extends keyof Settings>(k: K, ok: (v: unknown) => boolean): Settings[K] =>
    ok(r[k]) ? (r[k] as Settings[K]) : d[k]
  const isBool = (v: unknown) => typeof v === 'boolean'
  const channels = Array.isArray(r.channels)
    ? r.channels.filter((c) => c && typeof c.id === 'string' && typeof c.name === 'string')
    : d.channels
  return {
    schemaVersion: SETTINGS_SCHEMA_VERSION,
    firstRunDone: pick('firstRunDone', isBool),
    activeChannelId: typeof r.activeChannelId === 'string' ? r.activeChannelId : null,
    channels: channels.length ? channels : d.channels,
    format: pick('format', (v) => v === 'vertical' || v === 'landscape'),
    largeText: pick('largeText', isBool),
    punchPauseSec: pick('punchPauseSec', (v) => typeof v === 'number' && v >= 0 && v <= 10),
    showOnScreenText: pick('showOnScreenText', isBool),
    checkForUpdates: pick('checkForUpdates', isBool)
  }
}

/** Anthropic keys start with "sk-ant-". Quick shape check before calling the API. */
export function looksLikeAnthropicKey(key: string): boolean {
  return /^sk-ant-[A-Za-z0-9_-]{20,}$/.test(key.trim())
}
