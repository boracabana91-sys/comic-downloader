# BUILD BRIEF — "Punchline Studio" (working name; I can rename it later)

You are building a Mac app for me. **I am not a coder.** Talk to me in plain English, never assume I know terminal commands, and give me one copy-paste command at a time when I have to run something. Work in phases (section 11). After each phase, tell me in 3 lines what works and exactly how to try it. Do not ask me many questions: make sensible choices, tell me what you chose, and only ask when a wrong guess would cost me a lot.

## 1. Why this app exists (do NOT break these)

I make short vertical comedy/"Casanova"-style cartoon videos (and what-if videos for another channel) where a **voiceover, background music and the picture are timed perfectly to a punch line**. The app turns my files into a finished, posted-ready video with almost no effort. These are non-negotiable:

1. **Punch-line sync is the product.** The punch line must land exactly on a music hit, with a configurable pause before it (default 2.0 s) while the music keeps running. Everything else is secondary to this.
2. **My voice file is used as-is.** Clean it, never replace or fake it. Louder but never overpowering the music (voice about 8 dB above the music while speaking).
3. **Never trust a guess about what the voice says.** Transcribe it; if the transcript doesn't match the line I gave (Tagalog transcription is unreliable), STOP and ask me which phrase is the punch line.
4. **Show me a picture first.** Before any full render, show a still of the character/scene and the key frames, and wait for my OK. One full render per request whenever possible.
5. **No on-screen text unless I switch it on.**
6. **Characters stay consistent** (same look, always seated if I said seated, symmetric mouth, blush inside the face). Reuse the saved character; never silently change it.
7. **Never overwrite my original files.** Work on copies. All projects live in `~/Documents/Punchline Studio/`.
8. A failed render must never leave a half-written file that looks finished (write to a temp name, rename on success).

## 2. Install must be granny-proof

- Deliver one **.dmg** (universal: Apple Silicon + Intel). Inside it: the app, and a big file called **"Double-click me first.command"**. That script must run `xattr -cr` on the app, copy it to Applications, open it, and print friendly messages ("All done! You can close this window."). Also put the plain command in a README for people who prefer typing: `xattr -cr "/Applications/Punchline Studio.app"`.
- The app is not Apple-signed, so ship a picture-based "Start Here" page (HTML or PDF) that shows the right-click → Open fallback.
- **Everything bundled**: ffmpeg, audio tools, fonts. Big AI models (vocal separation ~70 MB, speech check) download on first launch with a clear progress bar and a retry button. No Python, Node, Homebrew or terminal needed by me.
- **First-run wizard** (max 4 screens, big buttons): 1) Welcome, 2) paste my Anthropic API key (show a "where do I get this?" link and screenshots, test the key, store it in the macOS Keychain, show a rough cost estimate per video), 3) pick my channel profile or make one, 4) done.
- Windows support later; design so it is possible (no mac-only code in the engine).

## 3. Main screen (simple, big, friendly)

One window, three zones:

1. **Drop zone** (huge, centre): "Drop everything here". I can drop pictures, **voiceover**, **background music**, **video clips** (e.g. from Higgsfield/Kling), and notes, all at once. The app auto-detects what each file is by type AND by analysis (speech vs music; a voice file with music baked in is flagged), shows each as a labelled card (Voice / Music / Character picture / Background picture / Video clip) and lets me change the label with one click. If it is ambiguous, ask — mislabelling voice vs music already happened to me once.
2. **Format ticker** (a clear switch, default Shorts/Reels): **Shorts/Reels 9:16 (1080×1920)** or **YouTube/Facebook 16:9 (1920×1080)**. Rendering/reframing happens natively for the chosen format (not a crop of the other one): smart reframe, blurred-fill option, safe zones so Shorts/Reels buttons never cover the face or captions.
3. **Chat panel** (right side): talk to the app in plain language ("make the background a rooftop at night", "make the cuts faster", "more pause before the punch line", "use the same music as last time"). The assistant changes the project settings, shows me a preview still, and only renders after I say go.

Bottom bar: big **Make my video** button, progress, **Preview** (low-res quick draft, a few seconds) and **Export**.

## 4. Smart memory ("use the last one?")

Keep a library: characters, voices, backgrounds/music, locations, last-used settings, per channel profile (e.g. "Casanova", "Anachron"). If I forget something, the app must suggest: *"No background music dropped — use the one from your last video (name, play button)? [Yes] [Choose another]"*. Same for the character and the voiceover. Never auto-use without showing me what it is.

## 5. The video engine (use what we already worked out)

Two engines, same sync brain:

**A) "Edit my clip" engine** (user supplies the AI-made video, voice, music): trim and retime the clips so the key action (wink/smirk/look at camera) lands on the punch line; insert the pause; build slideshow cuts; reframe to the chosen ratio; replace the clip's own audio; stretch the length by reusing takes; export. Detect the motion/face peak in the clip to align it. Be honest in the UI when a clip's mouth doesn't match my voice (offer: hide with cuts, or "needs a lip-sync tool").

**B) "Draw it" engine** (code-drawn cartoon, from my character pictures/saved character): 30 fps, 2× supersample, 3 temporal subsamples for motion blur, shot list ("director" keyframes: zoom, pan, roll, tilt, eyes, wink, brow, smirk, grin, blush, look, hearts) interpolated with PCHIP so motion never stops dead between keys. Lip-sync from the voice-only track: per-frame RMS envelope (fast attack 0.7, slow release 0.35), mouth width from spectral centroid, mouth always symmetric except an explicit smirk value. Props like a chair/seat as pseudo-3D faces with painter's sort. Be upfront in the UI that code-drawn animation is stiffer than hand-animated cartoons and that layered character art from me gives the biggest jump.

### Audio pipeline (shared)
1. Convert input to 44.1 kHz stereo WAV.
2. **Vocal isolation** (when music is baked into the voice): model `UVR-MDX-NET-Voc_FT.onnx` from `https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Voc_FT.onnx`, run via onnxruntime. Settings: n_fft=7680, hop=1024, dim_f=3072, dim_t=256, chunk=hop*(dim_t-1), Hann window, reflect padding, input `[1,4,3072,256]` (real/imag of both channels), zero-pad bins 3072..3840 on the output, overlap-add with window-square normalisation, trim n_fft/2 at chunk edges, ×1.021.
3. Clean the stem with ffmpeg: `highpass=85, lowpass=10500, afftdn=nr=12:nf=-45, agate=threshold=0.008:ratio=3:attack=4:release=120, equalizer=f=220:g=1.5, equalizer=f=3000:g=2.5, acompressor=threshold=0.05:ratio=3:makeup=2, loudnorm=I=-13:TP=-1.5`.
4. **Find phrases**: `silencedetect=noise=-38dB:d=0.18`; cut each phrase with ~50 ms padding and 15 ms fades; re-place on a silent timeline (the long pause before the punch line is a feature). Check words with a bundled Whisper-small (sherpa-onnx, language selectable, Tagalog = `tl`) — use only as a sanity check, and ask me when it doesn't match.
5. **Music alignment**: 50 ms RMS envelope; hits = biggest ratio of mean(next 3–7 frames) / mean(previous 8–2 frames); autocorrelate onset envelope for tempo. Shift/trim music so a hit lands exactly on the punch line. If I give an *intro* and a *chorus* file: intro ends with a dip then a hit → start the intro at an offset so that hit lands on the punch line, and start the chorus where the intro ends. To lengthen a bed, repeat the 2 s before the cut point (stutter edit).
6. **Mix**: music gain ~0.85, ducked ~40% by a smoothed voice envelope (60 ms RMS, 250 ms smoothing); voice gain ~1.45. Subtle SFX only: sub thump (sine 48 Hz + 60 Hz sweep, decay 7/s) on the punch line, band-passed noise whoosh (0.28 s, quadratic rise) ending on each cut. Normalise to about −14…−16 LUFS with `volume` + `alimiter=limit=0.8:level=disabled`; verify true peak below −1 dBFS (`ebur128=peak=true`). Show me the loudness result in plain words.
7. **Slideshow cuts** (optional style, default for punch line): 1 s takes, hard cut + 3-frame white flash + gaussian blur on the frames around the cut (radius 3, 7, 11, 7, 3.5, 1.5) + handheld shake that decays after each cut.

Rendering rules: one encoded file per scene, same size/fps/encoder settings, join with the concat demuxer (`-c copy`), add sound with `-c:v copy`; H.264 `-preset veryfast`, yuv420p, AAC; JPEG/PNG frames only when drawing. Show a progress bar with a real estimate.

## 6. Posting and scheduling (Buffer / Facebook / YouTube)

Goal: after the video is made, I click **Schedule** and pick date/time + channel.
- First **research the current status** of: Buffer's API (its public API access has been limited — verify), the YouTube Data API (`videos.insert` with `status.publishAt`; note that uploads from unverified/unaudited API projects can be forced private and there are daily quota limits — verify and tell me), and Facebook Graph API scheduled Page posts/Reels. Tell me what is really possible in plain English before building.
- Build in this order: (1) **Export folder for Buffer**: a tidy folder with the video, a generated title/caption/hashtags text file (in the language I choose, Tagalog/English), thumbnail, and suggested posting times, plus a one-click "Open Buffer" button; (2) **direct YouTube scheduling** with a guided one-time connection wizard; (3) **direct Facebook scheduling**; (4) Buffer API only if it is truly available to me.
- A **calendar view** of what is scheduled/posted. Never post anything without showing me a final confirmation screen (video, caption, time, account).

## 7. Chat assistant and internet access

- Chat uses the Anthropic API with tool-use so it can: change project settings, search the web, fetch assets, re-run a preview, and explain what it did. It keeps the whole project state so "go back to the previous version" works.
- **Internet**: web search (Anthropic web-search tool or equivalent) for background ideas, VFX/sound effects, locations, trends and hooks. Download only **freely licensed** assets (Pexels, Pixabay, Wikimedia Commons, etc.) and **record the source and licence** of every asset in the project. Never use copyrighted music or characters; never download photos of real public figures for use in the video.
- Always show me 3–6 options with previews (a still or a short loop) before applying a new background.

## 8. Drag-and-drop updates

- A small "Update" drop target (and a menu item) accepts an **update pack** file. The app verifies it (checksum + **ed25519 signature** with a public key built into the app) before installing, keeps the previous version for one-click rollback, restarts itself, and tells me what changed in plain words. Reject unsigned/modified packs with a friendly message.
- Provide a script `make-update` and a short guide so that I can ask Claude Code, "make an update pack," and get a signed file. Also an optional "Check for updates" button (off by default).

## 9. Extras — you have my go-ahead (never at the cost of section 1)

Please add what a thoughtful product person would: channel profiles with templates ("Casanova limo", "what-if"); undo/version history; a safe "Preview in 5 seconds" mode; platform loudness and safe-zone presets; caption/title/hashtag/thumbnail generator (Haiku-class model to keep cost low); batch queue; automatic project backups; "Copy diagnostics" button for bug reports; plain-English error messages with a fix button; offline mode for everything except chat/search/posting; disk-space and cost warnings; an "Explain what the app just did" button; keyboard-free usage; large text option; and a built-in 2-minute tutorial using sample files. Keep the screen simple — advanced options hidden behind "More".

## 10. Suggested stack (change it if you have a better reason, and tell me why)

Electron + React + TypeScript; bundled `ffmpeg-static`/`ffprobe-static`; `onnxruntime-node` for vocal separation; `sherpa-onnx` (node) for the speech check; `sharp`/canvas for drawing and stills; SQLite or JSON for the library; `electron-builder` for the universal .dmg; Keychain via Electron `safeStorage`. Engine code must be separate from UI code and covered by automated tests (sync accuracy test: the punch-line voice onset and the music hit must be within ±1 frame at 30 fps; loudness test; reframe test for both ratios).

## 11. Phases (stop and show me after each)

1. **Skeleton + installer**: window, drop zone, format ticker, the "Double-click me first" DMG flow, first-run wizard. I can install it on a clean Mac.
2. **Audio brain**: vocal clean-up, phrase finder + transcript check, music hit alignment, mix. I can drop voice+music and hear a finished mix with the punch line on the hit.
3. **Edit-my-clip engine**: my Higgsfield video + that audio → synced 9:16 and 16:9 exports with slideshow cuts.
4. **Memory + chat + internet assets.**
5. **Draw-it engine** (my saved characters, limo/throne scenes).
6. **Scheduling/export for Buffer, YouTube, Facebook.**
7. **Drag-and-drop updates + polish + tutorial.**

## 12. Deliverables

The installable .dmg, a one-page "Start Here" guide for non-technical users, a short "How I (the owner) update this app with Claude Code" note, and a changelog. Test everything yourself (run the tests, render a real sample, look at frames) before telling me it works, and say honestly what is not finished.

Begin with Phase 1 now. First reply: your 5-line plan, the stack you chose, and anything you truly need from me.
