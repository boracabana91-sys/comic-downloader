// Builds resources/bin/{ffmpeg,ffprobe} for packaging.
// On macOS: downloads the Apple Silicon and Intel builds and joins them into one universal binary (lipo),
// so the same file works on every Mac. Runs in CI on a Mac runner.
import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync, copyFileSync, chmodSync, rmSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { gunzipSync } from 'node:zlib'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

const require = createRequire(import.meta.url)
const out = join(process.cwd(), 'resources', 'bin')
rmSync(out, { recursive: true, force: true })
mkdirSync(out, { recursive: true })

async function download(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Download failed (${res.status}): ${url}`)
  return Buffer.from(await res.arrayBuffer())
}

if (process.platform === 'darwin') {
  const meta = require('ffmpeg-static/package.json')['ffmpeg-static']
  const tag = meta['binary-release-tag']
  const tmp = join(tmpdir(), `catty-bin-${Date.now()}`)
  mkdirSync(tmp, { recursive: true })
  // Both tools come from the same ffmpeg-static release. (The ffprobe-static package's "arm64"
  // build is really Intel-only, so it can't be joined into a universal binary.)
  for (const tool of ['ffmpeg', 'ffprobe']) {
    const parts = []
    for (const arch of ['arm64', 'x64']) {
      const url = `https://github.com/eugeneware/ffmpeg-static/releases/download/${tag}/${tool}-darwin-${arch}.gz`
      console.log('Downloading', url)
      const f = join(tmp, `${tool}-${arch}`)
      writeFileSync(f, gunzipSync(await download(url)))
      chmodSync(f, 0o755)
      console.log('  ', execFileSync('lipo', ['-archs', f]).toString().trim())
      parts.push(f)
    }
    execFileSync('lipo', ['-create', ...parts, '-output', join(out, tool)])
  }
  for (const b of ['ffmpeg', 'ffprobe']) {
    chmodSync(join(out, b), 0o755)
    console.log(execFileSync('lipo', ['-info', join(out, b)]).toString().trim())
  }
} else {
  // Other platforms (Windows later): copy the host binaries.
  const exe = process.platform === 'win32' ? '.exe' : ''
  copyFileSync(require('ffmpeg-static'), join(out, `ffmpeg${exe}`))
  copyFileSync(require('ffprobe-static').path, join(out, `ffprobe${exe}`))
}
console.log('Video tools ready in', out)
