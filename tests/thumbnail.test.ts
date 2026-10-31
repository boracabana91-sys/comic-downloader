import { describe, it, expect } from 'vitest'
import { parseVideoStreams, pickThumbnailStream } from '@engine/thumbnail'

// Real ffmpeg output for an actual iPhone HEIC photo used while testing: a grey depth map first,
// then the real photo, then a small embedded preview.
const REAL_HEIC_STDERR = `
  Stream #0:60[0x3f]: Video: hevc (Rext) (hvc1 / 0x31637668), gray(pc), 2016x1512, 1 fps, 1 tbr, 1 tbn
  Stream #0:61[0x41]: Video: hevc (Main 10) (hvc1 / 0x31637668), yuv420p10le(pc), 1024x768, 1 fps, 1 tbr, 1 tbn
  Stream #0:62[0x42]: Video: hevc (Main Still Picture) (hvc1 / 0x31637668), yuvj420p(pc, smpte170m/smpte432/bt709), 416x312, 1 fps, 1 tbr, 1 tbn
`

describe('HEIC thumbnail stream picking', () => {
  it('finds all three streams', () => {
    expect(parseVideoStreams(REAL_HEIC_STDERR)).toHaveLength(3)
  })
  it('skips the grey depth map and picks the real, biggest photo', () => {
    const streams = parseVideoStreams(REAL_HEIC_STDERR)
    expect(streams[0].grey).toBe(true)
    expect(pickThumbnailStream(streams)).toBe(1) // the 1024x768 real photo, not the 2016x1512 grey map
  })
  it('falls back sanely for a normal single-stream picture', () => {
    const streams = parseVideoStreams('  Stream #0:0: Video: mjpeg, yuvj420p(pc), 800x600, 1 fps')
    expect(pickThumbnailStream(streams)).toBe(0)
  })
  it('never crashes on no streams found', () => {
    expect(pickThumbnailStream([])).toBe(0)
  })
})

import { heicRotationFilter } from '@engine/heic'
import { readFileSync, existsSync } from 'node:fs'

describe('iPhone photo rotation', () => {
  const box = (n: number) => Uint8Array.from([0, 0, 0, 9, 0x69, 0x72, 0x6f, 0x74, n])
  it('reads the irot box', () => {
    expect(heicRotationFilter(box(0))).toBe('')
    expect(heicRotationFilter(box(1))).toBe('transpose=2')
    expect(heicRotationFilter(box(2))).toBe('hflip,vflip')
    expect(heicRotationFilter(box(3))).toBe('transpose=1')
    expect(heicRotationFilter(Uint8Array.from([1, 2, 3]))).toBe('')
  })
  it.skipIf(!existsSync('/tmp/catty-test/IMG_4664.HEIC'))('finds the rotation in a real iPhone photo', () => {
    expect(heicRotationFilter(readFileSync('/tmp/catty-test/IMG_4664.HEIC').subarray(0, 1 << 20))).toBe('transpose=1')
  })
})
