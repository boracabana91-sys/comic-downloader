# ADDENDUM to the Punchline Studio brief (paste right after the original brief)

These additions are mine as your product/engineering helper. They never override section 1 of the brief.

## 0. Name and version (owner's decision)
- The app is named **Cattyfied** (replaces the working name "Punchline Studio" everywhere: app, .dmg, folders `~/Documents/Cattyfied/`, installer script, guides).
- The version is always visible in the **top-right corner** of the main window as **"Cattyfied vX.Y"**. It comes from one single source (package version), so it updates automatically with every release and update pack.

## A. Honest constraints to handle up front
1. **A .dmg can only be built on a Mac.** Do not pretend otherwise. Set up a **GitHub Actions macOS runner** that builds, ad-hoc signs, tests and uploads the universal .dmg. Tell me the one-time steps (create GitHub account/repo) in plain English.
2. **Apple Silicon refuses unsigned arm64 code.** Ad-hoc sign everything (`codesign --force --deep --sign -`) including bundled ffmpeg/ffprobe and native modules, then verify on both architectures. Newer macOS versions also removed the old right-click → Open shortcut: the "Start Here" page must show **System Settings → Privacy & Security → Open Anyway** too. Check the current behaviour before writing the page.
3. **Universal builds are tricky** (`ffmpeg-static`, `onnxruntime-node`, `sharp`, `sherpa-onnx` ship per-architecture binaries). Prove this works in a spike before building features on it.
4. **FFmpeg licensing**: libx264 is GPL. For personal use that is fine; say so in the notes, and fall back to `h264_videotoolbox` if the bundled build lacks x264.

## B. Phase 0 (before Phase 1): 1-day feasibility spikes
Run each, report pass/fail in plain words, and change the plan if one fails:
- Vocal separation speed on a base M1 and an old Intel Mac (target: under 2 min for a 60 s clip; show real progress).
- Whisper-small Tagalog accuracy on a sample of my voice; define the "mismatch" threshold from real data, not a guess.
- Universal .dmg launches on a clean Mac (arm64 and x64) with the bundled ffmpeg.

## C. Sync you can prove
- Work in **samples, not seconds**: store the punch-line onset and the music hit as sample positions; convert to frames only at render.
- Compensate for **AAC encoder delay** (about 1024 samples of priming) so the muxed file still lands on the hit.
- After every render, run an **automatic QA report** that re-measures the finished file: voice onset vs music hit (in ms and frames), loudness/true peak, duration, black/frozen frames, audio clipping. Show green/red results in plain words and refuse to call a red result "done".
- Generate **synthetic test fixtures in code** (click track + tone "voice") so the sync/loudness/reframe tests run anywhere with no copyrighted files.
- Add **golden-frame tests** for the draw-it engine (same input gives the same frame, within tolerance).

## D. Safety, privacy, cost
- API key only in Keychain, never logged, never in the project folder. **Send only text and metadata to the API, never my voice, music or video.** No telemetry.
- A **monthly spend cap** I can set, a warning at 80%, and a hard stop at 100%. Use a cheap model for captions/hashtags and the stronger one only for planning.
- Show a **dry-run cost** before any web-search or multi-step chat action.
- Project files carry a **schema version** with migrations, so old projects open after updates. Automatic backup before each migration.
- **Render robustness**: cancel button, resume after crash, temp-file cleanup, free-disk check before starting, never block the UI thread (render in a separate process).

## E. Posting and platform rules
- Verify current limits instead of trusting memory: Shorts max length, Reels max length, Facebook Reels specs, caption/hashtag limits.
- Add a toggle for YouTube's **"altered or synthetic content" disclosure** and Meta's AI label, defaulting on for AI-generated footage, with a one-line explanation.
- Check recycled/duplicate-content risk: warn me if two videos in a batch share the same intro/music/structure.

## F. Small things that make it feel great
- **Sample project** that works offline on first launch so I can see success in 2 minutes.
- **A/B hook generator**: 3 candidate punch-line pause lengths (1.5 / 2.0 / 2.5 s) as quick low-res previews, so I choose by ear.
- **"Why did it do that?"** panel listing each decision (which hit, which cut points) with a play button at that moment.
- **Panic button**: "Undo everything since last good render."
- Plain-English error list with a "Fix it for me" button wherever a fix is possible; otherwise a one-click "Copy diagnostics".
- Log licence and source for every downloaded asset into a **credits.txt** exported with each video.

## G. How we work together
- Keep a `PROGRESS.md` and a short `CLAUDE.md` in the repo (architecture, decisions, how to run tests, what is unfinished) so any new session picks up exactly where we stopped.
- Use git: one commit per finished step, a tag per phase, and tell me how to roll back in one copy-paste line.
- End every phase with: what works, how to try it, what is NOT done, and the next phase's risks.
