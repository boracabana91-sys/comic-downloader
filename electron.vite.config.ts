import { resolve } from 'node:path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'
import pkg from './package.json'

// One single source of truth for the version: package.json.
const define = { __APP_VERSION__: JSON.stringify(pkg.version), __APP_NAME__: JSON.stringify(pkg.productName) }

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    define,
    resolve: { alias: { '@engine': resolve(__dirname, 'src/engine') } },
    build: { rollupOptions: { input: { index: resolve(__dirname, 'src/main/index.ts'), 'mdx-worker': resolve(__dirname, 'src/main/mdx-worker.ts') } } }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    define
  },
  renderer: {
    root: resolve(__dirname, 'src/renderer'),
    define,
    resolve: { alias: { '@engine': resolve(__dirname, 'src/engine') } },
    plugins: [react()],
    build: { rollupOptions: { input: resolve(__dirname, 'src/renderer/index.html') } }
  }
})
