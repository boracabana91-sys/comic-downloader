import type { CattyApi } from '../../preload/index'

declare global {
  interface Window { catty: CattyApi }
  const __APP_VERSION__: string
  const __APP_NAME__: string
}

export {}
