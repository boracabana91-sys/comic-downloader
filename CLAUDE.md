# Cattyfied: notes for Claude

The owner (Anne) is **not a coder**. Plain English, one copy-paste command at a time, few questions.
The full brief is in `docs/BRIEF.md` and `docs/BRIEF_ADDENDUM.md`. Section 1 of the brief is non-negotiable.
Progress and what's unfinished: `PROGRESS.md`. Changes for the owner: `CHANGELOG.md`.

## Architecture
- `src/engine/`: pure TypeScript, **no Electron or macOS-only code** (Windows later). All logic + tests go here.
- `src/main/`: Electron main process (IPC, Keychain via `safeStorage`, file access, running ffmpeg).
- `src/preload/`: the only bridge to the UI (`window.catty`).
- `src/renderer/`: React UI. Never touches files directly.
- `installer/`: files placed inside the .dmg. `build/`: packaging scripts.
- Version: single source = `package.json` `version`. Shown top-right as "Cattyfied vX.Y".

## Commands
- `npm test`: engine tests. `npm run typecheck`. `npm run build`.
- Screenshots on Linux: `xvfb-run -a node scripts/screenshot.mjs docs/screenshots` (needs Playwright linked into node_modules).
- The .dmg is built **only on GitHub's Mac runners** (`.github/workflows/build-mac.yml`). It cannot be built on Linux.

## Rules
- Never overwrite the owner's files; write via `writeFileAtomic` (temp name, then rename).
- Never commit secrets (API keys, update-signing private key).
- When ambiguous (voice vs music, character vs background), ask the owner.
