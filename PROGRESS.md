# Progress

## Phase 1: Skeleton + installer (v0.1), in progress

Done and checked on Linux (tests + real app launched + screenshots in `docs/screenshots/`):
- Main window: drop zone with labelled cards (Voice / Music / Character / Background / Video / Notes), one-click relabel, ❓ + "please tell me" when unsure.
- Format switch: Shorts/Reels 9:16 (1080×1920) or YouTube/Facebook 16:9 (1920×1080).
- Version "Cattyfied v0.1" in the top-right corner.
- First-run wizard (4 screens): welcome → Anthropic key (tested, stored in Keychain via safeStorage, skippable) → channel profile (Casanova / Anachron / new) → done.
- Bigger-text switch, "Open my projects folder" (~/Documents/Cattyfied).
- Chat panel placeholder (real chat = Phase 4). Make/Preview/Export buttons disabled until Phases 2–3.
- 13 automated tests pass (labelling, formats/safe zones, settings repair, version label, atomic writes, ffmpeg runs).
- Installer files: "Double-click me first.command", "Start Here.html" (drawn illustrations), README.txt.
- Mac build robot (GitHub Actions): universal ffmpeg/ffprobe via lipo, ad-hoc signing, .dmg, then an install + launch test on Apple Silicon and on Intel.

NOT done yet / not verified:
- ✅ First .dmg built by CI (run 41219723928): app + ffmpeg + ffprobe are universal (x86_64 + arm64), ad-hoc signature valid, and it installed and stayed open on both an Apple Silicon and an Intel runner.
- The Apple Silicon and Intel halves of the ffmpeg-static release are different builds (6.0 vs 6.1.1). Fine for now; pin one version in Phase 2 if audio results differ between Macs.
- The .dmg is about 300 MB (universal Electron + 2× ffmpeg).
- Not yet tested on a real Mac by the owner.
- The "Double-click me first" file is itself blocked by macOS on first open (it came from the internet). The Start Here page covers "Open Anyway". There's no way around this without a paid Apple Developer account ($99/year).
- Start Here uses drawn pictures, not real screenshots. Swap in real ones after the owner's first install.
- Model downloads with progress bar (vocal separation, speech check) belong to Phase 2.
- Real audio analysis for labelling (speech vs music, music baked into voice) belongs to Phase 2. Today's labelling uses file names only.
- Phase 0 spikes still to run on a Mac: separation speed, Tagalog Whisper accuracy.
