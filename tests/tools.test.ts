import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)

// Proves the bundled video tools actually run on this machine (CI runs this on a Mac too).
describe('bundled video tools', () => {
  // First start on a Mac can be slow: macOS scans new programs before running them.
  it('ffmpeg and ffprobe start', { timeout: 120_000 }, () => {
    const ffmpeg: string = require('ffmpeg-static')
    const ffprobe: string = require('ffprobe-static').path
    expect(execFileSync(ffmpeg, ['-version']).toString()).toMatch(/ffmpeg version/)
    expect(execFileSync(ffprobe, ['-version']).toString()).toMatch(/ffprobe version/)
  })
})
