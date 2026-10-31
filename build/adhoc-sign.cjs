// Apple Silicon Macs refuse to run unsigned code. Without a paid Apple certificate we "ad-hoc" sign
// the whole app (including ffmpeg/ffprobe) so it runs after the quarantine flag is cleared.
const { execFileSync } = require('node:child_process')
const { join } = require('node:path')

exports.default = async function adhocSign(context) {
  if (context.electronPlatformName !== 'darwin') return
  // Only sign the final merged universal app (Arch.universal === 4); the per-arch halves must stay
  // unsigned so they can be merged cleanly.
  if (context.arch !== 4) {
    console.log('Skipping ad-hoc sign for single-arch half, arch =', context.arch)
    return
  }
  const app = join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`)
  console.log('Ad-hoc signing', app)
  execFileSync('codesign', ['--force', '--deep', '--sign', '-', app], { stdio: 'inherit' })
  execFileSync('codesign', ['--verify', '--deep', '--strict', '--verbose=2', app], { stdio: 'inherit' })
}
