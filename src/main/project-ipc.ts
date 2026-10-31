// Connects the engine's "Check timing" and "Make my video" to the window.
import { app, ipcMain, protocol, net, shell, type WebContents } from 'electron'
import { join, basename, extname, resolve, sep } from 'node:path'
import { promises as fs, existsSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { buildAudio, renderDraft, type AudioPlan } from '../engine/project'
import { FORMATS, type FormatId } from '../engine/formats'
import { projectsFolder, safeName } from '../engine/paths'
import type { MusicRole, AssetKind } from '../engine/classify'
import type { Visual } from '../engine/video'

export interface CardIn {
  path: string
  kind: AssetKind
  musicRole: MusicRole | null
}

export interface CheckRequest {
  cards: CardIn[]
  format: FormatId
  pauseSec: number
  punchIndex: number | null
  hitIndex: number
  channelName: string
}

interface Current {
  dir: string
  copies: Map<string, string>
  plan: AudioPlan | null
  req: CheckRequest | null
}

let current: Current | null = null

const MEDIA_SCHEME = 'catty-media'

/** Must run before app ready. */
export function registerMediaScheme(): void {
  protocol.registerSchemesAsPrivileged([{ scheme: MEDIA_SCHEME, privileges: { standard: true, secure: true, stream: true, supportFetchAPI: true } }])
}

function allowedRoots(): string[] {
  return [projectsFolder(app.getPath('documents')), join(app.getPath('temp'), 'cattyfied-thumbs')].map((p) => resolve(p) + sep)
}

/** Serves files from the projects folder only, so the window can play previews safely. */
export function handleMediaScheme(): void {
  protocol.handle(MEDIA_SCHEME, (req) => {
    const p = resolve(decodeURIComponent(new URL(req.url).pathname))
    if (!allowedRoots().some((r) => p.startsWith(r))) return new Response('Not allowed', { status: 403 })
    return net.fetch(pathToFileURL(p).toString(), { headers: req.headers })
  })
}

export const mediaUrl = (p: string) => `${MEDIA_SCHEME}://local${encodeURI(resolve(p))}?v=${Date.now()}`

function stamp(d = new Date()): string {
  const z = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}.${z(d.getMinutes())}`
}

async function ensureProject(channelName: string): Promise<Current> {
  if (current) return current
  const dir = join(projectsFolder(app.getPath('documents')), safeName(`${stamp()} ${channelName}`))
  await fs.mkdir(join(dir, 'originals'), { recursive: true })
  await fs.mkdir(join(dir, 'work'), { recursive: true })
  current = { dir, copies: new Map(), plan: null, req: null }
  return current
}

/** Owner rule: never touch the originals. Work on copies inside the project. */
async function copyIn(cur: Current, original: string): Promise<string> {
  const have = cur.copies.get(original)
  if (have && existsSync(have)) return have
  let name = basename(original)
  let target = join(cur.dir, 'originals', name)
  let n = 2
  while (existsSync(target)) {
    name = `${basename(original, extname(original))} (${n++})${extname(original)}`
    target = join(cur.dir, 'originals', name)
  }
  await fs.copyFile(original, target)
  cur.copies.set(original, target)
  return target
}

function pickVisual(cards: CardIn[], copies: Map<string, string>): Visual {
  const clip = cards.find((c) => c.kind === 'video')
  if (clip) return { type: 'clip', path: copies.get(clip.path)! }
  const pic = cards.find((c) => c.kind === 'character') ?? cards.find((c) => c.kind === 'background')
  if (pic) return { type: 'picture', path: copies.get(pic.path)! }
  return { type: 'none' }
}

function friendly(err: unknown): string {
  const m = String((err as Error)?.message ?? err)
  if (/No such file|ENOENT/.test(m)) return 'One of your files was moved or deleted. Please drop it again.'
  if (/Invalid data|could not find codec|moov atom/i.test(m)) return 'One of the files can’t be read. It may be damaged or in an unusual format.'
  if (/ENOSPC|No space/i.test(m)) return 'Your Mac is out of disk space. Free some space and try again.'
  if (m.length < 160 && !/ffmpeg/i.test(m)) return m
  return 'Something went wrong while working on your files. Use “Copy details” and send them to Claude.'
}

export function registerProjectIpc(getFfmpeg: () => string): void {
  ipcMain.handle('project:new', () => {
    current = null
    return true
  })

  ipcMain.handle('project:check', async (e, req: CheckRequest) => {
    const send = (wc: WebContents, step: string, fraction: number | null = null) => wc.send('job:progress', { step, fraction })
    try {
      const voice = req.cards.filter((c) => c.kind === 'voice')
      if (voice.length === 0) return { ok: false, message: 'Please drop your voiceover (or mark one sound file as “Voice”).' }
      if (voice.length > 1) return { ok: false, message: 'There are two voice files. Please mark just one as “Voice”.' }
      const cur = await ensureProject(req.channelName)
      send(e.sender, 'Copying your files into the project (your originals stay untouched)…')
      for (const c of req.cards) if (c.kind !== 'notes' && c.kind !== 'unknown') await copyIn(cur, c.path)
      const music = req.cards
        .filter((c) => c.kind === 'music')
        .map((c) => ({ path: cur.copies.get(c.path)!, role: (c.musicRole ?? 'main') as MusicRole }))

      const plan = await buildAudio(
        {
          ffmpeg: getFfmpeg(),
          workDir: join(cur.dir, 'work'),
          voice: cur.copies.get(voice[0].path)!,
          music,
          pauseSec: req.pauseSec,
          punchIndex: req.punchIndex,
          hitIndex: req.hitIndex
        },
        (s) => send(e.sender, s)
      )
      cur.plan = plan
      cur.req = req

      // Picture first (owner rule 4): a still of how the video will be framed.
      let still: string | null = null
      const visual = pickVisual(req.cards, cur.copies)
      const fmt = FORMATS[req.format]
      send(e.sender, 'Making a preview picture…')
      try {
        const { makeCanvas, grabFrame } = await import('../engine/video')
        const out = join(cur.dir, 'work', `still-${fmt.id}.jpg`)
        if (visual.type === 'picture') {
          const png = join(cur.dir, 'work', `canvas-${fmt.id}.png`)
          await makeCanvas(getFfmpeg(), visual.path, fmt, png)
          const { runTool } = await import('../engine/ffmpeg')
          await runTool(getFfmpeg(), ['-y', '-v', 'error', '-i', png, '-vf', 'scale=360:-2', '-frames:v', '1', '-update', '1', out])
          still = out
        } else if (visual.type === 'clip') {
          await grabFrame(getFfmpeg(), visual.path, 0.5, out)
          still = out
        }
      } catch {
        still = null
      }

      return {
        ok: true,
        projectDir: cur.dir,
        plan: {
          ...plan,
          mixUrl: mediaUrl(plan.mixWav),
          phrases: plan.phrases.map((p) => ({ ...p, url: mediaUrl(p.clip) }))
        },
        visual: visual.type,
        stillUrl: still ? mediaUrl(still) : null
      }
    } catch (err) {
      return { ok: false, message: friendly(err), detail: String((err as Error)?.stack ?? err) }
    }
  })

  ipcMain.handle('project:render', async (e) => {
    try {
      if (!current?.plan || !current.req) return { ok: false, message: 'Please click “Check timing” first.' }
      const cur = current
      const req = current.req
      const plan = current.plan
      const fmt = FORMATS[req.format]
      const t = new Date()
      const z = (n: number) => String(n).padStart(2, '0')
      const out = join(cur.dir, `Cattyfied ${fmt.id === 'vertical' ? 'Shorts-Reels' : 'YouTube-Facebook'} ${z(t.getHours())}.${z(t.getMinutes())}.${z(t.getSeconds())}.mp4`)
      e.sender.send('job:progress', { step: 'Making your video…', fraction: 0 })
      const result = await renderDraft({
        ffmpeg: getFfmpeg(),
        workDir: join(cur.dir, 'work'),
        outFile: out,
        plan,
        visual: pickVisual(req.cards, cur.copies),
        fmt,
        onProgress: (f) => e.sender.send('job:progress', { step: 'Making your video…', fraction: f })
      })
      e.sender.send('job:progress', { step: 'Checking the finished video…', fraction: 1 })
      await fs.writeFile(join(cur.dir, 'project.json'), JSON.stringify({ request: req, plan, output: out, qa: result.qa }, null, 2))
      return {
        ok: true,
        video: result.video,
        videoUrl: mediaUrl(result.video),
        frames: result.frames.map((f) => ({ ...f, url: mediaUrl(f.path) })),
        qa: result.qa
      }
    } catch (err) {
      return { ok: false, message: friendly(err), detail: String((err as Error)?.stack ?? err) }
    }
  })

  ipcMain.handle('project:reveal', (_e, p: string) => {
    if (current && resolve(p).startsWith(resolve(current.dir))) shell.showItemInFolder(p)
  })
}
