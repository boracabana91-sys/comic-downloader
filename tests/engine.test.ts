import { describe, it, expect } from 'vitest'
import { mkdtempSync, readFileSync, readdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { guessKind, allowedKinds } from '@engine/classify'
import { FORMATS, aspect, insideSafeZone } from '@engine/formats'
import { defaultSettings, migrateSettings, looksLikeAnthropicKey } from '@engine/settings'
import { safeName, appFolder } from '@engine/paths'
import { versionLabel } from '@engine/version'
import { writeFileAtomic } from '@engine/atomic'
import pkg from '../package.json'

describe('file labelling', () => {
  it('labels clear voice and music file names', () => {
    expect(guessKind('punchline_voiceover.mp3')).toMatchObject({ kind: 'voice', ambiguous: false })
    expect(guessKind('limo-bgm-chorus.wav')).toMatchObject({ kind: 'music', ambiguous: false })
  })
  it('asks when a sound file could be voice or music', () => {
    expect(guessKind('recording 12.m4a').ambiguous).toBe(true)
  })
  it('labels video, pictures and notes', () => {
    expect(guessKind('higgsfield_take3.MP4').kind).toBe('video')
    expect(guessKind('rooftop-background.png').kind).toBe('background')
    expect(guessKind('casanova_cat_pose.png').kind).toBe('character')
    expect(guessKind('IMG_2231.jpg').ambiguous).toBe(true)
    expect(guessKind('script.txt').kind).toBe('notes')
  })
  it('only offers sensible relabels', () => {
    expect(allowedKinds('a.wav')).toEqual(['voice', 'music'])
    expect(allowedKinds('a.png')).toEqual(['character', 'background'])
  })
})

describe('formats', () => {
  it('has native 9:16 and 16:9 sizes', () => {
    expect([FORMATS.vertical.width, FORMATS.vertical.height]).toEqual([1080, 1920])
    expect([FORMATS.landscape.width, FORMATS.landscape.height]).toEqual([1920, 1080])
    expect(aspect(FORMATS.vertical)).toBeCloseTo(9 / 16)
    expect(aspect(FORMATS.landscape)).toBeCloseTo(16 / 9)
  })
  it('safe zones fit inside the frame', () => {
    for (const f of Object.values(FORMATS)) {
      const s = f.safeZone
      expect(s.x + s.w).toBeLessThanOrEqual(f.width)
      expect(s.y + s.h).toBeLessThanOrEqual(f.height)
      expect(insideSafeZone(f, s)).toBe(true)
      expect(insideSafeZone(f, { x: 0, y: 0, w: f.width, h: f.height })).toBe(false)
    }
  })
})

describe('settings', () => {
  it('defaults follow the owner rules', () => {
    const d = defaultSettings()
    expect(d.punchPauseSec).toBe(2.0)
    expect(d.showOnScreenText).toBe(false)
    expect(d.checkForUpdates).toBe(false)
    expect(d.format).toBe('vertical')
  })
  it('survives damaged or old settings files', () => {
    expect(migrateSettings(null)).toEqual(defaultSettings())
    expect(migrateSettings('garbage')).toEqual(defaultSettings())
    const m = migrateSettings({ format: 'landscape', punchPauseSec: 99, largeText: 'yes' })
    expect(m.format).toBe('landscape')
    expect(m.punchPauseSec).toBe(2.0)
    expect(m.largeText).toBe(false)
  })
  it('checks the key shape', () => {
    expect(looksLikeAnthropicKey('sk-ant-api03-abcdefghijklmnopqrstuvwxyz')).toBe(true)
    expect(looksLikeAnthropicKey('hello')).toBe(false)
  })
})

describe('naming and version', () => {
  it('version label shows in the corner as "Cattyfied vX.Y"', () => {
    expect(versionLabel('Cattyfied', '0.1.0')).toBe('Cattyfied v0.1')
    expect(versionLabel('Cattyfied', '1.2.3')).toBe('Cattyfied v1.2.3')
    expect(pkg.productName).toBe('Cattyfied')
  })
  it('projects live in Documents/Cattyfied', () => {
    expect(appFolder('/Users/anne/Documents')).toBe('/Users/anne/Documents/Cattyfied')
    expect(safeName('a/b:c?')).toBe('a b c')
    expect(safeName('   ')).toBe('Untitled')
  })
})

describe('atomic writes', () => {
  it('leaves only the finished file, no .partial', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'catty-'))
    const f = join(dir, 'out.json')
    await writeFileAtomic(f, '{"ok":true}')
    expect(readFileSync(f, 'utf8')).toBe('{"ok":true}')
    expect(readdirSync(dir)).toEqual(['out.json'])
  })
})
