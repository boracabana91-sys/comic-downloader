// Drives the built app like a user: drop real files, answer questions, check timing, make the video.
import { _electron as electron } from 'playwright'
import { mkdtempSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { createRequire } from 'node:module'

const shots = resolve(process.argv[2] ?? 'docs/screenshots')
const home = mkdtempSync(join(tmpdir(), 'catty-home-'))
const app = await electron.launch({
  executablePath: createRequire(import.meta.url)(resolve('node_modules/electron')),
  args: ['--no-sandbox', `--user-data-dir=${join(home, 'ud')}`, resolve('.')],
  env: { ...process.env, HOME: home }
})
const win = await app.firstWindow()
await win.setViewportSize({ width: 1400, height: 900 })
await win.waitForSelector('.version')
await win.click('text=Let’s start'); await win.click('text=Skip for now'); await win.click('text=Next →'); await win.click('text=Open Cattyfied')
const files = ['Sol_Street_69.m4a', 'money_mode_wil_intro.mp3', 'money_mode_wil_chorus_1.mp3', 'casanova_v11.mp4'].map((n) => join('/tmp/catty-test', n))
await app.evaluate(async ({ dialog }, p) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: p }) }, files)
await win.click('text=click to choose files')
await win.waitForSelector('.card')
// Answer the yellow card: the .m4a is the voice.
await win.locator('.card', { hasText: 'Sol_Street_69' }).locator('button.chip', { hasText: 'Voice' }).click()
await win.click('text=Check timing')
await win.waitForSelector('.timing', { timeout: 120000 })
await win.waitForTimeout(800)
await win.screenshot({ path: join(shots, 'p2-1-check-timing.png') })
console.log('facts:', (await win.$$eval('.timing .facts li', (els) => els.map((e) => e.textContent))).join('\n  '))
await win.click('button:has-text("is the punch line")')
await win.click('text=Make my video')
await win.waitForSelector('.result', { timeout: 300000 })
await win.waitForTimeout(1500)
await win.screenshot({ path: join(shots, 'p2-2-result.png') })
console.log('qa:', (await win.$$eval('.result .facts li', (els) => els.map((e) => e.textContent))).join('\n  '))
console.log('home:', home)
await app.close()
