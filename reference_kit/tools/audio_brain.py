#!/usr/bin/env python3
"""
audio_brain.py - REFERENCE implementation of the punch-line timing + mix that produced the "great timing".
Port this logic faithfully (any language). Do not "simplify" it: every step exists because a video went wrong without it.

  python3 audio_brain.py --voice Sol_Street_71.m4a --intro intro.mp3 --chorus chorus_2.mp3 \
      --punch-units 2,3 --out out_dir --model UVR-MDX-NET-Voc_FT.onnx --mdx mdx.py

Outputs in --out:  vo.wav (voice only, placed on the timeline - drive the mouth from THIS file, never from the mix)
                   mix_final.wav (what goes under the video)   timeline.json (every time the video engine needs)
"""
import argparse, json, os, re, subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 44100

def sh(cmd): subprocess.run(cmd, shell=True, check=True)
def rd(f):
    sr, a = wavfile.read(f); assert sr == SR, (f, sr)
    return a.astype(np.float64) / 32768.0
def wr(f, x, scale=1.0): wavfile.write(f, SR, (np.clip(x * scale, -1, 1) * 32767).astype(np.int16))
def to_wav(src, dst, ch):  sh(f"ffmpeg -v error -y -i '{src}' -ar {SR} -ac {ch} '{dst}'")

# ---------------------------------------------------------------- 1. voice: isolate, clean
CLEAN = ("highpass=f=85,lowpass=f=10500,afftdn=nr=12:nf=-45,agate=threshold=0.008:ratio=3:attack=4:release=120,"
         "equalizer=f=220:t=q:w=1:g=1.5,equalizer=f=3000:t=q:w=1.2:g=2.5,"
         "acompressor=threshold=0.05:ratio=3:attack=5:release=90:makeup=2,loudnorm=I=-13:TP=-1.5")

# ---------------------------------------------------------------- 2. phrases -> units
def find_phrases(voc, thr_db=-38.0, min_gap=0.18, min_len=0.06):
    """Same result as ffmpeg silencedetect=noise=-38dB:d=0.18 on the ISOLATED stem (before loudnorm)."""
    mono = np.abs(voc).max(axis=1) if voc.ndim > 1 else np.abs(voc)
    hop = int(0.01 * SR); n = len(mono) // hop
    peak = mono[: n * hop].reshape(n, hop).max(axis=1)
    act = peak >= 10 ** (thr_db / 20)
    segs, i = [], 0
    while i < n:
        if act[i]:
            j = i
            while j < n and act[j]: j += 1
            segs.append([i * 0.01, j * 0.01]); i = j
        else: i += 1
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < min_gap: merged[-1][1] = s[1]
        else: merged.append(s)
    return [tuple(s) for s in merged if s[1] - s[0] >= min_len]

def group_units(phrases, unit_gap=0.9):
    """A 'unit' = words said together. A gap of >= 0.9 s is a deliberate pause between units."""
    units = []
    for p in phrases:
        if units and p[0] - units[-1][1] < unit_gap: units[-1] = (units[-1][0], p[1])
        else: units.append(p)
    return units

# ---------------------------------------------------------------- 3. music
def first_downbeat(chorus, search=0.5):
    """Time (s) of the strongest rise in the first `search` s of the chorus file = its first downbeat (~0.10 s for money_mode_wil_chorus_2)."""
    a = chorus.mean(axis=1) if chorus.ndim > 1 else chorus
    h = int(0.01 * SR); n = int(search * SR) // h
    r = np.array([np.sqrt(np.mean(a[i * h:i * h + 2 * h] ** 2)) for i in range(n)])
    return (np.argmax(np.diff(r)) + 1) * 0.01

def whoosh(dur, peak, seed=3):
    n = int(SR * dur); x = np.random.default_rng(seed).standard_normal(n)
    x = sosfilt(butter(2, [500, 6000], btype="band", fs=SR, output="sos"), x) * np.linspace(0, 1, n) ** 2.2
    return x / np.abs(x).max() * peak
def impact(peak, seed=5):
    n = int(SR * 0.7); t = np.arange(n) / SR
    thump = np.sin(2 * np.pi * (48 + 60 * np.exp(-t * 18)) * t) * np.exp(-t * 7)
    snap = np.random.default_rng(seed).standard_normal(n) * np.exp(-t * 40) * 0.3
    return (thump + snap) / 1.3 * peak

def lufs(path):
    out = subprocess.run(f"ffmpeg -hide_banner -i '{path}' -af ebur128=peak=true -f null - 2>&1", shell=True, capture_output=True, text=True).stdout
    I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1]); pk = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", out)[-1])
    return I, pk

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True); ap.add_argument("--intro", required=True); ap.add_argument("--chorus", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--model", required=True); ap.add_argument("--mdx", required=True)
    ap.add_argument("--punch-time", type=float, default=8.24)       # the music downbeat / start of the punch line
    ap.add_argument("--pause", type=float, default=2.0)             # silence (music keeps running) before the punch line
    ap.add_argument("--duration", type=float, default=18.0)
    ap.add_argument("--punch-units", default="")                   # e.g. "2,3"; default = LAST unit. THE USER MUST CONFIRM THIS.
    ap.add_argument("--target-lufs", type=float, default=-15.5)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); O = lambda f: os.path.join(a.out, f)
    N = int(SR * a.duration)

    # --- voice
    to_wav(a.voice, O("voice44.wav"), 2); sh(f"python3 '{a.mdx}' '{a.model}' '{O('voice44.wav')}' '{O('voc.wav')}'")
    voc = rd(O("voc.wav")); phrases = find_phrases(voc); units = group_units(phrases)
    sh(f"ffmpeg -v error -y -i '{O('voc.wav')}' -ar {SR} -ac 1 -af '{CLEAN}' '{O('voc_clean.wav')}'")
    v = rd(O("voc_clean.wav")); v = v.mean(axis=1) if v.ndim > 1 else v
    pu = [int(x) for x in a.punch_units.split(",")] if a.punch_units else [len(units) - 1]
    pre = [i for i in range(len(units)) if i < min(pu)]
    assert pre, "need at least one unit before the punch line"
    # --- levels: bring every unit to the average level of the pre-punch units (cap +6 dB) so the punch is never the quietest
    rms = lambda s0, s1: np.sqrt(np.mean(v[int(s0 * SR):int(s1 * SR)] ** 2) + 1e-12)
    target = np.mean([rms(*units[i]) for i in pre])
    # --- placement: punch unit starts exactly on punch-time; pre-punch units keep their natural gaps and end `pause` s before it
    prms = np.sqrt(np.mean([rms(*units[i]) ** 2 for i in pu]))
    shift_pre = (a.punch_time - a.pause) - units[max(pre)][1]
    shift_punch = a.punch_time - units[min(pu)][0]
    placed = []; vo = np.zeros(N)
    for i, (s0, s1) in enumerate(units):
        if i in pu: sh_, g = shift_punch, min(2.0, max(1.0, target / prms))
        elif i in pre: sh_, g = shift_pre, 1.0
        else: continue
        p0, p1 = max(0, s0 - 0.05), s1 + 0.05
        seg = v[int(p0 * SR):int(p1 * SR)].copy() * g; f = int(0.015 * SR); seg[:f] *= np.linspace(0, 1, f); seg[-f:] *= np.linspace(1, 0, f)
        o = int((p0 + sh_) * SR); vo[o:o + len(seg)] += seg[:max(0, N - o)] if o + len(seg) > N else seg
        placed.append(dict(unit=i, src=[s0, s1], dest=[s0 + sh_, s1 + sh_], gain=round(g, 3)))
    wr(O("vo.wav"), vo, 0.95 / max(np.abs(vo).max(), 1e-9))

    # --- music: chorus downbeat lands ON the punch time; intro is trimmed so it ends exactly where the chorus starts
    intro = rd(a.intro); ch = rd(a.chorus)
    db = first_downbeat(ch); chorus_start = a.punch_time - db
    while len(intro) / SR < chorus_start + 0.01:           # stutter edit: repeat the last 2 s to lengthen the bed
        seg = intro[-2 * SR:]; intro = np.concatenate([intro, seg])
    intro_offset = len(intro) / SR - chorus_start
    mus = np.zeros((N, 2)); seg = intro[int(intro_offset * SR):]; L = min(len(seg), N); mus[:L] += seg[:L]
    mus[:int(0.35 * SR)] *= np.linspace(0, 1, int(0.35 * SR))[:, None]
    c0 = int(chorus_start * SR); cs = ch[:N - c0]; mus[c0:c0 + len(cs)] += cs
    fo = int(1.9 * SR); mus[-fo:] *= np.linspace(1, 0, fo)[:, None]

    # --- cuts + sfx
    cuts = [round(a.punch_time + d, 2) for d in (1.0, 2.0, 3.0, 4.2, 5.2, 6.3, 7.4) if a.punch_time + d < a.duration - 0.5]
    sfx = np.zeros(N)
    def put(x, at):
        o = int(at * SR); L = min(len(x), N - o); sfx[o:o + L] += x[:L]
    put(impact(0.55), a.punch_time)
    for c in cuts: put(whoosh(0.28, 0.22), c - 0.28); put(impact(0.22)[:int(SR * 0.35)], c)

    # --- mix: music ducked 50% by the voice envelope, voice x1.45, then loudness to target
    env = np.convolve(np.abs(vo), np.ones(int(0.06 * SR)) / int(0.06 * SR), "same")
    env = np.convolve(np.minimum(env / 0.12, 1), np.ones(int(0.25 * SR)) / int(0.25 * SR), "same")
    M = mus * 0.85 * (1 - 0.50 * env)[:, None]; V = np.stack([vo, vo], 1) * 1.45
    mix = M + V + np.stack([sfx, sfx], 1) * 0.9
    pk = np.abs(mix).max(); mix *= 0.93 / pk if pk > 0.93 else 1
    wr(O("mix_raw.wav"), mix)
    gain = 0.0
    for _ in range(3):                                       # loudness: measure, correct, limit (loudnorm alone undershoots short clips)
        sh(f"ffmpeg -v error -y -i '{O('mix_raw.wav')}' -af 'volume={gain}dB,alimiter=limit=0.8:level=disabled' '{O('mix_final.wav')}'")
        I, peak = lufs(O("mix_final.wav")); gain += a.target_lufs - I
    # --- self-checks (print them; a failed check must be shown to the user, never hidden)
    act = np.convolve(np.abs(vo), np.ones(int(0.05 * SR)) / int(0.05 * SR), "same") > 0.02
    vdb = 20 * np.log10(np.sqrt(np.mean(V[act, 0] ** 2)) + 1e-9); mdb = 20 * np.log10(np.sqrt(np.mean(M[act, 0] ** 2)) + 1e-9)
    onset = np.argmax(np.abs(vo[int((a.punch_time - 0.3) * SR):]) > 0.01) / SR + a.punch_time - 0.3
    gap_before = a.punch_time - max(d["dest"][1] for d in placed if d["unit"] in pre)
    tl = dict(punch_time=a.punch_time, units=units, punch_units=pu, placed=placed, chorus_start=round(chorus_start, 3), chorus_downbeat=round(db, 3),
              intro_offset=round(intro_offset, 3), cuts=cuts, duration=a.duration, lufs=I, peak_dbfs=peak, voice_over_music_db=round(vdb - mdb, 1),
              voice_onset=round(onset, 3), pause_before_punch=round(gap_before, 2))
    json.dump(tl, open(O("timeline.json"), "w"), indent=1)
    print(json.dumps({k: tl[k] for k in ("chorus_start", "intro_offset", "cuts", "lufs", "peak_dbfs", "voice_over_music_db", "voice_onset", "pause_before_punch")}, indent=1))
    print("units:", [(round(s, 2), round(e, 2)) for s, e in units])

if __name__ == "__main__": main()
