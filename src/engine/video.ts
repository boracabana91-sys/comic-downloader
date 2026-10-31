// Picture side of the draft: frames the character/background or clip for the chosen format,
// adds a punch-line zoom + shake + quick flash exactly on the punch line, and encodes.
import { runTool } from './ffmpeg'
import type { FormatPreset } from './formats'
import { parseVideoStreams, pickThumbnailStream } from './thumbnail'
import { rotationFor } from './heic'

export const FPS = 30

export type Visual =
  | { type: 'picture'; path: string }
  | { type: 'clip'; path: string }
  | { type: 'drawn' }
  | { type: 'none' }

async function imageStreamMap(ffmpeg: string, path: string): Promise<string> {
  let info = ''
  try {
    await runTool(ffmpeg, ['-i', path])
  } catch (e) {
    info = String((e as Error).message)
  }
  const streams = parseVideoStreams(info)
  return streams.length > 1 ? `0:v:${pickThumbnailStream(streams)}` : '0:v:0'
}

/**
 * A still of the framed picture at 2× size (sharper zooms). Whole picture visible, the empty space
 * filled with a blurred copy of itself (brief: blurred-fill option). Also used as the preview still.
 */
export async function makeCanvas(ffmpeg: string, picture: string, fmt: FormatPreset, out: string): Promise<void> {
  const W = fmt.width * 2
  const H = fmt.height * 2
  const map = await imageStreamMap(ffmpeg, picture)
  const rot = await rotationFor(picture)
  const fc =
    `[${map}]${rot ? rot + ',' : ''}format=rgba,split[a][b];` +
    `[a]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},boxblur=40:4,eq=brightness=-0.06[bg];` +
    `[b]scale=${W}:${H}:force_original_aspect_ratio=decrease[fg];` +
    `[bg][fg]overlay=(W-w)/2:(H-h)/2,format=rgb24`
  await runTool(ffmpeg, ['-y', '-v', 'error', '-i', picture, '-filter_complex', fc, '-frames:v', '1', '-update', '1', out])
}

/** zoompan expressions: slow push-in over the whole video, a punch zoom + decaying shake at the punch line. */
export function motionExpressions(totalFrames: number, punchFrame: number) {
  const P = punchFrame
  const N = Math.max(1, totalFrames)
  const z = `1+0.06*on/${N}+if(gte(on,${P}),0.05+0.09*exp(-(on-${P})/7),0)`
  const sx = `if(gte(on,${P}),18*exp(-(on-${P})/6)*sin((on-${P})*2.3),0)`
  const sy = `if(gte(on,${P}),14*exp(-(on-${P})/6)*cos((on-${P})*1.9),0)`
  return {
    z,
    x: `iw/2-(iw/zoom/2)+${sx}`,
    y: `ih/2-(ih/zoom/2)+${sy}`
  }
}

/** Three-frame white flash on the punch line (brief: 3-frame white flash on cuts). */
function flash(punchFrame: number): string {
  const P = punchFrame
  return `eq=brightness=0.45:enable='eq(n,${P})',eq=brightness=0.25:enable='eq(n,${P + 1})',eq=brightness=0.1:enable='eq(n,${P + 2})'`
}

export async function renderVideo(opts: {
  ffmpeg: string
  visual: Visual
  canvas?: string
  fmt: FormatPreset
  audioWav: string
  durationSec: number
  punchSec: number
  outPartial: string
  onProgress?: (fraction: number) => void
}): Promise<void> {
  const { ffmpeg, fmt } = opts
  const W = fmt.width
  const H = fmt.height
  const total = Math.ceil(opts.durationSec * FPS)
  const P = Math.round(opts.punchSec * FPS)
  const m = motionExpressions(total, P)
  const zoom = `zoompan=z='${m.z}':x='${m.x}':y='${m.y}':d=1:s=${W}x${H}:fps=${FPS}`

  const args: string[] = ['-y', '-v', 'error', '-stats']
  let fc: string
  if (opts.visual.type === 'picture' && opts.canvas) {
    args.push('-loop', '1', '-framerate', String(FPS), '-t', opts.durationSec.toFixed(3), '-i', opts.canvas)
    fc = `[0:v]${zoom},${flash(P)},format=yuv420p[v]`
  } else if (opts.visual.type === 'clip') {
    args.push('-stream_loop', '-1', '-t', opts.durationSec.toFixed(3), '-i', opts.visual.path)
    fc =
      `[0:v]fps=${FPS},split[a][b];` +
      `[a]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},boxblur=30:3,eq=brightness=-0.06[bg];` +
      `[b]scale=${W}:${H}:force_original_aspect_ratio=decrease[fg];` +
      `[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,${zoom},${flash(P)},format=yuv420p[v]`
  } else {
    args.push('-f', 'lavfi', '-t', opts.durationSec.toFixed(3), '-i', `color=c=0x2b2230:s=${W}x${H}:r=${FPS}`)
    fc = `[0:v]${flash(P)},format=yuv420p[v]`
  }
  args.push('-i', opts.audioWav)
  args.push(
    '-filter_complex', fc,
    '-map', '[v]', '-map', '1:a',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', String(FPS),
    '-c:a', 'aac', '-b:a', '192k',
    '-t', opts.durationSec.toFixed(3),
    '-movflags', '+faststart',
    '-f', 'mp4', opts.outPartial
  )
  await runToolWithProgress(ffmpeg, args, opts.durationSec, opts.onProgress)
}

async function runToolWithProgress(bin: string, args: string[], durationSec: number, onProgress?: (f: number) => void) {
  const { spawn } = await import('node:child_process')
  await new Promise<void>((resolve, reject) => {
    const p = spawn(bin, args, { stdio: ['ignore', 'ignore', 'pipe'] })
    let err = ''
    p.stderr.on('data', (d: Buffer) => {
      const s = d.toString()
      err = (err + s).slice(-20000)
      const m = s.match(/time=(\d+):(\d+):([\d.]+)/)
      if (m && onProgress) onProgress(Math.min(1, (Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3])) / durationSec))
    })
    p.on('error', reject)
    p.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`Video render failed: ${err.slice(-1500)}`))))
  })
}

/** Grab single frames (for the "show me a picture first" step and the QA check). */
export async function grabFrame(ffmpeg: string, video: string, atSec: number, out: string, width = 360): Promise<void> {
  await runTool(ffmpeg, ['-y', '-v', 'error', '-ss', atSec.toFixed(3), '-i', video, '-frames:v', '1', '-update', '1', '-vf', `scale=${width}:-2`, out])
}
