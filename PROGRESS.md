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

## Phase 1 polish (found by testing with the owner's real files)
Tested with real files: a voiceover (.m4a), an intro + chorus music pair (.mp3), a sample video
clip, and an iPhone photo (.HEIC). Fixed what that testing found:
- Added an Intro / Chorus / Single track tag for music cards (needed for the brief's intro→hit→chorus
  handoff). Guessed from the file name, asks when unsure, same as other labels.
- Added real thumbnails on cards (video frame; pictures, converted from HEIC so they display at all —
  Chromium can't show HEIC directly).
- Fixed a real bug the HEIC test file exposed: iPhone photos can store several hidden images in one
  file (a flat grey depth map, the real photo, a small preview). The first pass picked whichever came
  first, which was sometimes the grey map — a solid black thumbnail. Now it skips grey streams and
  picks the real photo. Covered by `tests/thumbnail.test.ts` using the real file's stream layout.
- Note to the owner: the provided IMG_4664.HEIC is a screenshot of character notes, not a photo of the
  character — worth re-sending the actual reference art before Phase 5 (the draw-it engine).

## Phase 2 first draft (v0.2): audio brain + draft video
Works in the app by drag and drop: Check timing → confirm the punch line by ear → Make my video.
Verified on the owner's real files (Sol_Street_69.m4a + money_mode_wil_intro.mp3 + money_mode_wil_chorus_1.mp3 + casanova_v11.mp4):
- 3 phrases found; punch line (part 3) lands at 4.82 s; intro hit found at 9.230 s (the true attack, checked at 5 ms resolution).
- Punch line vs music hit: 0 ms apart (independent re-measurement on the placed tracks).
- Finished MP4 sound vs planned mix: 0 ms (AAC delay checked by cross-correlation).
- Voice 8.0 dB over music; loudness −14.6 LUFS, true peak −1.9 dB (4× oversampled limiter; the plain limiter let inter-sample peaks reach −0.8 dB).
- Frame-by-frame: flash on frame 145 = 4.83 s, then the punch zoom and shake.
Engine: src/engine/{ffmpeg,loudness,video,project,heic}.ts, src/engine/audio/{analysis,timeline,mix}.ts. UI: TimingPanel, ResultPanel. 31 tests (tests/sync.test.ts = the brief's ±1-frame sync, loudness and both-shape render tests on generated sounds).

NOT done yet (honest list):
- No vocal separation model yet (UVR-MDX): a voice file with music baked in only gets a warning.
- No Whisper transcript check yet: the owner confirms the punch line by listening (satisfies "never trust a guess").
- Video is a draft: a clip is reframed and looped (no motion-peak alignment, no slideshow cuts, no lip-sync; that's Phase 3/5). Pictures get a slow push-in, then zoom + shake + flash on the punch line.
- Whoosh SFX on cuts belongs to Phase 3 (no cuts yet). The sub thump on the punch line is in.
- Not yet run by the owner on a real Mac.

## v0.3: Draw-it engine (animated Casanova cat), pulled forward because v0.2 didn't move like the reference
The reference video (casanova_v11.mp4) was made with the cartoon-short-voice-sync skill: a code-drawn character plus a director shot list.
Measured its rhythm: one continuous shot until the punch line (8.27 s), then hard cuts every 1.0 s, each followed by ~3 flash/blur frames.
Built: src/engine/draw/{cat,director,lipsync,pchip,render}.ts using @napi-rs/canvas (Skia, prebuilt for both Mac types).
- cat.ts: limo set + Casanova cat drawn from the owner's picture; rig = lid, winkL/R, brow, look, smirk (only asymmetry), grin, open/wide (lip-sync), blush, headRoll/Bob, glass toast, tail, ear, hearts.
- director.ts: PCHIP camera keys; push-in → punch cut → 1 s takes (wink+laugh+hearts, brow, eye close-up, toast, other wink); blinks; look away in the pause; handheld drift; decaying cut shake; 3-frame flash; blur 3/7/11/7/3.5/1.5.
- lipsync.ts: per-frame RMS (attack 0.7, release 0.35) + spectral-centroid width.
- render.ts: 30 fps, 2× supersample, 3 motion-blur subsamples (never across a cut), raw RGBA streamed to ffmpeg.
- Audio: 'draw' style adds 5 s after the punch line for the takes, plus a whoosh ending on each cut.
Verified in the real app with the owner's files: 11.1 s video; punch/hit 0 ms; MP4 offset 0 ms; −14.4 LUFS, TP −1.9; voice +8.0 dB. Render ≈ 100 s here (Linux cloud CPU).
CI: bundles canvas for both arm64 and x64; CATTY_SELFTEST=1 draws a real frame inside the installed app on both Mac types.
Not done: still one built-in character (the cat). Takes are fixed templates (chat control comes in Phase 4). No 3D throne-style turning props yet. Lip shapes are open/wide only.

## v0.4: manual timeline editor (owner request: fix sync by hand when automatic fails)
- Engine: music is now always a list of clips (src/engine/audio/clips.ts). The automatic plan is converted to clips (clipsFromTimeline), so the editor shows exactly what auto did, and manual placements go through the same placeClips → mixPlaced path. Manual positions are stored relative to the punch line.
- buildAudio(manualMusic) + plan.editor (waveform peaks at 100/s, hits per file, clips, manual flag).
- UI: TimelineEditor.tsx (drag/trim/snap/move-together/nudge/numeric/drop-to-place/Web Audio preview).
- Found and fixed while testing: the live preview was blocked by the window's security policy (connect-src, then CORS on catty-media://). Now allowed for that private scheme only; preview errors show a message.
- Tested in the real app (scripts/editor-flow.mjs): auto 0 ms → drag +445 ms → +1 frame 478 ms → applied mix measured 480–485 ms → 🎯 back to 0 ms → Back to automatic 0 ms; preview playhead advances. Engine tests: manual +250 ms measured 220–280 ms; dropped file placed by hand lands within one frame.
