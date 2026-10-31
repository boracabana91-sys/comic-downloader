import { join } from 'node:path'

export const APP_FOLDER_NAME = 'Cattyfied'

/** All projects live in ~/Documents/Cattyfied/. The owner's original files are never touched: we copy in. */
export function appFolder(documentsDir: string): string {
  return join(documentsDir, APP_FOLDER_NAME)
}

export function projectsFolder(documentsDir: string): string {
  return join(appFolder(documentsDir), 'Projects')
}

/** Safe folder name for a project: no slashes or odd characters, never empty. */
export function safeName(name: string): string {
  const cleaned = name.replace(/[\\/:*?"<>|\u0000-\u001f]/g, ' ').replace(/\s+/g, ' ').trim()
  return cleaned.slice(0, 80) || 'Untitled'
}

/** Temp name used while writing; renamed to the final name only on success. */
export function tempNameFor(finalPath: string): string {
  return `${finalPath}.partial`
}
