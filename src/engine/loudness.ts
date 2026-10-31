import { runTool } from './ffmpeg'

export interface Loudness {
  lufs: number
  truePeakDb: number
}

/** Measure integrated loudness and true peak (brief: ebur128=peak=true). */
export async function measureLoudness(ffmpeg: string, file: string): Promise<Loudness> {
  const { stderr } = await runTool(ffmpeg, ['-nostats', '-i', file, '-af', 'ebur128=peak=true', '-f', 'null', '-'])
  const summary = stderr.slice(stderr.lastIndexOf('Summary:'))
  const i = summary.match(/I:\s+(-?[\d.]+|-inf)\s+LUFS/)
  const p = summary.match(/True peak:\s+Peak:\s+(-?[\d.]+|-inf)\s+dBFS/)
  if (!i || !p) throw new Error('Could not read the loudness measurement.')
  return { lufs: i[1] === '-inf' ? -70 : Number(i[1]), truePeakDb: p[1] === '-inf' ? -70 : Number(p[1]) }
}

/**
 * Bring a WAV to the target loudness (brief: about −14…−16 LUFS, `volume` + `alimiter=limit=0.8:level=disabled`),
 * then verify the true peak stays below −1 dBFS. Retries with less gain if the peak is too high.
 */
export async function normalizeLoudness(
  ffmpeg: string,
  input: string,
  output: string,
  targetLufs = -14
): Promise<Loudness & { gainDb: number }> {
  const before = await measureLoudness(ffmpeg, input)
  let gainDb = targetLufs - before.lufs
  for (let attempt = 0; attempt < 4; attempt++) {
    await runTool(ffmpeg, [
      '-y', '-v', 'error', '-i', input,
      // Limit once normally, then again at 4× resolution so in-between ("true") peaks are caught too.
      '-af', `volume=${gainDb.toFixed(2)}dB,alimiter=limit=0.8:level=disabled,aresample=176400,alimiter=limit=0.8:level=disabled,aresample=44100`,
      '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le', output
    ])
    const after = await measureLoudness(ffmpeg, output)
    if (after.truePeakDb < -1) return { ...after, gainDb }
    gainDb -= after.truePeakDb + 1.2
  }
  const after = await measureLoudness(ffmpeg, output)
  return { ...after, gainDb }
}

export function describeLoudness(l: Loudness): string {
  const level =
    l.lufs > -12 ? 'a bit loud' : l.lufs >= -16.5 ? 'just right for YouTube, Facebook and Reels' : 'a bit quiet'
  const peak = l.truePeakDb < -1 ? 'no distortion risk' : 'peaks are close to distorting'
  return `Loudness ${l.lufs.toFixed(1)} LUFS (${level}); ${peak} (peak ${l.truePeakDb.toFixed(1)} dB).`
}
