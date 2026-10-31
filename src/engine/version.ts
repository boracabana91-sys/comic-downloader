/** "0.1.0" -> "Cattyfied v0.1". Patch numbers are hidden unless non-zero. */
export function versionLabel(appName: string, version: string): string {
  const [maj = '0', min = '0', patch = '0'] = version.split('-')[0].split('.')
  const short = patch === '0' ? `${maj}.${min}` : `${maj}.${min}.${patch}`
  return `${appName} v${short}`
}
