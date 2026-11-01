// The vocal-isolation model: downloaded once on first use (~67 MB, from the GitHub release the reference
// uses), verified with SHA-256, stored in the app's data folder. Written to a temp name, renamed when complete.
import { app, net } from 'electron'
import { createHash } from 'node:crypto'
import { createWriteStream, existsSync, promises as fs } from 'node:fs'
import { join } from 'node:path'
import { MDX_MODEL_URL, MDX_MODEL_SHA256, MDX_MODEL_BYTES, type OrtLike } from '../engine/audio/mdx'

export function modelPath(): string {
  return join(app.getPath('userData'), 'models', 'UVR-MDX-NET-Voc_FT.onnx')
}

let ortCache: OrtLike | null | undefined
/** onnxruntime is only shipped for Apple Silicon Macs; on others vocal isolation is switched off. */
export function loadOrt(): OrtLike | null {
  if (ortCache !== undefined) return ortCache
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    ortCache = require('onnxruntime-node') as OrtLike
  } catch {
    ortCache = null
  }
  return ortCache
}

let inFlight: Promise<string> | null = null

export async function ensureModel(onProgress: (fraction: number) => void): Promise<string> {
  const target = modelPath()
  const okMark = target + '.verified'
  if (existsSync(target) && existsSync(okMark)) return target
  if (inFlight) return inFlight
  inFlight = (async () => {
    await fs.mkdir(join(app.getPath('userData'), 'models'), { recursive: true })
    const partial = target + '.partial'
    const res = await net.fetch(MDX_MODEL_URL)
    if (!res.ok || !res.body) throw new Error(`download failed (${res.status})`)
    const total = Number(res.headers.get('content-length')) || MDX_MODEL_BYTES
    const hash = createHash('sha256')
    const out = createWriteStream(partial)
    let got = 0
    const reader = res.body.getReader()
    try {
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        hash.update(value)
        got += value.length
        if (!out.write(value)) await new Promise<void>((r) => out.once('drain', () => r()))
        onProgress(Math.min(1, got / total))
      }
    } finally {
      await new Promise<void>((r) => out.end(() => r()))
    }
    if (hash.digest('hex') !== MDX_MODEL_SHA256) {
      await fs.rm(partial, { force: true })
      throw new Error('the downloaded file was damaged')
    }
    await fs.rename(partial, target)
    await fs.writeFile(okMark, MDX_MODEL_SHA256)
    return target
  })()
  try {
    return await inFlight
  } finally {
    inFlight = null
  }
}

/**
 * Run vocal isolation in a helper process: Electron in plain-Node mode (onnxruntime crashes inside the
 * main process). Progress lines "P 0.25" are forwarded.
 */
export function workerIsolator(ffmpeg: string, model: string) {
  return (inWav: string, outWav: string, onProgress: (f: number) => void): Promise<void> =>
    new Promise((resolve, reject) => {
      const { spawn } = require('node:child_process') as typeof import('node:child_process')
      const script = join(__dirname, 'mdx-worker.js')
      const p = spawn(process.execPath, [script, ffmpeg, model, inWav, outWav], {
        env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
        stdio: ['ignore', 'pipe', 'pipe']
      })
      let err = ''
      let buf = ''
      p.stdout.on('data', (d: Buffer) => {
        buf += d.toString()
        let i
        while ((i = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, i); buf = buf.slice(i + 1)
          if (line.startsWith('P ')) onProgress(Number(line.slice(2)))
        }
      })
      p.stderr.on('data', (d: Buffer) => { err = (err + d.toString()).slice(-3000) })
      p.on('error', reject)
      p.on('close', (code, sig) => (code === 0 ? resolve() : reject(new Error(`voice separation failed (${code ?? sig}): ${err.slice(-500)}`))))
    })
}
