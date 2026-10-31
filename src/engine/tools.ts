import { join } from 'node:path'

export interface ToolPaths { ffmpeg: string; ffprobe: string }

/**
 * Where the bundled ffmpeg/ffprobe live.
 * Packaged app: <resources>/bin (one universal binary for Apple Silicon + Intel).
 * Development: the npm packages.
 */
export function resolveToolPaths(opts: {
  packaged: boolean
  resourcesPath: string
  platform: NodeJS.Platform
  devFfmpeg: string | null
  devFfprobe: string | null
}): ToolPaths {
  const exe = opts.platform === 'win32' ? '.exe' : ''
  if (opts.packaged) {
    return {
      ffmpeg: join(opts.resourcesPath, 'bin', `ffmpeg${exe}`),
      ffprobe: join(opts.resourcesPath, 'bin', `ffprobe${exe}`)
    }
  }
  if (!opts.devFfmpeg || !opts.devFfprobe) throw new Error('ffmpeg/ffprobe not installed in development')
  return { ffmpeg: opts.devFfmpeg, ffprobe: opts.devFfprobe }
}
