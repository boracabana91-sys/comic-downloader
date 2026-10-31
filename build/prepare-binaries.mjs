// Puts ffmpeg into resources/bin for packaging.
// On macOS: downloads the build for ONE Mac type (TARGET_ARCH=arm64 or x64), so each installer
// only carries what that Mac needs. Runs in CI on a Mac runner.
import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync, copyFileSync, chmodSync, rmSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { gunzipSync } from 'node:zlib'
import { join } from 'node:path'

const require = createRequire(import.meta.url)
const out = join(process.cwd(), 'resources', 'bin')
rmSync(out, { recursive: true, force: true })
mkdirSync(out, { recursive: true })

if (process.platform === 'darwin') {
  const arch = process.env.TARGET_ARCH
  if (arch !== 'arm64' && arch !== 'x64') throw new Error('Set TARGET_ARCH to arm64 or x64')
  const tag = require('ffmpeg-static/package.json')['ffmpeg-static']['binary-release-tag']
  const url = `https://github.com/eugeneware/ffmpeg-static/releases/download/${tag}/ffmpeg-darwin-${arch}.gz`
  console.log('Downloading', url)
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Download failed (${res.status}): ${url}`)
  const f = join(out, 'ffmpeg')
  writeFileSync(f, gunzipSync(Buffer.from(await res.arrayBuffer())))
  chmodSync(f, 0o755)
  console.log(execFileSync('lipo', ['-archs', f]).toString().trim())
} else {
  const exe = process.platform === 'win32' ? '.exe' : ''
  copyFileSync(require('ffmpeg-static'), join(out, `ffmpeg${exe}`))
}
console.log('Video tool ready in', out)
