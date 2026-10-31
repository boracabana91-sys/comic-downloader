import { join } from 'node:path'

export interface ToolPaths { ffmpeg: string }

/**
 * Where the bundled ffmpeg lives (it does all the audio/video work; ffprobe is not shipped,
 * which keeps the download much smaller).
 * Packaged app: <resources>/bin. Development: the npm package.
 */
export function resolveToolPaths(opts: {
  packaged: boolean
  resourcesPath: string
  platform: NodeJS.Platform
  devFfmpeg: string | null
}): ToolPaths {
  const exe = opts.platform === 'win32' ? '.exe' : ''
  if (opts.packaged) return { ffmpeg: join(opts.resourcesPath, 'bin', `ffmpeg${exe}`) }
  if (!opts.devFfmpeg) throw new Error('ffmpeg not installed in development')
  return { ffmpeg: opts.devFfmpeg }
}
