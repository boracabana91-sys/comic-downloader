// Vocal isolation runs in its own helper process (Electron in plain-Node mode). onnxruntime crashes inside
// Electron's main process (V8 memory rules), and a separate process also keeps the window responsive.
// Usage: <electron> mdx-worker.js <ffmpeg> <model.onnx> <in.wav> <out.wav>   (env ELECTRON_RUN_AS_NODE=1)
// Prints "P <fraction>" progress lines and "OK" at the end.
import { decodeAudio, encodeWav } from '../engine/ffmpeg'
import { isolateVocals, type OrtLike } from '../engine/audio/mdx'
import { writeFileSync, renameSync } from 'node:fs'

async function main() {
  const [ffmpeg, model, inWav, outWav] = process.argv.slice(2)
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const ort = require('onnxruntime-node') as OrtLike
  const mix = await decodeAudio(ffmpeg, inWav)
  const voc = await isolateVocals(ort, model, mix, (f) => process.stdout.write(`P ${f.toFixed(3)}\n`))
  writeFileSync(outWav + '.partial', encodeWav(voc))
  renameSync(outWav + '.partial', outWav)
  process.stdout.write('OK\n')
}

main().catch((e) => {
  process.stderr.write(String((e as Error)?.stack ?? e))
  process.exit(1)
})
