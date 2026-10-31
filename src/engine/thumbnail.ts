// Picking the right image inside a file for a thumbnail.
//
// A HEIC photo (the default format iPhones save in) can bundle several hidden images in one file:
// a depth/gain map (flat grey, useless as a picture), a full-size photo, and a small preview.
// ffmpeg's default pick is "whichever stream comes first", which is sometimes the grey one — that
// showed up as a solid black thumbnail when testing with a real iPhone photo. This picks the real
// picture instead: skip grey streams, then prefer the biggest one.

export interface VideoStreamInfo {
  index: number // ffmpeg's 0-based position among VIDEO streams in the file (for -map 0:v:N)
  width: number
  height: number
  grey: boolean
}

/** Parses the "Stream #0:N[...]: Video: ... WxH ..." lines ffmpeg prints to stderr with `-i`. */
export function parseVideoStreams(ffmpegStderr: string): VideoStreamInfo[] {
  const lines = ffmpegStderr.split('\n').filter((l) => /Stream #0:\d+.*Video:/.test(l))
  return lines.map((line, i) => {
    const size = line.match(/(\d{2,5})x(\d{2,5})/)
    const grey = /\bgray\b/.test(line)
    return { index: i, width: size ? Number(size[1]) : 0, height: size ? Number(size[2]) : 0, grey }
  })
}

/** Returns the ffmpeg video-stream index (for `-map 0:v:<n>`) most likely to be the real picture. */
export function pickThumbnailStream(streams: VideoStreamInfo[]): number {
  if (streams.length === 0) return 0
  const real = streams.filter((s) => !s.grey)
  const pool = real.length ? real : streams
  return pool.reduce((best, s) => (s.width * s.height > best.width * best.height ? s : best)).index
}
