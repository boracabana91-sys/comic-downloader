# What's new in Cattyfied

## v0.5 (the reference timing: "measure → timeline → render → verify")
- New: **music removal from your voice** (the same AI model the reference uses). It downloads once, 67 MB, with a progress bar. If your voice file has music in it, the timing and mouth now follow your voice only. Apple Silicon Macs only for now.
- New: your voice is split into **parts** (a pause of 0.9 s or more starts a new part). You tick which parts are the punch line, and it can be more than one.
- New timing, exactly like your reference video:
  - the punch line starts at 8.24 s, after a 2.0 s pause with music only;
  - the punch-line music's first beat lands exactly on it, and the intro ends exactly where that music starts;
  - the punch line is never the quietest part.
- New animation, exactly like your reference:
  - it opens close on the champagne, pulls back to reveal the cat, and he sips during the pause;
  - a white flash on the punch line, then cuts at +1.0, 2.0, 3.0, 4.2, 5.2, 6.3, 7.4 s, each with flash, blur and shake;
  - a different close-up each time (wink, grin, eyebrows, smug look, laugh), and it ends on a flirty smirk;
  - hearts only at the very end, and no more repeating loop;
  - the mouth moves only with your voice and is closed when you're silent.
- New: **preflight check** on every finished video:
  - flashes on every cut, no loop, mouth closed in the silences;
  - the beat on the punch line, the pause, the loudness, the peak and the length;
  - red means "not ready", and it's never hidden.
- Kept: the hand timeline editor (waveforms, drag, trim, drop files) for files the automatic part gets wrong.
- Fixed: the whole soundtrack was 10 ms late (limiter delay), and the cleaned voice was 6 dB too loud.

## v0.4.1 (much smaller, faster download)
- One installer per Mac type instead of one big combined installer, so you download only what your Mac needs (about 2.5× smaller).
- Removed a video tool the app didn't need, and the installer is packed tighter.
- Two separate downloads now: pick the one for your Mac.

## v0.4 (fix the timing by hand)
- Automatic sync is still the default. Nothing changes unless you open the new section.
- New: **"Fix the timing by hand"** on the Check timing screen, a timeline like a video editor:
  - your voice and music shown as waveforms, the punch line as a red line, music hits as yellow marks
  - drag the music to move it; drag its edges to choose exactly where it starts and ends
  - drop any music or video file (mp3, m4a, wav, mp4…) onto the timeline at the spot where it should start
  - exact numbers, plus −1 frame / −10 ms / +10 ms / +1 frame buttons
  - "Put its hit on the punch line", snapping, and "Move all music together" (on by default)
  - ▶ instant preview while you edit; "Use this timing" makes the real mix and checks it
  - "Back to automatic" undoes your edits
- Your hand placement stays locked to the punch line if you change the pause.

## v0.3 (the cat moves!)
- New: **Animated Casanova cat**, drawn from your reference picture (limo, tux, champagne, tail). It's now the default look.
- His mouth moves with your voice, and he blinks and looks around.
- The camera does what your reference video does: one smooth push-in until the punch line, then a hard cut every second with a white flash, blur and shake. The close-ups switch between a wink with a laugh and hearts, a raised eyebrow, a smug eye close-up, a champagne toast, and the other wink.
- New: a whoosh sound into each cut. The thump stays on the punch line.
- New: you can still choose your own video clip or picture instead.

## v0.2 (first draft that makes videos)
- New: **Check timing**. Drop your voice and music, and Cattyfied finds the parts of your voice, guesses the punch line (you confirm it by listening), finds the music's hit, and lines them up exactly. Press play to hear it before anything is made.
- New: intro + punch-line music. The intro's hit lands exactly on your punch line, and the punch-line music starts right where the intro ends.
- New: a pause slider before the punch line (default 2 s). The music keeps playing through it.
- New: your voice is kept about 8 dB above the music, and the loudness is set for YouTube, Facebook and Reels.
- New: **Make my video**. Shorts/Reels (tall) or YouTube/Facebook (wide), with a zoom, shake and flash right on the punch line. It uses your video clip or picture.
- New: after every video, Cattyfied re-checks the finished file and shows green or red results.
- Fixed: iPhone photos (HEIC) no longer come out sideways.
- Music tag "Chorus" is now called "Punch line".

## v0.1 (first test version)
- New: the Cattyfied window with a big "Drop everything here" box. Cattyfied labels your files and asks when it isn't sure.
- New: switch between Shorts/Reels (tall) and YouTube/Facebook (wide).
- New: a 4-step welcome setup (Anthropic key, channel).
- New: the version number in the top-right corner.
- Not yet: making videos (next update).
