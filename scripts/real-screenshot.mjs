import { _electron as electron } from 'playwright'
import { mkdtempSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { createRequire } from 'node:module'

const userData = mkdtempSync(join(tmpdir(), 'catty-ud-'))
const app = await electron.launch({
  executablePath: createRequire(import.meta.url)(resolve('node_modules/electron')),
  args: ['--no-sandbox', `--user-data-dir=${userData}`, resolve('.')],
  env: { ...process.env, HOME: userData }
})
const win = await app.firstWindow()
await win.setViewportSize({ width: 1280, height: 820 })
await win.waitForSelector('.version')
await win.click('text=Let’s start')
await win.click('text=Skip for now')
await win.click('text=Next →')
await win.click('text=Open Cattyfied')
await win.waitForSelector('.dropzone')

const paths = ['Sol_Street_69.m4a','money_mode_wil_intro.mp3','money_mode_wil_chorus_1.mp3','casanova_v11.mp4','IMG_4664.HEIC'].map(n => join('/tmp/catty-test', n))
await app.evaluate(async ({ dialog }, p) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: p }) }, paths)
await win.click('text=click to choose files')
await win.waitForSelector('.card')
await win.waitForTimeout(2500)
await win.screenshot({ path: '/home/user/cattyfied/docs/screenshots/real-files-test.png' })
const info = await win.$$eval('.card', els => els.map(e => ({
  name: e.querySelector('.card-name')?.getAttribute('title'),
  reason: e.querySelector('.card-reason')?.textContent,
  kind: e.querySelector('.card-kind')?.textContent || e.querySelector('.chip.on')?.textContent
})))
console.log(JSON.stringify(info, null, 2))
await app.close()
