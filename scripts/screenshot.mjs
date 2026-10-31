// Dev helper: launches the built app, clicks through the wizard and the drop zone, saves screenshots.
// Usage: xvfb-run -a node scripts/screenshot.mjs <outDir>
import { _electron as electron } from 'playwright'
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'

const outDir = resolve(process.argv[2] ?? 'screenshots')
mkdirSync(outDir, { recursive: true })
const userData = mkdtempSync(join(tmpdir(), 'catty-ud-'))
const samples = mkdtempSync(join(tmpdir(), 'catty-samples-'))
for (const n of ['punchline_voiceover.mp3', 'limo-bgm.wav', 'recording 12.m4a', 'higgsfield_take3.mp4', 'casanova_cat.png', 'IMG_2231.jpg'])
  writeFileSync(join(samples, n), 'x'.repeat(2048))

const app = await electron.launch({
  executablePath: (await import('node:module')).createRequire(import.meta.url)(resolve('node_modules/electron')),
  args: ['--no-sandbox', `--user-data-dir=${userData}`, resolve('.')],
  env: { ...process.env, HOME: userData }
})
const win = await app.firstWindow()
await win.setViewportSize({ width: 1280, height: 820 })
await win.waitForSelector('.version')
const shot = async (n) => win.screenshot({ path: join(outDir, n) })

await shot('1-welcome.png')
await win.click('text=Let’s start')
await win.fill('.big-input', 'not-a-key')
await win.click('text=Check and save my key')
await win.waitForSelector('.banner')
await shot('2-key.png')
await win.click('text=Skip for now')
await shot('3-channel.png')
await win.click('text=Next →')
await shot('4-done.png')
await win.click('text=Open Cattyfied')
await win.waitForSelector('.dropzone')
await shot('5-main-empty.png')

// Simulate a drop by calling the same code path the drop uses.
const paths = ['punchline_voiceover.mp3', 'limo-bgm.wav', 'recording 12.m4a', 'higgsfield_take3.mp4', 'casanova_cat.png', 'IMG_2231.jpg'].map((n) => join(samples, n))
await app.evaluate(async ({ dialog }, p) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: p }) }, paths)
await win.click('text=click to choose files')
await win.waitForSelector('.card')
await win.click('text=YouTube / Facebook')
await shot('6-main-cards.png')
console.log('version label:', await win.textContent('.version'))
await app.close()
