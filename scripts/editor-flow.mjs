// Drives the timeline editor like a user: open it, drag the music, nudge, apply, go back to automatic.
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
await win.setViewportSize({ width: 1400, height: 1000 })
await win.waitForSelector('.version')
await win.click('text=Let’s start'); await win.click('text=Skip for now'); await win.click('text=Next →'); await win.click('text=Open Cattyfied')
const files = ['Sol_Street_69.m4a', 'money_mode_wil_intro.mp3', 'money_mode_wil_chorus_1.mp3'].map((n) => join('/tmp/catty-test', n))
await app.evaluate(async ({ dialog }, p) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: p }) }, files)
await win.click('text=click to choose files')
await win.waitForSelector('.card')
await win.locator('.card', { hasText: 'Sol_Street_69' }).locator('button.chip', { hasText: 'Voice' }).click()
await win.click('text=Check timing')
await win.waitForSelector('.timing', { timeout: 180000 })
const sync = async () => (await win.$$eval('.timing .facts li', (els) => els.map((e) => e.textContent).find((t) => /apart/.test(t ?? '')) ?? '')).trim()
console.log('AUTO:', await sync())

await win.click('summary:has-text("Fix the timing by hand")')
await win.waitForSelector('.tl-clip')
await win.locator('.tl-wrap').scrollIntoViewIfNeeded()
await win.waitForTimeout(300)
await win.locator('.tl-wrap').screenshot({ path: join(shots, 'p4-1-editor-auto.png') })
console.log('clips:', await win.$$eval('.tl-label', (els) => els.map((e) => e.textContent)))
console.log('detail:', (await win.textContent('.tl-detail-row')).trim())

// Drag the first music clip 40 px to the right with the mouse (snap off so it really moves).
await win.uncheck('text=Snap to the punch line')
const box = await win.locator('.tl-clip').first().boundingBox()
await win.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
await win.mouse.down()
await win.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2, { steps: 8 })
await win.mouse.up()
console.log('after drag:', (await win.textContent('.tl-detail-row')).trim())
// Then fine-tune with the nudge buttons.
await win.click('button:has-text("+1 frame")')
win.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log('PAGE', m.type(), m.text()) })
win.on('pageerror', (e) => console.log('PAGEERROR', e.message))
console.log('audio probe:', await win.evaluate(async () => {
  const out = {}
  try { const ctx = new AudioContext(); out.state = ctx.state; const t0 = ctx.currentTime; await new Promise((r) => setTimeout(r, 500)); out.advanced = ctx.currentTime - t0; await ctx.close() } catch (e) { out.ctxErr = String(e) }
  try { const url = document.querySelector('audio.mix')?.getAttribute('src'); const r = await fetch(url); out.fetch = r.status + ' ' + (await r.arrayBuffer()).byteLength } catch (e) { out.fetchErr = String(e) }
  return out
}))
// Live preview: press play and check the playhead moves.
const h1 = await win.textContent('.tl-time')
await win.click('.tl-bar .play')
await win.waitForTimeout(1500)
const h2 = await win.textContent('.tl-time')
await win.click('.tl-bar .play')
console.log('preview playhead:', h1, '→', h2)
console.log('clip lefts (move together):', await win.$$eval('.tl-clip', (els) => els.map((e) => e.style.left)))
console.log('after +1 frame:', (await win.textContent('.tl-detail-row')).trim())
await win.locator('.tl-wrap').screenshot({ path: join(shots, 'p4-2-editor-moved.png') })
await win.click('button:has-text("Use this timing")')
await win.waitForTimeout(500)
await win.waitForFunction(() => !document.querySelector('.progress'), null, { timeout: 180000 })
console.log('MANUAL:', await sync())
console.log('notes:', (await win.$$eval('.timing .facts li', (els) => els.map((e) => e.textContent))).filter((t) => /hand/.test(t ?? '')))

// The "put the hit on the punch line" button, then use it.
await win.evaluate(() => { const d = document.querySelector('details.tl-wrap'); if (d) d.open = true })
await win.waitForSelector('.tl-clip')
await win.locator('.tl-clip').first().click()
await win.click('button:has-text("Put its hit on the punch line")')
console.log('after 🎯:', (await win.textContent('.tl-detail-row')).trim())
await win.click('button:has-text("Use this timing")')
await win.waitForTimeout(500)
await win.waitForFunction(() => !document.querySelector('.progress'), null, { timeout: 180000 })
console.log('MANUAL 🎯:', await sync())

await win.evaluate(() => { const d = document.querySelector('details.tl-wrap'); if (d) d.open = true })
await win.click('button:has-text("Back to automatic")')
await win.waitForTimeout(500)
await win.waitForFunction(() => !document.querySelector('.progress'), null, { timeout: 180000 })
console.log('BACK TO AUTO:', await sync())
await app.close()
