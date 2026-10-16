"""Find the live play in a sports broadcast.

Method (cheap, no AI, numpy only):
  * Watch the scoreboard clock digits. While the game clock runs, the digits change
    every second; during timeouts, free throws and dead balls they stay frozen.
  * Cut frozen stretches longer than `min_dead_s`, plus anything with no scoreboard.
  * If the result is longer than your maximum minutes, drop the least interesting stretches until it fits;
    if it is shorter than your minimum (or the clock could not be read) add the most active stretches back.
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


def live_mask(clk: np.ndarray, secs: int, min_dead_s: float, want_pres: bool = False):
    """Per-second boolean: True where the scoreboard is present and its clock is running.
    With want_pres=True returns (live, scoreboard_present) so the caller can tell 'no play' from 'clock not readable'."""
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
    return (live, pres) if want_pres else live


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


def lengths(cfg: dict) -> tuple:
    """(min seconds, max seconds) the finished clip should be. Minutes in the settings; max is never below min."""
    lo = max(0.5, float(cfg.get("min_minutes", 8))) * 60
    hi = max(lo, float(cfg.get("max_minutes", 12)) * 60)
    return lo, hi


def game_end(runs: list, tail_gap_s: float = 120, noise_s: float = 15) -> float:
    """Second at which the game itself ends: the end of the last running-clock stretch. A short, lonely stretch
    far after the others (the scoreboard flickering back during the interview) is not counted. runs = [[a, b], ...]"""
    runs = [list(r) for r in runs]
    while len(runs) > 1 and runs[-1][1] - runs[-1][0] < noise_s and runs[-1][0] - runs[-2][1] > tail_gap_s:
        runs.pop()
    return float(runs[-1][1]) if runs else 0.0


def _top_up(final: list, secs: int, motion: np.ndarray, interest, min_s: float, max_s: float,
            end_s: float | None = None) -> list:
    """The clip came out shorter than the minimum: add back whole stretches from the parts that were cut,
    most interesting first (crowd noise + motion), until the minimum is reached. Still in game order.
    vv13: nothing after `end_s` (the end of the game) is added back, so the post-game interview stays out."""
    end_s = float(secs) if end_s is None else float(min(end_s, secs))
    gaps, t = [], 0.0
    for a, b in sorted(final) + [[end_s, end_s]]:
        if a - t >= 10:
            gaps.append([t, a])
        t = max(t, b)
    cands = _chunk(gaps, motion, 12, 30)
    cur = sum(b - a for a, b in final)
    chosen = []
    for seg in sorted(cands, key=interest, reverse=True):
        if cur >= min_s:
            break
        length = seg[1] - seg[0]
        if length < 6 or cur + length > max_s * 1.02:
            continue
        chosen.append(seg)
        cur += length
    out = sorted([list(x) for x in final] + chosen)
    merged: list = []
    for a, b in out:
        if merged and a <= merged[-1][1] + 0.01:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def plan(path: str, cfg: dict, log=print) -> dict:
    progress.set("analysing the video")
    info = media.probe(path)
    m, s = divmod(int(info["duration"]), 60)
    log(f"video: {info['width']}x{info['height']}, {info['codec']}, {m}:{s:02d} long")
    secs = int(info["duration"])
    with tempfile.TemporaryDirectory() as tmp:
        clk, mot, aud = _extract(path, info, cfg["clock_roi"], tmp)
    secs = min(secs, len(clk) // CLOCK_FPS)
    total = info["duration"]
    min_s, max_s = lengths(cfg)
    if total <= min_s:                                  # the source is already as short as you want
        log(f"the video is only {total:.0f}s - shorter than your minimum, so all of it is kept")
        return {"info": info, "segments": [[0.0, float(total)]], "kept_s": float(total), "source_s": total,
                "after_dead_s": float(total)}
    live, pres = live_mask(clk, secs, cfg["min_dead_s"], want_pres=True)
    seen = float(pres.mean()) if secs else 0.0
    log(f"scoreboard clock readable in {seen:.0%} of the video, running in {live.mean():.0%} of it")
    if seen < 0.30 or live.sum() < 0.12 * secs:
        # the clock was not found (different broadcast layout): do NOT trust it - choose by activity instead
        log("WARNING: could not read the scoreboard clock on this video - picking the most active stretches by motion and crowd sound "
            "instead (set clock_roi in config.json to the clock's position for better dead-time cuts)")
        live[:] = True
        clock_ok = False
    else:
        clock_ok = True
    # vv13: the post-game interview is cut unless "Include post-game interview" is ticked
    end_s = float(secs)
    interview_cut = 0.0
    if not cfg.get("include_interview", False) and secs > 120:
        if clock_ok:
            runs = _runs(live)
            if runs:
                end_s = min(float(secs), game_end(runs) + 20)
        else:                                             # no clock to tell where the game ends: drop the last few percent
            end_s = secs - min(0.06 * secs, 180.0)
        if end_s < secs:
            live[int(end_s):] = False
            interview_cut = secs - end_s
            log(f"post-game: the last {interview_cut / 60:.1f} min of the video (after the final play) is left out "
                f"- tick 'Include post-game interview' to keep it")
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

    kept = list(range(len(segs)))
    cur = sum(b - a for a, b in segs)
    if cur > max_s:                                     # too long: drop whole stretches down to your maximum
        if hl:
            kept = _even_drop(segs, rz, max_s)
        else:
            order = sorted(kept, key=lambda i: interest(segs[i]))
            for i in order:
                if cur <= max_s:
                    break
                length = segs[i][1] - segs[i][0]
                if cur - length < max_s * 0.9:
                    continue
                kept.remove(i)
                cur -= length
        cur = sum(segs[i][1] - segs[i][0] for i in kept)
        if cur > max_s * 1.15:                          # protected stretches blocked the even drop: trim the dullest
            for i in sorted(kept, key=lambda i: interest(segs[i])):
                if cur <= max_s * 1.05:
                    break
                kept.remove(i)
                cur -= segs[i][1] - segs[i][0]
    final = [segs[i] for i in sorted(kept)]
    kept_s = sum(b - a for a, b in final)
    if kept_s < min_s * 0.97:                           # too short to follow: add the most active stretches that were cut
        final = _top_up(final, secs, motion, interest, min_s, max_s, end_s)
        kept_s = sum(b - a for a, b in final)
    log(("highlights mode - " if hl else "") + f"analysis: {total:.0f}s source -> live play {after_dead:.0f}s -> final {kept_s:.0f}s "
        f"({kept_s / 60:.1f} min; you asked for {min_s / 60:.0f}-{max_s / 60:.0f} min) in {len(final)} clips")
    if kept_s < min_s * 0.9:
        log(f"note: only {kept_s / 60:.1f} min could be kept - the rest of the video had no activity worth keeping")
    return {"info": info, "segments": final, "kept_s": kept_s, "source_s": total, "after_dead_s": after_dead,
            "game_end_s": end_s, "interview_cut_s": interview_cut}
