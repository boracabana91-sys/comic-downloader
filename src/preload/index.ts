import { contextBridge, ipcRenderer, webUtils } from 'electron'

const api = {
  appInfo: () => ipcRenderer.invoke('app:info'),
  getSettings: () => ipcRenderer.invoke('settings:get'),
  setSettings: (s: unknown) => ipcRenderer.invoke('settings:set', s),
  hasKey: () => ipcRenderer.invoke('key:has'),
  testKey: (k: string) => ipcRenderer.invoke('key:test', k),
  saveKey: (k: string) => ipcRenderer.invoke('key:save', k),
  removeKey: () => ipcRenderer.invoke('key:remove'),
  checkTools: () => ipcRenderer.invoke('tools:check'),
  describeFiles: (paths: string[]) => ipcRenderer.invoke('files:describe', paths),
  thumbnail: (path: string, kind: 'image' | 'video') => ipcRenderer.invoke('files:thumbnail', path, kind),
  pickFiles: () => ipcRenderer.invoke('files:pick'),
  ensureFolder: () => ipcRenderer.invoke('folder:ensure'),
  openFolder: () => ipcRenderer.invoke('folder:open'),
  openLink: (url: string) => ipcRenderer.invoke('link:open', url),
  checkTiming: (req: unknown) => ipcRenderer.invoke('project:check', req),
  makeVideo: () => ipcRenderer.invoke('project:render'),
  newProject: () => ipcRenderer.invoke('project:new'),
  reveal: (p: string) => ipcRenderer.invoke('project:reveal', p),
  onProgress: (cb: (p: { step: string; fraction: number | null }) => void) => {
    const h = (_e: unknown, p: { step: string; fraction: number | null }) => cb(p)
    ipcRenderer.on('job:progress', h)
    return () => { ipcRenderer.removeListener('job:progress', h) }
  },
  copyText: (t: string) => navigator.clipboard.writeText(t),
  /** Dropped files: Electron no longer exposes File.path, so ask Electron for it. */
  pathForFile: (f: File) => webUtils.getPathForFile(f)
}

export type CattyApi = typeof api

contextBridge.exposeInMainWorld('catty', api)
