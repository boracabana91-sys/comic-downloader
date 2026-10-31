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
  pickFiles: () => ipcRenderer.invoke('files:pick'),
  ensureFolder: () => ipcRenderer.invoke('folder:ensure'),
  openFolder: () => ipcRenderer.invoke('folder:open'),
  openLink: (url: string) => ipcRenderer.invoke('link:open', url),
  /** Dropped files: Electron no longer exposes File.path, so ask Electron for it. */
  pathForFile: (f: File) => webUtils.getPathForFile(f)
}

export type CattyApi = typeof api

contextBridge.exposeInMainWorld('catty', api)
