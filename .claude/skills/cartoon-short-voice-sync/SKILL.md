---
name: "cartoon-short-voice-sync"
description: "Build a lip-synced cartoon YouTube Short from a voiceover and music: clean the voice, time the punch line to a music hit, mix, and animate to the audio."
---

# Cartoon Short: voice, music and animation sync

Use this when the user gives a voiceover (often with background music baked in), one or more music files, and wants a vertical (9:16) cartoon short whose mouth, camera and cuts are timed to the audio, especially to a punch line.

## 0. Ground rules learned the hard way
- Never trust a guess about what the voice says. Transcribe it, and if the transcript does not match the line the user gave, STOP and ask which phrase is the punch line.
- The sandbox blocks cloud TTS (Edge, Hugging Face). Ask the user for a voice file (ElevenLabs etc.). GitHub release downloads usually work.
- Do not run `pkill -f <name>` from a command line that itself contains `<name>` (it kills its own shell, exit 144). Use `pkill -f "[n]ame"` in a command by itself.
- Show a still of the character and get approval before building an animation.
- Say plainly that code-drawn vector animation looks stiffer than hand-animated cartoons; the biggest quality jump is clean layered character art from the user.

## 1. Clean the voice (vocal isolation)
1. Convert input to 44.1 kHz stereo wav with ffmpeg.
2. Download the MDX vocal model from GitHub releases: `https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Voc_FT.onnx` (about 67 MB). `pip install onnxruntime`.
3. Run it in plain numpy + onnxruntime (no torch): n_fft=7680, hop=1024, dim_f=3072, dim_t=256, chunk=hop*(dim_t-1); hann window; STFT each chunk with reflect padding, feed `[1,4,3072,256]` (real/imag of both channels), take output, zero-pad bins 3072..3840, inverse STFT with overlap-add and window-square normalisation, trim n_fft/2 from each chunk edge, multiply by 1.021.
4. Post-process the stem with ffmpeg: `highpass=85, lowpass=10500, afftdn=nr=12:nf=-45, agate=threshold=0.008:ratio=3:attack=4:release=120, equalizer=f=220:g=1.5, equalizer=f=3000:g=2.5, acompressor=threshold=0.05:ratio=3:makeup=2, loudnorm=I=-13:TP=-1.5`.

## 2. Find phrases and check the words
- `ffmpeg -af silencedetect=noise=-38dB:d=0.18` on the vocal stem gives phrase start/end times.
- Transcribe with sherpa-onnx Whisper (small, language `tl` for Tagalog): `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-small.tar.bz2`. Whisper-small is unreliable on Tagalog; use it only as a sanity check.
- Cut each phrase with about 50 ms of padding and 15 ms fades, then re-place the phrases on a silent timeline at the wanted times (long pause before the punch line is a feature, music keeps running).

## 3. Music alignment
- Compute a 50 ms RMS envelope; find hits with the biggest ratio of mean(next 3-7 frames) over mean(previous 8-2 frames). Autocorrelate the onset envelope for tempo.
- Shift or trim the music so a hit lands exactly on the punch line. Intro files often end with a silent dip then a hit that hands off to the chorus: start the intro at an offset so that hit lands on the punch line and start the chorus where the intro ends.
- To lengthen a bed, repeat the 2 s before the cut point (stutter edit) so the hit moves by exactly 2 s.

## 4. Mix
- Music bed about 0.85 gain, ducked 40% by a smoothed voice envelope (60 ms RMS, 250 ms smoothing). Voice about 1.45 gain. Target: voice about 8 dB above music while speaking, never drowning it.
- Subtle SFX only: sub thump (sine 48 Hz + 60 Hz sweep, decay 7/s) on the punch line, band-passed noise whoosh (0.28 s, quadratic rise) ending on each cut.
- Normalise to about -14..-16 LUFS with `volume` + `alimiter=limit=0.8:level=disabled`; verify peak below -1 dBFS with `ebur128=peak=true`. The `loudnorm` filter alone undershoots on short clips.

## 5. Animate to the audio
- Lip-sync from the voice-only track: per-frame RMS envelope with fast attack (0.7) and slow release (0.35); mouth width from the spectral centroid. Mouth must be symmetric; asymmetry only through an explicit smirk parameter.
- Camera and states come from a director shot list (JSON of keyframes: zoom, fx, fy, roll, tilt, shades, lid, wink, brow, smirk, grin, blush, look, hearts). Interpolate with scipy PCHIP per shot so speed never drops to zero between keys (per-segment smoothstep stutters).
- Rendering: 30 fps, 2x supersample, 3 temporal subsamples for motion blur (shutter about 1/3 frame).
- Slideshow cuts: hard cut + 3-frame white flash + gaussian blur on the frames around each cut (radius 3, 7, 11, 7, 3.5, 1.5) + handheld shake that decays after each cut.
- 3D props (e.g. a throne): build faces as 3D quads, rotate about the vertical axis, mild perspective plus a pitch term so top faces show, cull back faces, painter's sort by depth against a sprite character at depth 0. Character turning width: sqrt(cos^2 + (0.66 sin)^2).
- Seated character: lower the seat, bend the legs (thigh, knee, shin), keep the set behind him in every shot.
- Check frames at the key moments (first frame, punch-line frame, each take) before the full render, and render long jobs in the background.