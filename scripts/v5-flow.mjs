// Drives the app like the owner: drop files → Check timing (downloads the voice separator the first time)
// → confirm the punch line → Make my video → preflight report.
import { _electron as electron } from 'playwright'
import { mkdtempSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { createRequire } from 'node:module'

const shots = resolve(process.argv[2] ?? 'docs/screenshots')
const files = process.argv.slice(3)
const home = mkdtempSync(join(tmpdir(), 'catty-home-'))
// This cloud machine can't download from GitHub inside Electron (proxy certificate), so put the model in place.
import { mkdirSync, copyFileSync, writeFileSync } from 'node:fs'
for (const d of [join(home, 'ud', 'models'), join(home, '.config', 'Cattyfied', 'models')]) {
  mkdirSync(d, { recursive: true })
  copyFileSync('/tmp/models/UVR-MDX-NET-Voc_FT.onnx', join(d, 'UVR-MDX-NET-Voc_FT.onnx'))
  writeFileSync(join(d, 'UVR-MDX-NET-Voc_FT.onnx.verified'), 'local')
}
const app = await electron.launch({
  executablePath: createRequire(import.meta.url)(resolve('node_modules/electron')),
  args: ['--no-sandbox', `--user-data-dir=${join(home, 'ud')}`, resolve('.')],
  env: { ...process.env, HOME: home }
})
app.process().stdout.on('data', (d) => process.stdout.write('[main] ' + d))
app.process().stderr.on('data', (d) => { const t = d.toString(); if (/rror|xception|rash|abort|SIG|fatal/i.test(t) && !/ssl_client|gpu|GPU|dbus|viz/.test(t)) process.stdout.write('[main-err] ' + t) })
app.on('close', () => console.log('[app closed]'))
const win = await app.firstWindow()
win.on('pageerror', (e) => console.log('PAGEERROR', e.message))
await win.setViewportSize({ width: 1400, height: 1000 })
await win.waitForSelector('.version')
console.log('version:', await win.textContent('.version'))
await win.click('text=Let’s start'); await win.click('text=Skip for now'); await win.click('text=Next →'); await win.click('text=Open Cattyfied')
await app.evaluate(async ({ dialog }, p) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: p }) }, files)
await win.click('text=click to choose files')
await win.waitForSelector('.card')
console.log('cards:', await win.$$eval('.card', (els) => els.map((e) => e.querySelector('.card-name')?.textContent + ' → ' + [...e.querySelectorAll('.chip.on')].map((c) => c.textContent).join('/'))))
const steps = new Set()
const poll = setInterval(async () => { try { const t = await win.evaluate(() => document.querySelector('.progress-label')?.textContent); if (t && !steps.has(t)) { steps.add(t); console.log('  step:', t) } } catch {} }, 500)
const t0 = Date.now()
await win.click('text=Check timing')
await win.waitForSelector('.timing, .banner.error', { timeout: 600000 })
const err = await win.$('.banner.error')
if (err) { console.log('ERROR BANNER:', await err.textContent()); process.exit(1) }
console.log('check timing took', ((Date.now() - t0) / 1000).toFixed(0), 's')
await win.waitForTimeout(800)
await win.screenshot({ path: join(shots, 'p5-1-punchline.png') })
console.log('parts:', await win.$$eval('.phrase-pick', (els) => els.map((e) => e.textContent)))
console.log('facts:\n  ' + (await win.$$eval('.timing .facts li', (els) => els.map((e) => e.textContent))).join('\n  '))
await win.click('button:has-text("is the punch line")')
const t1 = Date.now()
await win.click('text=Make my video')
await win.waitForSelector('.result', { timeout: 1800000 })
clearInterval(poll)
console.log('make video took', ((Date.now() - t1) / 1000).toFixed(0), 's')
await win.waitForTimeout(1500)
await win.screenshot({ path: join(shots, 'p5-2-result.png') })
console.log('title:', await win.textContent('.result-side h2'))
console.log('preflight:\n  ' + (await win.$$eval('.result .facts li', (els) => els.map((e) => e.textContent))).join('\n  '))
console.log('home:', home)
await app.close()
