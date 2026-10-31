import { promises as fs } from 'node:fs'

/**
 * iPhone HEIC photos store their rotation in an "irot" box that ffmpeg ignores, so photos came out
 * sideways. This reads it. Returns the ffmpeg filter that makes the picture upright, or '' if none.
 * irot angle n (0–3) means "rotate n × 90° anticlockwise" for display.
 */
export function heicRotationFilter(head: Uint8Array): string {
  const tag = [0x69, 0x72, 0x6f, 0x74] // "irot"
  for (let i = 4; i <= head.length - 5; i++) {
    if (head[i] === tag[0] && head[i + 1] === tag[1] && head[i + 2] === tag[2] && head[i + 3] === tag[3]) {
      const size = (head[i - 4] << 24) | (head[i - 3] << 16) | (head[i - 2] << 8) | head[i - 1]
      if (size !== 9) continue
      const n = head[i + 4] & 3
      return n === 1 ? 'transpose=2' : n === 2 ? 'hflip,vflip' : n === 3 ? 'transpose=1' : ''
    }
  }
  return ''
}

export async function rotationFor(path: string): Promise<string> {
  if (!/\.(heic|heif)$/i.test(path)) return ''
  const fh = await fs.open(path, 'r')
  try {
    const buf = Buffer.alloc(1 << 20)
    const { bytesRead } = await fh.read(buf, 0, buf.length, 0)
    return heicRotationFilter(buf.subarray(0, bytesRead))
  } finally {
    await fh.close()
  }
}
