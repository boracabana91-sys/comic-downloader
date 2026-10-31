import { app, BrowserWindow, ipcMain, safeStorage, shell, dialog } from 'electron'
import { join, basename } from 'node:path'
import { promises as fs, existsSync } from 'node:fs'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { guessKind, allowedKinds } from '../engine/classify'
import { migrateSettings, looksLikeAnthropicKey, type Settings } from '../engine/settings'
import { appFolder, projectsFolder } from '../engine/paths'
import { resolveToolPaths } from '../engine/tools'
import { writeFileAtomic } from '../engine/atomic'

const run = promisify(execFile)

app.setName('Cattyfied')

const settingsFile = () => join(app.getPath('userData'), 'settings.json')
const keyFile = () => join(app.getPath('userData'), 'anthropic-key.bin')

async function loadSettings(): Promise<Settings> {
  try {
    return migrateSettings(JSON.parse(await fs.readFile(settingsFile(), 'utf8')))
  } catch {
    return migrateSettings(null)
  }
}

async function saveSettings(s: Settings): Promise<Settings> {
  const clean = migrateSettings(s)
  await writeFileAtomic(settingsFile(), JSON.stringify(clean, null, 2))
  return clean
}

function devToolPath(mod: string): string | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const m = require(mod)
    return typeof m === 'string' ? m : m.path ?? null
  } catch {
    return null
  }
}

function tools() {
  return resolveToolPaths({
    packaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    platform: process.platform,
    devFfmpeg: app.isPackaged ? null : devToolPath('ffmpeg-static'),
    devFfprobe: app.isPackaged ? null : devToolPath('ffprobe-static')
  })
}

async function testKey(key: string): Promise<{ ok: boolean; message: string }> {
  if (!looksLikeAnthropicKey(key)) {
    return { ok: false, message: 'That doesn’t look like an Anthropic key. It should start with “sk-ant-”.' }
  }
  try {
    const res = await fetch('https://api.anthropic.com/v1/models?limit=1', {
      headers: { 'x-api-key': key.trim(), 'anthropic-version': '2023-06-01' }
    })
    if (res.ok) return { ok: true, message: 'Your key works!' }
    if (res.status === 401) return { ok: false, message: 'Anthropic says this key is not valid. Please copy it again.' }
    if (res.status === 403) return { ok: false, message: 'This key has no permission. Check your Anthropic account billing.' }
    return { ok: false, message: `Anthropic answered with an error (${res.status}). Try again in a minute.` }
  } catch {
    return { ok: false, message: 'I can’t reach the internet. Check your Wi-Fi and try again.' }
  }
}

function registerIpc(): void {
  ipcMain.handle('app:info', () => ({
    name: app.getName(),
    version: app.getVersion(),
    platform: process.platform,
    arch: process.arch
  }))

  ipcMain.handle('settings:get', () => loadSettings())
  ipcMain.handle('settings:set', (_e, s: Settings) => saveSettings(s))

  ipcMain.handle('key:has', () => existsSync(keyFile()))
  ipcMain.handle('key:test', (_e, key: string) => testKey(key))
  ipcMain.handle('key:save', async (_e, key: string) => {
    const result = await testKey(key)
    if (!result.ok) return result
    if (!safeStorage.isEncryptionAvailable()) {
      return { ok: false, message: 'Your Mac’s secure storage (Keychain) is not available, so I won’t save the key.' }
    }
    await writeFileAtomic(keyFile(), safeStorage.encryptString(key.trim()))
    return { ok: true, message: 'Your key works and is saved safely in your Mac’s Keychain.' }
  })
  ipcMain.handle('key:remove', async () => {
    await fs.rm(keyFile(), { force: true })
    return true
  })

  ipcMain.handle('tools:check', async () => {
    try {
      const t = tools()
      const [a, b] = await Promise.all([run(t.ffmpeg, ['-version']), run(t.ffprobe, ['-version'])])
      return { ok: true, ffmpeg: a.stdout.split('\n')[0], ffprobe: b.stdout.split('\n')[0] }
    } catch (err) {
      return { ok: false, message: 'The video tools inside the app could not start.', detail: String(err) }
    }
  })

  ipcMain.handle('files:describe', async (_e, paths: string[]) => {
    const out = []
    for (const p of paths) {
      try {
        const st = await fs.stat(p)
        if (!st.isFile()) continue
        const name = basename(p)
        out.push({ path: p, name, size: st.size, guess: guessKind(name), allowed: allowedKinds(name) })
      } catch {
        /* skip unreadable files */
      }
    }
    return out
  })

  ipcMain.handle('folder:ensure', async () => {
    const docs = app.getPath('documents')
    await fs.mkdir(projectsFolder(docs), { recursive: true })
    return appFolder(docs)
  })
  ipcMain.handle('folder:open', async () => {
    const docs = app.getPath('documents')
    await fs.mkdir(projectsFolder(docs), { recursive: true })
    return shell.openPath(appFolder(docs))
  })

  const ALLOWED_LINKS = ['https://console.anthropic.com/', 'https://docs.anthropic.com/', 'https://www.anthropic.com/']
  ipcMain.handle('link:open', (_e, url: string) => {
    if (ALLOWED_LINKS.some((p) => url.startsWith(p))) return shell.openExternal(url)
    return false
  })

  ipcMain.handle('files:pick', async () => {
    const r = await dialog.showOpenDialog({ properties: ['openFile', 'multiSelections'] })
    return r.canceled ? [] : r.filePaths
  })
}

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 640,
    title: 'Cattyfied',
    backgroundColor: '#fff8f2',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    show: false,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      sandbox: false,
      nodeIntegration: false
    }
  })
  win.once('ready-to-show', () => win.show())
  // Never let the app open random web pages inside its own window.
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (e) => e.preventDefault())

  if (process.env.ELECTRON_RENDERER_URL) win.loadURL(process.env.ELECTRON_RENDERER_URL)
  else win.loadFile(join(__dirname, '../renderer/index.html'))
}

app.whenReady().then(() => {
  registerIpc()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
