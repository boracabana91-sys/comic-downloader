"""Find the live play in a sports broadcast.

Method (cheap, no AI, numpy only):
  * Watch the scoreboard clock digits. While the game clock runs, the digits change
    every second; during timeouts, free throws and dead balls they stay frozen.
  * Cut frozen stretches longer than `min_dead_s`, plus anything with no scoreboard.
  * If the result is still longer than `target_ratio` of the source, drop the least
    interesting live runs (quietest crowd, least motion) until it fits.
Clips always stay in game order at normal speed.
"""
from __future__ import annotations
import os
import sys
import tempfile
import numpy as np

from . import progress
from . import media

CLOCK_FPS = 2


def _extract(path: str, info: dict, roi, tmp: str):
    W, H = info["width"], info["height"]
    cw = max(8, int(W * roi[2]) // 2 * 2); ch = max(8, int(H * roi[3]) // 2 * 2)
    cx = int(W * roi[0]); cy = int(H * roi[1])
    clock = os.path.join(tmp, "clock.raw"); mot = os.path.join(tmp, "mot.raw"); aud = os.path.join(tmp, "aud.raw")
    def build(hw: bool):
        cmd = [media.need("ffmpeg"), "-v", "error", "-y"]
        if hw:
            cmd += ["-hwaccel", "videotoolbox"]                 # the Mac's decoder chip: much faster than the CPU
        cmd += ["-i", path,
                "-map", "0:v:0", "-vf", f"fps={CLOCK_FPS},crop={cw}:{ch}:{cx}:{cy},format=gray", "-f", "rawvideo", clock,
                "-map", "0:v:0", "-vf", "fps=1,scale=64:36,format=gray", "-f", "rawvideo", mot]
        if info["has_audio"]:
            cmd += ["-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "s16le", aud]
        return cmd

    on_pct = lambda p: progress.set("analysing the video", p)
    if sys.platform == "darwin":
        try:
            media.run_progress(build(True), info["duration"], on_pct)
        except RuntimeError:
            media.run_progress(build(False), info["duration"], on_pct)       # no hardware decode for this video
    else:
        media.run_progress(build(False), info["duration"], on_pct)
    clk = np.fromfile(clock, np.uint8).reshape(-1, ch * cw)
    m = np.fromfile(mot, np.uint8).reshape(-1, 36 * 64).astype(np.float32)
    a = np.fromfile(aud, np.int16).astype(np.float32) / 32768 if info["has_audio"] and os.path.exists(aud) else np.zeros(0, np.float32)
    return clk, m, a


def _runs(mask: np.ndarray):
    out, s = [], None
    for i, v in enumerate(mask):
        if v and s is None:
            s = i
        elif not v and s is not None:
            out.append([s, i]); s = None
    if s is not None:
        out.append([s, len(mask)])
    return out


def live_mask(clk: np.ndarray, secs: int, min_dead_s: float) -> np.ndarray:
    """Per-second boolean: True where the scoreboard is present and its clock is running."""
    M = clk > 150
    white = M.mean(1)
    dark = (clk < 70).mean(1)
    present = (white > 0.03) & (white < 0.45) & (dark > 0.25)
    n = len(clk)
    change = np.zeros(n)
    change[:n - 2] = (M[:-2] ^ M[2:]).mean(1)
    tick = np.zeros(secs, bool); pres = np.zeros(secs, bool)
    for s in range(secs):
        a, b = s * CLOCK_FPS, min(n, s * CLOCK_FPS + CLOCK_FPS)
        if a >= n:
            break
        tick[s] = (change[a:b] > 0.02).any()
        pres[s] = present[a:b].mean() > 0.5
    live = tick & pres
    # a short frozen gap is normal (digit flicker, tenths) - only gaps > min_dead_s are cut
    gap = max(1, int(round(min_dead_s)))
    for r in _runs(~live):
        if r[1] - r[0] <= gap and r[0] > 0 and r[1] < secs:
            live[r[0]:r[1]] = True
    return live


def _chunk(segs, motion, min_len, max_len):
    """Split long live runs at the strongest camera cuts so clips can be ranked and dropped one by one."""
    out, todo = [], [list(s) for s in segs]
    while todo:
        a, b = todo.pop(0)
        if b - a <= max_len:
            out.append([a, b]); continue
        lo, hi = int(a + min_len), int(b - min_len)
        if hi <= lo or len(motion) <= hi:
            out.append([a, b]); continue
        mid = (a + b) / 2
        cut = max(range(lo, hi + 1), key=lambda t: motion[t] - 0.02 * abs(t - mid))
        todo = [[a, float(cut)], [float(cut), b]] + todo
    return sorted(out)


def _even_drop(segs: list, loud_z: np.ndarray, target: float) -> list:
    """Highlights: shorten to the target by dropping whole chunks of play, spread evenly through the game
    (what the reference reclip does). Never dropped: the tip-off chunk, the last 2 minutes of play, and
    any chunk holding one of the loudest crowd moments. Returns the indices of the chunks kept, in order."""
    n = len(segs)
    if n < 3:
        return list(range(n))
    length = [b - a for a, b in segs]
    center = [(a + b) / 2 for a, b in segs]
    end = segs[-1][1]
    live_secs = np.concatenate([np.arange(int(a), int(b)) for a, b in segs])
    live_secs = live_secs[live_secs < len(loud_z)]
    thr = np.quantile(loud_z[live_secs], 0.98) if len(live_secs) else np.inf
    protect = {0}
    for i, (a, b) in enumerate(segs):
        if b > end - 120:
            protect.add(i)
        sl = loud_z[int(a):int(b)]
        if len(sl) and sl.max() > thr:
            protect.add(i)
    cur = sum(length)
    dropped: list = []
    while cur > target * 1.01:
        avail = [i for i in range(n) if i not in protect and i not in dropped and cur - length[i] >= target * 0.95]
        apart = [i for i in avail if i - 1 not in dropped and i + 1 not in dropped]   # no back-to-back drops
        avail = apart or avail
        if not avail:
            break
        k = len(dropped) + max(1, round((cur - target) / (sum(length[i] for i in avail) / len(avail))))
        span_a, span_b = segs[0][0], end
        slots = [span_a + (j + 0.5) * (span_b - span_a) / k for j in range(k)]
        pos = max(slots, key=lambda p: min([abs(p - center[d]) for d in dropped] or [1e9]))
        i = min(avail, key=lambda i: abs(center[i] - pos))
        dropped.append(i)
        cur -= length[i]
    return [i for i in range(n) if i not in dropped]


def plan(path: str, cfg: dict, log=print) -> dict:
    progress.set("analysing the video")
    info = media.probe(path)
    m, s = divmod(int(info["duration"]), 60)
    log(f"video: {info['width']}x{info['height']}, {info['codec']}, {m}:{s:02d} long")
    secs = int(info["duration"])
    with tempfile.TemporaryDirectory() as tmp:
        clk, mot, aud = _extract(path, info, cfg["clock_roi"], tmp)
    secs = min(secs, len(clk) // CLOCK_FPS)
    live = live_mask(clk, secs, cfg["min_dead_s"])
    hl = bool(cfg.get("highlights"))
    if hl:
        # highlights: short gaps in the scoreboard read are kept as play
        for r in _runs(~live):
            if r[1] - r[0] <= 8 and r[0] > 0 and r[1] < secs:
                live[r[0]:r[1]] = True
        # start a few seconds before tip-off (first stretch of running clock), like the reference reclip
        tip = next((a for a, b in _runs(live) if b - a >= 20), None)     # 20 s of running clock = game on
        if tip is not None:
            lead = int(cfg.get("highlight_lead_s", 3))
            live[:tip] = False
            live[max(0, tip - lead):tip] = True
    else:
        live[: int(cfg.get("trim_start_s", 0))] = False
    pad = cfg["pad_s"]
    segs = [[max(0.0, a - pad), min(float(secs), b + pad)] for a, b in _runs(live)]
    merged: list = []
    for s in segs:                      # padding can make neighbours overlap
        if merged and s[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], s[1])
        else:
            merged.append(s)
    segs = [s for s in merged if s[1] - s[0] >= cfg["min_clip_s"]]
    after_dead = sum(b - a for a, b in segs)
    motion = np.r_[0, np.abs(np.diff(mot, axis=0)).mean(1)] if len(mot) > 1 else np.zeros(secs)
    if hl:      # possession-sized chunks (12-45 s), split at camera cuts, so whole stretches can be dropped
        segs = _chunk(segs, motion, max(12, cfg["min_clip_s"]), cfg.get("highlight_chunk_s", 45))
    else:
        segs = _chunk(segs, motion, cfg["min_clip_s"], cfg.get("max_clip_s", 30))

    # interest per segment: crowd loudness + motion, z-scored over the whole video
    rms = np.sqrt((aud[: len(aud) // 8000 * 8000].reshape(-1, 8000) ** 2).mean(1)) if len(aud) >= 8000 else np.zeros(secs)
    z = lambda x: (x - x.mean()) / (x.std() + 1e-6)
    rz, mz = z(rms), z(motion)

    def interest(seg):
        a, b = int(seg[0]), max(int(seg[0]) + 1, int(seg[1]))
        r = rz[a:b] if len(rz) >= b else np.zeros(1); m = mz[a:b] if len(mz) >= b else np.zeros(1)
        return float(r.max() * 0.6 + m.mean() * 0.4)

    total = info["duration"]
    target = cfg["target_ratio"] * total
    kept = list(range(len(segs)))
    if hl and target > 0 and after_dead > target:
        kept = _even_drop(segs, rz, target)
    elif not hl and target > 0 and after_dead > target:
        order = sorted(kept, key=lambda i: interest(segs[i]))
        cur = sum(b - a for a, b in segs)
        for i in order:
            if cur <= target:
                break
            length = segs[i][1] - segs[i][0]
            if cur - length < target * 0.9:      # never overshoot far below the target
                continue
            kept.remove(i)
            cur -= length
    final = [segs[i] for i in sorted(kept)]
    kept_s = sum(b - a for a, b in final)
    log(("highlights mode - " if hl else "") + f"analysis: {total:.0f}s source -> live play {after_dead:.0f}s -> final {kept_s:.0f}s "
        f"({kept_s / total:.0%}) in {len(final)} clips")
    return {"info": info, "segments": final, "kept_s": kept_s, "source_s": total, "after_dead_s": after_dead}
