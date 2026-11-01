// Renderer: reads the shot list (Director, built from timeline.json) and vo.wav (voice only).
// 30 fps, 2× supersample, 3 temporal subsamples for motion blur (never across a cut), fade-in,
// vignette, white flash and blur at cuts. Renders natively at the chosen format. Writes a per-frame
// log (mouth opening, take, flash) that the preflight checks use.
import { createCanvas, type Canvas, type SKRSContext2D } from '@napi-rs/canvas'
import { spawn } from 'node:child_process'
import { drawLimo, drawCat, drawBucket } from './cat'
import { makeDirector, FPS, type FrameState, type DirectorTimeline } from './director'
import { mouthTrack } from './lipsync'
import type { Stereo } from '../ffmpeg'
import type { FormatPreset } from '../formats'

export { FPS }
const SS = 2
const SUBSAMPLES = 3
const SHUTTER = 1 / 3 // of a frame

export interface FrameLog { f: number; talk: number; take: number; flash: number; blur: number }

export interface DrawRenderInput {
  ffmpeg: string
  fmt: FormatPreset
  timeline: DirectorTimeline
  /** vo.wav: the voice only, placed on the timeline. The mouth is driven by THIS, never by the mix. */
  voiceTrack: Stereo
  audioWav: string
  outPartial: string
  onProgress?: (f: number) => void
  onlyFrames?: number[]
  onFrame?: (index: number, canvas: Canvas) => Promise<void> | void
  log?: FrameLog[]
}

function applyCamera(ctx: SKRSContext2D, W: number, H: number, st: FrameState) {
  const fit = W > H ? H / 1280 : W / 720
  const s = fit * st.cam.zoom
  ctx.translate(W / 2, H / 2)
  ctx.rotate((st.cam.roll * Math.PI) / 180)
  ctx.scale(s, s)
  ctx.translate(-st.cam.fx, -st.cam.fy)
}

export async function renderDrawn(inp: DrawRenderInput): Promise<void> {
  const W = inp.fmt.width
  const H = inp.fmt.height
  const total = Math.round(inp.timeline.duration * FPS)
  const dir = makeDirector(inp.timeline)
  const mouths = mouthTrack(inp.voiceTrack, FPS, total + 2)
  const mouthAt = (fr: number) => {
    const i = Math.max(0, Math.min(mouths.length - 1, fr))
    const a = Math.floor(i), b = Math.min(mouths.length - 1, a + 1), u = i - a
    return { open: mouths[a].open * (1 - u) + mouths[b].open * u, wide: mouths[a].wide * (1 - u) + mouths[b].wide * u }
  }

  // The set never changes: draw it once at high resolution, then place it each frame.
  const setScale = 3
  const setW = 2720, setH = 1900, setX = -1000, setY = -300
  const set = createCanvas((setW * setScale) / 2, (setH * setScale) / 2)
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
  const fxc = createCanvas(W, H)
  const fctx = fxc.getContext('2d')
  // Vignette (reference: darken corners by up to 34 %).
  const vig = createCanvas(W, H)
  {
    const v = vig.getContext('2d')
    const g = v.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.25, W / 2, H / 2, Math.hypot(W, H) * 0.55)
    g.addColorStop(0, 'rgba(0,0,0,0)')
    g.addColorStop(1, 'rgba(0,0,0,0.34)')
    v.fillStyle = g
    v.fillRect(0, 0, W, H)
  }

  const drawScene = (st: FrameState) => {
    bctx.setTransform(1, 0, 0, 1, 0, 0)
    bctx.fillStyle = '#120818'
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
      '-c:a', 'aac', '-b:a', '192k', '-t', inp.timeline.duration.toFixed(3), '-movflags', '+faststart',
      '-f', 'mp4', inp.outPartial
    ], { stdio: ['pipe', 'ignore', 'pipe'] })
    ff.stderr!.on('data', (d: Buffer) => { ffErr = (ffErr + d.toString()).slice(-4000) })
    ffDone = new Promise((res, rej) => {
      ff!.on('error', rej)
      ff!.on('close', (code) => (code === 0 ? res() : rej(new Error(`Video encoding failed: ${ffErr}`))))
    })
  }

  const frames = inp.onlyFrames ?? Array.from({ length: total }, (_, i) => i)
  let done = 0
  for (const f of frames) {
    const take = dir.takeAt(f / FPS)
    let st0: FrameState | null = null
    actx.setTransform(1, 0, 0, 1, 0, 0)
    for (let s = 0; s < SUBSAMPLES; s++) {
      let fs = f + ((s - (SUBSAMPLES - 1) / 2) / (SUBSAMPLES - 1)) * SHUTTER
      if (dir.takeAt(fs / FPS) !== take) fs = f // never blur across a hard cut
      const m = mouthAt(fs)
      const st = dir.state(fs, m.open, m.wide)
      if (s === (SUBSAMPLES - 1) / 2) st0 = st
      drawScene(st)
      actx.globalAlpha = 1 / (s + 1) // running average of the subframes = motion blur
      actx.imageSmoothingEnabled = true
      actx.drawImage(big, 0, 0, W, H)
    }
    actx.globalAlpha = 1
    const cur = st0 ?? dir.state(f, mouthAt(f).open, mouthAt(f).wide)
    actx.drawImage(vig, 0, 0)
    if (cur.fade < 1) { actx.globalAlpha = 1 - cur.fade; actx.fillStyle = '#000'; actx.fillRect(0, 0, W, H); actx.globalAlpha = 1 }

    let out: Canvas = acc
    if (cur.blur > 0.2) {
      fctx.setTransform(1, 0, 0, 1, 0, 0)
      fctx.filter = `blur(${(cur.blur * W) / 720}px)`
      fctx.drawImage(acc, 0, 0)
      fctx.filter = 'none'
      out = fxc
    }
    if (cur.flash > 0) {
      const c = out.getContext('2d')
      c.globalAlpha = cur.flash
      c.fillStyle = '#ffffff'
      c.fillRect(0, 0, W, H)
      c.globalAlpha = 1
    }
    inp.log?.push({ f, talk: Math.round(cur.pose.open * 1000) / 1000, take: cur.takeIndex, flash: cur.flash, blur: cur.blur })

    if (inp.onFrame) await inp.onFrame(f, out)
    else {
      const px = out.getContext('2d').getImageData(0, 0, W, H).data
      const buf = Buffer.from(px.buffer, px.byteOffset, px.byteLength)
      if (!ff!.stdin!.write(buf)) await new Promise<void>((r) => ff!.stdin!.once('drain', () => r()))
    }
    inp.onProgress?.(++done / frames.length)
    await new Promise<void>((r) => setImmediate(r)) // keep the app responsive between frames
  }
  if (ff) {
    ff.stdin!.end()
    await ffDone
  }
}
