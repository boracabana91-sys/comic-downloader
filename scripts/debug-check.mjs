import { _electron as electron } from 'playwright'
import { mkdtempSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { createRequire } from 'node:module'
const files = process.argv.slice(2)
const home = mkdtempSync(join(tmpdir(), 'catty-home-'))
import { mkdirSync, copyFileSync, writeFileSync } from 'node:fs'
mkdirSync(join(home, 'ud', 'models'), { recursive: true })
copyFileSync('/tmp/models/UVR-MDX-NET-Voc_FT.onnx', join(home, 'ud', 'models', 'UVR-MDX-NET-Voc_FT.onnx'))
writeFileSync(join(home, 'ud', 'models', 'UVR-MDX-NET-Voc_FT.onnx.verified'), 'local')
const app = await electron.launch({
  executablePath: createRequire(import.meta.url)(resolve('node_modules/electron')),
  args: ['--no-sandbox', `--user-data-dir=${join(home, 'ud')}`, resolve('.')],
  env: { ...process.env, HOME: home, ELECTRON_ENABLE_LOGGING: '1' }
})
app.process().stdout.on('data', (d) => process.stdout.write('[main] ' + d))
app.process().stderr.on('data', (d) => { const s = d.toString(); if (!/dbus|Fontconfig|gpu_|GPU|viz|ssl_client/.test(s)) process.stdout.write('[main-err] ' + s) })
app.process().on('exit', (code, sig) => console.log('[main exited]', code, sig))
const win = await app.firstWindow()
win.on('console', (m) => console.log('[page]', m.type(), m.text()))
win.on('pageerror', (e) => console.log('[pageerror]', e.message))
await win.waitForSelector('.version')
await win.click('text=Let’s start'); await win.click('text=Skip for now'); await win.click('text=Next →'); await win.click('text=Open Cattyfied')
await app.evaluate(async ({ dialog }, p) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: p }) }, files)
await win.click('text=click to choose files')
await win.waitForSelector('.card')
await win.click('text=Check timing')
for (let i = 0; i < 100; i++) {
  await win.waitForTimeout(3000).catch(() => {})
  const st = await win.evaluate(() => ({ prog: document.querySelector('.progress-label')?.textContent, bar: document.querySelector(".progress-fill")?.style?.width, err: document.querySelector('.banner.error')?.textContent, timing: !!document.querySelector('.timing'), hint: document.querySelector('.hint')?.textContent }))
  console.log(`[t=${(i + 1) * 3}s]`, JSON.stringify(st))
  if (st.timing || st.err) break
}
await app.close().catch(() => {})
