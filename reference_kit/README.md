# Punchline kit — reference for "the same great timing"

Read this folder BEFORE touching the app. It is the proven recipe that made `golden/casanova_cat_v1.mp4`.

| path | what it is |
|---|---|
| `.claude/skills/cartoon-short-voice-sync/SKILL.md` | The rules/skill. Claude Code loads it automatically from here. ALSO embed its text as the system prompt of the in-app chat/director. |
| `tools/audio_brain.py` | Tested reference for: vocal isolation call, phrase finder, unit grouping, punch placement with a 2.0 s pause, per-unit levelling, music alignment (chorus downbeat on the punch), cuts/SFX, ducking, loudness, self-checks, `timeline.json`. |
| `tools/mdx.py`, `tools/asr.py` | Vocal separation (UVR-MDX-NET-Voc_FT via onnxruntime) and Whisper sanity check. |
| `engine_reference/cat_core.py`, `cat_run.py` | The video side: shot list keyed to times, lip-sync from the voice-only file, cuts with white flash + blur + decaying shake, camera, sip, etc. Port the *ideas and numbers*, not the cat art. |
| `golden/casanova_cat_v1.mp4` | The finished reference video (A/B target). |
| `golden/timeline_expected.json` | Numbers the audio brain must reproduce for the golden inputs. |

## Golden case (inputs the owner already has)
Voice `Sol_Street_71.m4a`, music `money_mode_wil_intro.mp3` (bed) + `money_mode_wil_chorus_2.mp3` (from the punch line). Punch units = 2,3 (0-based) → "meron akong tyansa" … "(chance)".

Expected (tolerance in brackets): units = (1.35–2.93) (4.08–5.33) (6.37–6.87) (7.98–8.68); chorus downbeat lands on 8.24 s (±0.02); intro offset 1.18 s (±0.03); pause before punch 2.00 s (±0.05); cuts 9.24 10.24 11.24 12.44 13.44 14.54 15.64; voice over music ≥ 8 dB while speaking (reference ≈ 13 dB); −14…−16.5 LUFS (reference −15.5); peak ≤ −1 dBFS; length 18.0 s.

## The one idea that matters
**Measure the audio → build a timeline → render from the timeline → verify the numbers.** Never a fixed template, never a loop.
