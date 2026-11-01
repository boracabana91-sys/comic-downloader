# Cattyfied: notes for Claude

The owner (Anne) is **not a coder**. Plain English, one copy-paste command at a time, few questions.
The full brief is in `docs/BRIEF.md` and `docs/BRIEF_ADDENDUM.md`. Section 1 of the brief is non-negotiable.
Progress and what's unfinished: `PROGRESS.md`. Changes for the owner: `CHANGELOG.md`.

## The rules (owner's reference kit)
- `.claude/skills/cartoon-short-voice-sync/SKILL.md` is the recipe; follow it. `reference_kit/` is the owner's proven
  reference: `tools/audio_brain.py` (audio timing), `tools/mdx.py` (vocal isolation), `engine_reference/cat_run.py`
  (director), `golden/` (the video to match + expected numbers). Port numbers faithfully; never simplify.
- Design: measure → timeline.json → render → verify. Nothing about timing is hard-coded. Never a loop or fixed template.
- The mouth is driven by vo.wav (voice only), never the mix. The owner must confirm the punch-line units.
- `tests/golden.test.ts` = the acceptance tests; needs Sol_Street_71.m4a, money_mode_wil_intro.mp3,
  money_mode_wil_chorus_2.mp3 in /tmp/golden_inputs (or CATTY_GOLDEN_DIR) and the UVR model.
- Verify ports against the reference Python: `python3 -m venv /tmp/refenv && /tmp/refenv/bin/pip install numpy scipy onnxruntime`,
  then run reference_kit/tools/audio_brain.py on the same inputs and compare timeline.json + the wavs.

## Architecture
- `src/engine/`: pure TypeScript, **no Electron or macOS-only code** (Windows later). All logic + tests go here.
  - `audio/mdx.ts` (UVR-MDX port, exact 7680-pt FFT via Bluestein), `audio/brain.ts` (audio_brain.py port),
    `draw/director.ts` (cat_run.py port, from timeline), `draw/lipsync.ts`, `draw/render.ts`, `preflight.ts`.
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
