import { promises as fs } from 'node:fs'
import { dirname } from 'node:path'
import { tempNameFor } from './paths'

/**
 * Write a file so it never looks finished unless it is: write to "<name>.partial", then rename.
 * Rename is atomic on the same disk, so a crash leaves only a .partial file behind.
 */
export async function writeFileAtomic(finalPath: string, data: string | Uint8Array): Promise<void> {
  await fs.mkdir(dirname(finalPath), { recursive: true })
  const tmp = tempNameFor(finalPath)
  try {
    await fs.writeFile(tmp, data)
    await fs.rename(tmp, finalPath)
  } catch (err) {
    await fs.rm(tmp, { force: true })
    throw err
  }
}
