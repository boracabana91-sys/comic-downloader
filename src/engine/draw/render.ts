// Draws every frame (30 fps, 2× supersample, 3 temporal subsamples for motion blur) and streams
// them into ffmpeg together with the finished mix.
import { createCanvas, type Canvas, type SKRSContext2D } from '@napi-rs/canvas'
import { spawn } from 'node:child_process'
import { drawLimo, drawCat, drawBucket } from './cat'
import { makeDirector, cutEffects, type FrameState } from './director'
import { mouthTrack } from './lipsync'
import type { Stereo } from '../ffmpeg'
import type { FormatPreset } from '../formats'

export const FPS = 30
const SS = 2
const SUBSAMPLES = 3
const SHUTTER = 1 / 3 // of a frame

export interface DrawRenderInput {
  ffmpeg: string
  fmt: FormatPreset
  durationSec: number
  punchSec: number
  phrases: { start: number; end: number }[]
  voiceTrack: Stereo
  audioWav: string
  outPartial: string
  onProgress?: (f: number) => void
  /** Only render these frames (for previews/tests). */
  onlyFrames?: number[]
  onFrame?: (index: number, canvas: Canvas) => Promise<void> | void
}

/** Design space → screen: base scale fits the 720×1280 set to the output (fills height for 16:9). */
function applyCamera(ctx: SKRSContext2D, W: number, H: number, st: FrameState) {
  const base = Math.max(W / 720, H / 1280) * (W > H ? 1 : 1)
  const fit = W > H ? H / 1280 : base
  const s = fit * st.cam.zoom
  // Keep the camera from showing beyond the set at the top/bottom.
  const halfH = H / 2 / s
  const fy = Math.min(Math.max(st.cam.fy, -150 + halfH), 1430 - halfH)
  ctx.translate(W / 2 + st.shake.x * (W / 1080), H / 2 + st.shake.y * (W / 1080))
  ctx.rotate(((st.cam.roll + st.shake.rot) * Math.PI) / 180)
  ctx.scale(s, s)
  ctx.translate(-st.cam.fx, -fy)
}

export async function renderDrawn(inp: DrawRenderInput): Promise<void> {
  const W = inp.fmt.width
  const H = inp.fmt.height
  const total = Math.ceil(inp.durationSec * FPS)
  const dir = makeDirector({ durationSec: inp.durationSec, punchSec: inp.punchSec, phrases: inp.phrases })
  const mouths = mouthTrack(inp.voiceTrack, FPS, total + 1)
  const cutFrames = dir.cuts.map((c) => Math.round(c * FPS))

  // The set never changes: draw it once at high resolution, then just place it each frame.
  const setScale = 3
  const setW = 2720, setH = 1900, setX = -1000, setY = -300
  const set = createCanvas(setW * setScale / 2, setH * setScale / 2)
  {
    const c = set.getContext('2d')
    c.scale(setScale / 2, setScale / 2)
    c.translate(-setX, -setY)
    drawLimo(c)
  }

  const big = createCanvas(W * SS, H * SS)
  const bctx = big.getContext('2d')
  const acc = createCanvas(W, H)
  const actx = acc.getContext('2d')
  const fx = createCanvas(W, H)
  const fctx = fx.getContext('2d')

  const drawScene = (st: FrameState) => {
    bctx.setTransform(1, 0, 0, 1, 0, 0)
    bctx.fillStyle = '#140f1e'
    bctx.fillRect(0, 0, W * SS, H * SS)
    applyCamera(bctx, W * SS, H * SS, st)
    bctx.imageSmoothingEnabled = true
    bctx.drawImage(set, setX, setY, setW, setH)
    drawCat(bctx, st.pose)
    drawBucket(bctx)
  }

  let ff: ReturnType<typeof spawn> | null = null
  let ffErr = ''
  let ffDone: Promise<void> | null = null
  if (!inp.onFrame) {
    ff = spawn(inp.ffmpeg, [
      '-y', '-v', 'error',
      '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${W}x${H}`, '-r', String(FPS), '-i', 'pipe:0',
      '-i', inp.audioWav,
      '-map', '0:v', '-map', '1:a',
      '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
      '-c:a', 'aac', '-b:a', '192k', '-t', inp.durationSec.toFixed(3), '-movflags', '+faststart',
      '-f', 'mp4', inp.outPartial
    ], { stdio: ['pipe', 'ignore', 'pipe'] })
    ff.stderr!.on('data', (d: Buffer) => { ffErr = (ffErr + d.toString()).slice(-4000) })
    ffDone = new Promise((res, rej) => {
      ff!.on('error', rej)
      ff!.on('close', (code) => (code === 0 ? res() : rej(new Error(`Video encoding failed: ${ffErr}`))))
    })
  }

  const frames = inp.onlyFrames ?? Array.from({ length: total }, (_, i) => i)
  for (const f of frames) {
    const t0 = f / FPS
    const take = dir.takeAt(t0)
    actx.setTransform(1, 0, 0, 1, 0, 0)
    for (let s = 0; s < SUBSAMPLES; s++) {
      let t = t0 + ((s - (SUBSAMPLES - 1) / 2) / (SUBSAMPLES - 1)) * (SHUTTER / FPS)
      if (dir.takeAt(t) !== take) t = t0 // never blur across a hard cut
      const st = dir.state(t, mouths[Math.min(mouths.length - 1, Math.max(0, Math.round(t * FPS)))])
      drawScene(st)
      actx.globalAlpha = 1 / (s + 1) // running average of the subframes = motion blur
      actx.imageSmoothingEnabled = true
      actx.drawImage(big, 0, 0, W, H)
    }
    actx.globalAlpha = 1

    const fxs = cutEffects(f, cutFrames)
    let out: Canvas = acc
    if (fxs.blur > 0) {
      fctx.setTransform(1, 0, 0, 1, 0, 0)
      fctx.filter = `blur(${(fxs.blur * W) / 1080}px)`
      fctx.drawImage(acc, 0, 0)
      fctx.filter = 'none'
      out = fx
    }
    if (fxs.flash > 0) {
      const c = out.getContext('2d')
      c.globalAlpha = fxs.flash
      c.fillStyle = '#ffffff'
      c.fillRect(0, 0, W, H)
      c.globalAlpha = 1
    }

    if (inp.onFrame) await inp.onFrame(f, out)
    else {
      const px = out.getContext('2d').getImageData(0, 0, W, H).data
      const buf = Buffer.from(px.buffer, px.byteOffset, px.byteLength)
      if (!ff!.stdin!.write(buf)) await new Promise<void>((r) => ff!.stdin!.once('drain', () => r()))
    }
    inp.onProgress?.((frames.indexOf(f) + 1) / frames.length)
    // Let the app breathe between frames so the window never freezes.
    await new Promise<void>((r) => setImmediate(r))
  }
  if (ff) {
    ff.stdin!.end()
    await ffDone
  }
}
