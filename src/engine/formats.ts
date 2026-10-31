// Output format presets. Each format is rendered natively (never a crop of the other one).

export type FormatId = 'vertical' | 'landscape'

export interface Rect { x: number; y: number; w: number; h: number }

export interface FormatPreset {
  id: FormatId
  label: string
  subLabel: string
  width: number
  height: number
  fps: number
  /** Area where faces/captions are safe from platform buttons and titles. */
  safeZone: Rect
  /** Target loudness in LUFS (integrated). */
  loudnessLufs: number
}

export const FORMATS: Record<FormatId, FormatPreset> = {
  vertical: {
    id: 'vertical',
    label: 'Shorts / Reels',
    subLabel: '9:16 · 1080×1920',
    width: 1080,
    height: 1920,
    fps: 30,
    // Keep clear of the top bar, the right-side buttons and the bottom caption/channel area.
    safeZone: { x: 60, y: 250, w: 840, h: 1170 },
    loudnessLufs: -14
  },
  landscape: {
    id: 'landscape',
    label: 'YouTube / Facebook',
    subLabel: '16:9 · 1920×1080',
    width: 1920,
    height: 1080,
    fps: 30,
    safeZone: { x: 96, y: 54, w: 1728, h: 900 },
    loudnessLufs: -14
  }
}

export const DEFAULT_FORMAT: FormatId = 'vertical'

export function aspect(f: FormatPreset): number {
  return f.width / f.height
}

/** True when the rectangle sits fully inside the format's safe zone. */
export function insideSafeZone(f: FormatPreset, r: Rect): boolean {
  const s = f.safeZone
  return r.x >= s.x && r.y >= s.y && r.x + r.w <= s.x + s.w && r.y + r.h <= s.y + s.h
}
