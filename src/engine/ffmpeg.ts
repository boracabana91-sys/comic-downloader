import { spawn } from 'node:child_process'

export const SAMPLE_RATE = 44100

/** Run ffmpeg/ffprobe and collect output. Rejects with stderr on failure. */
export function runTool(bin: string, args: string[], opts: { stdoutBinary?: boolean } = {}): Promise<{ stdout: Buffer; stderr: string }> {
  return new Promise((resolve, reject) => {
    const p = spawn(bin, args, { stdio: ['ignore', 'pipe', 'pipe'] })
    const out: Buffer[] = []
    let err = ''
    p.stdout.on('data', (d: Buffer) => out.push(d))
    p.stderr.on('data', (d: Buffer) => {
      err += d.toString()
      if (err.length > 200_000) err = err.slice(-100_000)
    })
    p.on('error', reject)
    p.on('close', (code) => {
      if (code === 0) resolve({ stdout: Buffer.concat(out), stderr: err })
      else reject(new Error(`ffmpeg failed (${code}): ${err.slice(-1500)}`))
    })
    void opts
  })
}

/** Stereo audio as two Float32 channels at 44.1 kHz. */
export interface Stereo {
  l: Float32Array
  r: Float32Array
}

/** Decode any audio/video file's sound to 44.1 kHz stereo float (step 1 of the brief's pipeline). */
export async function decodeAudio(ffmpeg: string, file: string, filter?: string): Promise<Stereo> {
  const args = ['-v', 'error', '-i', file, '-vn']
  if (filter) args.push('-af', filter)
  args.push('-ac', '2', '-ar', String(SAMPLE_RATE), '-f', 'f32le', 'pipe:1')
  const { stdout } = await runTool(ffmpeg, args)
  const all = new Float32Array(stdout.buffer, stdout.byteOffset, Math.floor(stdout.length / 4))
  const n = Math.floor(all.length / 2)
  const l = new Float32Array(n)
  const r = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    l[i] = all[2 * i]
    r[i] = all[2 * i + 1]
  }
  return { l, r }
}

export function toMono(s: Stereo): Float32Array {
  const m = new Float32Array(s.l.length)
  for (let i = 0; i < m.length; i++) m[i] = 0.5 * (s.l[i] + s.r[i])
  return m
}

/** 16-bit PCM WAV bytes (what we hand to ffmpeg and to the preview player). */
export function encodeWav(s: Stereo): Buffer {
  const n = s.l.length
  const buf = Buffer.alloc(44 + n * 4)
  buf.write('RIFF', 0)
  buf.writeUInt32LE(36 + n * 4, 4)
  buf.write('WAVE', 8)
  buf.write('fmt ', 12)
  buf.writeUInt32LE(16, 16)
  buf.writeUInt16LE(1, 20)
  buf.writeUInt16LE(2, 22)
  buf.writeUInt32LE(SAMPLE_RATE, 24)
  buf.writeUInt32LE(SAMPLE_RATE * 4, 28)
  buf.writeUInt16LE(4, 32)
  buf.writeUInt16LE(16, 34)
  buf.write('data', 36)
  buf.writeUInt32LE(n * 4, 40)
  let o = 44
  for (let i = 0; i < n; i++) {
    buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, s.l[i])) * 32767), o)
    buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, s.r[i])) * 32767), o + 2)
    o += 4
  }
  return buf
}

/**
 * Decode to 44.1 kHz MONO (the reference cleans the voice with -ac 1 into a 16-bit file).
 * Uses 16-bit output on purpose: ffmpeg scales the stereo→mono downmix differently for float output
 * (it came out exactly 2× louder), and every level in the audio brain is tuned to the 16-bit path.
 */
export async function decodeMono(ffmpeg: string, file: string, filter?: string): Promise<Float32Array> {
  const args = ['-v', 'error', '-i', file, '-vn']
  if (filter) args.push('-af', filter)
  args.push('-ac', '1', '-ar', String(SAMPLE_RATE), '-f', 's16le', 'pipe:1')
  const { stdout } = await runTool(ffmpeg, args)
  const n = Math.floor(stdout.length / 2)
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) out[i] = stdout.readInt16LE(i * 2) / 32768
  return out
}
