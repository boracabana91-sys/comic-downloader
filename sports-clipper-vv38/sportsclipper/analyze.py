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
END_PAD_S = 2          # vv26: the clip ends this many seconds after the game ends (the final score), so no end credits show. Overtime keeps the clock running, so it stays in.
TH_W, TH_H, TH_SECS = 128, 72, 4 * 3600  # vv18/19: one small picture per second (up to 4 h): finds the score bug, i.e. where the game starts and ends


def _extract(path: str, info: dict, roi, tmp: str):
    W, H = info["width"], info["height"]
    cw = max(8, int(W * roi[2]) // 2 * 2); ch = max(8, int(H * roi[3]) // 2 * 2)
    cx = int(W * roi[0]); cy = int(H * roi[1])
    clock = os.path.join(tmp, "clock.raw"); mot = os.path.join(tmp, "mot.raw"); aud = os.path.join(tmp, "aud.raw")
    thumb = os.path.join(tmp, "thumb.raw")
    def build(hw: bool):
        cmd = [media.need("ffmpeg"), "-v", "error", "-y"]
        if hw:
            cmd += ["-hwaccel", "videotoolbox"]                 # the Mac's decoder chip: much faster than the CPU
        cmd += ["-i", path,
                "-map", "0:v:0", "-vf", f"fps={CLOCK_FPS},crop={cw}:{ch}:{cx}:{cy},format=gray", "-f", "rawvideo", clock,
                "-map", "0:v:0", "-vf", "fps=1,scale=64:36,format=gray", "-f", "rawvideo", mot,
                # vv18/19: the whole video as 128x72 pictures, to find the scoreboard BUG wherever it sits (jump ball and final buzzer)
                "-map", "0:v:0", "-vf", f"fps=1,scale={TH_W}:{TH_H},format=gray", "-t", str(TH_SECS), "-f", "rawvideo", thumb]
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
    th = np.fromfile(thumb, np.uint8) if os.path.exists(thumb) else np.zeros(0, np.uint8)
    th = th[: len(th) // (TH_W * TH_H) * TH_W * TH_H].reshape(-1, TH_H, TH_W)
    return clk, m, a, th


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


def tipoff(live: np.ndarray, min_run_s: int = 20):
    """Second the jump ball happens: the start of the first stretch of at least `min_run_s` seconds of running game clock
    (before that the clock is frozen at the start of the quarter, or the scoreboard is not on screen). None if not found."""
    return next((a for a, b in _runs(live) if b - a >= min_run_s), None)


def bug_track(th: np.ndarray, min_hold_s: int = 20):
    """vv19: find the broadcast's score BUG (the small score box, wherever it sits) in per-second grey thumbnails and say
    when it is on screen. Returns {"present": bool per second, "onset": s, "end": s} or None when nothing like a bug is found.
    The bug is a small, sharp picture that stays put while the camera moves, so the median over time shows it; it is on screen
    where a frame matches that median again. A logo that is there from the first seconds is a watermark, not the bug.
    onset = when the bug first appears and stays (the game has started); end = when it finally goes (the game is over)."""
    import cv2
    T = len(th)
    if T < 40:
        return None
    sub = th[:: max(1, T // 900)].astype(np.float32)                    # at most ~900 pictures for the statistics
    med = np.median(sub, axis=0)
    stable = (np.abs(sub - med) < 14).mean(0)
    g = np.hypot(cv2.Sobel(med, cv2.CV_32F, 1, 0), cv2.Sobel(med, cv2.CV_32F, 0, 1))
    core = (stable > 0.30) & (g > 60)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cv2.dilate(core.astype(np.uint8), np.ones((3, 5), np.uint8)), connectivity=8)
    area_all = th.shape[1] * th.shape[2]
    best = None
    for i in range(1, n):
        area = stats[i][4]
        if area < 12 or area > 0.15 * area_all:
            continue                                                   # specks, or too big to be a bug
        in_cluster = (lab == i) & core
        if not in_cluster.any():
            continue
        mask = in_cluster & (stable >= 0.8 * stable[in_cluster].max())     # the pixels that really stay put
        px = th[:, mask].astype(np.int16)
        present = (np.abs(px - med[mask].astype(np.int16)) < 20).mean(1) > 0.8
        if present[:5].mean() > 0.5 or present.mean() < 0.15:
            continue                                                   # a watermark (there from the start) or hardly ever there
        runs = [r for r in _runs(present) if r[1] - r[0] >= min_hold_s]
        if not runs:
            continue
        energy = float(g[mask].sum())
        if best is None or energy > best[0]:
            best = (energy, present, runs)
    if best is None:
        return None
    _, present, runs = best
    return {"present": present, "onset": float(runs[0][0]), "end": game_end(runs)}


def bug_onset(th: np.ndarray, min_hold_s: int = 20):
    """Second at which the score bug first appears and stays; None when no bug is found."""
    t = bug_track(th, min_hold_s)
    return t["onset"] if t else None


def tipoff_from_bug(th: np.ndarray, window_s: int = 30, track: dict | None = None):
    """vv18: the jump ball when the scoreboard clock cannot be read. The bug appears just after the tip, and the shot before it
    is the wide camera lining the players up: the last clear camera cut in the `window_s` seconds before the bug is the
    start of that shot. The jump ball is taken 3 s into it (the clip then starts `tip_lead_s` earlier). None if no bug."""
    track = track if track is not None else bug_track(th)
    if track is None:
        return None
    t_bug = track["onset"]
    lo, hi = max(1, int(t_bug) - window_s), int(t_bug) - 1
    if hi <= lo:
        return float(max(0.0, t_bug - 8))
    m = min(len(th), 1800)                                               # change between neighbouring seconds, over the opening stretch
    d = np.zeros(len(th) - 1, np.float32)
    d[:m - 1] = np.abs(np.diff(th[:m].astype(np.float32), axis=0)).mean((1, 2))   # d[i] = change between second i and i+1
    med = float(np.median(d[:m - 1])) if m > 2 else 0.0
    strong = [i for i in range(lo, hi + 1) if d[i - 1] >= max(1.4 * med, 25.0)]      # clear camera cuts before the bug
    if not strong:                                                                   # no clear cut: stay a little before the bug
        return float(max(0.0, t_bug - 8))
    return float(strong[-1] + 3)                                                     # the LAST one: the shot the bug appears in


def _top_up(final: list, secs: int, motion: np.ndarray, interest, min_s: float, max_s: float,
            end_s: float | None = None, start_s: float = 0.0) -> list:
    """The clip came out shorter than the minimum: add back whole stretches from the parts that were cut,
    most interesting first (crowd noise + motion), until the minimum is reached. Still in game order.
    vv13: nothing after `end_s` (the end of the game) is added back, so the post-game interview stays out.
    vv14: nothing before `start_s` (the jump ball, when that option is ticked) is added back either."""
    end_s = float(secs) if end_s is None else float(min(end_s, secs))
    gaps, t = [], float(start_s)
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


def gametime_card(th: np.ndarray) -> np.ndarray:
    """vv26: per second, True where the picture is a 'GAMETIME HIGHLIGHTS' stats card (the channel's own box-score card
    shown at the start or the end): a dark, flat screen with the text packed on the left side and the right side empty.
    th = per-second grey pictures (T x H x W). Live play never looks like this (the court and the crowd fill the frame)."""
    T = len(th)
    if T == 0:
        return np.zeros(0, bool)
    w = th.shape[2]
    f = th.astype(np.float32)
    left, right = f[:, :, : int(w * 0.50)], f[:, :, int(w * 0.62):]
    dark = f.mean((1, 2)) < 60
    empty_right = (right.std((1, 2)) < 9) & (right.mean((1, 2)) < 60)
    text_left = (left.std((1, 2)) > 14) & (((left > 110).mean((1, 2)) > 0.015) & ((left > 110).mean((1, 2)) < 0.30))
    return dark & empty_right & text_left


def _cut_runs(live: np.ndarray, mask: np.ndarray, min_s: int = 3) -> int:
    """Turn off `live` where `mask` holds for at least min_s seconds in a row (the card shows for a few seconds). Returns seconds cut."""
    cut = 0
    for a, b in _runs(mask):
        if b - a >= min_s:
            a2, b2 = max(0, a - 1), min(len(live), b + 1)
            cut += int(live[a2:b2].sum()); live[a2:b2] = False
    return cut


def hype_track(cues: list, secs: int) -> np.ndarray:
    """vv24: per second, how excited the commentators' words are (exciting words and exclamations), smoothed over +-3 s."""
    from . import captions
    h = np.zeros(max(secs, 1), np.float32)
    for t, text in cues or []:
        i = int(t)
        if 0 <= i < len(h):
            h[i] += len(captions.HYPE.findall(text)) * 2 + text.count("!")
    k = np.ones(7, np.float32) / 7
    return np.convolve(h, k, mode="same")


def best_clips(live: np.ndarray, rz: np.ndarray, mz: np.ndarray, hype: np.ndarray, max_s: float, start_s: float = 0.0,
               end_s: float | None = None, before_s: float = 10.0, after_s: float = 8.0, apart_s: float = 20.0) -> list:
    """vv24 'Best Clips': the moments the crowd and the commentators reacted to most. Each pick is a clip that starts
    `before_s` before the peak and ends `after_s` after it, never running through dead time (it is cut to the running play
    around the peak). Picks are at least `apart_s` apart, best first, until `max_s` is full; returned in game order."""
    n = len(live)
    z = lambda x: (x - x.mean()) / (x.std() + 1e-6) if len(x) and x.std() > 0 else np.zeros(len(x))
    sc = np.zeros(n, np.float32)
    for arr, w in ((rz, 0.5), (mz, 0.2), (z(hype), 0.3)):
        m = min(n, len(arr))
        sc[:m] += w * np.asarray(arr[:m], np.float32)
    end_s = float(n) if end_s is None else min(float(end_s), float(n))
    sc[~live] = -1e9
    sc[: int(start_s)] = -1e9
    sc[int(end_s):] = -1e9
    runs = _runs(live)
    picks, segs, total = [], [], 0.0
    for t in np.argsort(-sc):
        t = int(t)
        if sc[t] < -1e8 or total >= max_s:
            break
        if any(abs(t - c) < apart_s for c in picks):
            continue
        run = next((r for r in runs if r[0] <= t < r[1]), None)
        if run is None:
            continue
        a, b = max(float(run[0]), t - before_s, start_s), min(float(run[1]), t + after_s, end_s)
        if b - a < 5 or total + (b - a) > max_s * 1.02:
            continue
        picks.append(t); segs.append([a, b]); total += b - a
    segs.sort()
    merged: list = []
    for a, b in segs:
        if merged and a <= merged[-1][1] + 0.01:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


GAME_OVER = None


def final_from_cues(cues: list, secs: float, from_frac: float = 0.6) -> float | None:
    """vv38: the second the commentators say the game is over ('... win the ball game', 'that's the ballgame', 'final score',
    'the final buzzer', 'game over'). Looks only in the last part of the video and takes the FIRST such line there. Returns the second
    just after that line (a few seconds for its words), or None. cues = [(start_s, text)]."""
    import re
    global GAME_OVER
    if GAME_OVER is None:
        GAME_OVER = re.compile(r"\b(?:(?:that'?s|that is|win|wins|won)\s+(?:the\s+)?ball\s?game|final\s+(?:score|buzzer|horn)|game\s+over"
                               r"|(?:final\s+)?(?:horn|buzzer)\s+sounds)\b", re.I)
    for t, text in sorted(cues or [], key=lambda c: c[0]):
        if t >= secs * from_frac and GAME_OVER.search(text or ""):
            words = len(re.findall(r"\w+", text))
            return float(t) + min(6.0, 1.2 + 0.4 * words)
    return None


def clamp_to_end(final: list, end_s: float, end_known: bool) -> list:
    """vv38: nothing is ever kept after the game's end: pieces that start after it go, a piece that runs past it is cut at it."""
    if not end_known or end_s <= 0:
        return final
    out = []
    for a, b in final:
        if a >= end_s - 0.01:
            continue
        out.append([a, min(b, end_s)])
    return out or final


def ensure_ending(final: list, end_s: float, end_known: bool, tail_s: float = 12.0) -> tuple:
    """vv36: every clip ends at the game's end (the final play and the final score). When the last picked piece stops earlier,
    the last `tail_s` seconds up to the game end are added. Returns (segments, added_seconds). Nothing is added when the
    game end is not known (then the video's very end may be credits)."""
    if not final or not end_known or end_s <= 0:
        return final, 0.0
    final = clamp_to_end([list(x) for x in final], end_s, end_known)      # vv38: never past the end
    last_b = final[-1][1]
    if last_b >= end_s - 0.75:
        final[-1][1] = max(last_b, end_s) if last_b < end_s else last_b
        return final, 0.0
    a = max(end_s - tail_s, last_b)
    if end_s - a < 2.0:
        final[-1][1] = end_s
        return final, end_s - last_b
    if a <= last_b + 0.01:
        added = end_s - last_b
        final[-1][1] = end_s
    else:
        added = end_s - a
        final.append([a, end_s])
    return final, added


def best_plays(segs: list, rz: np.ndarray, mz: np.ndarray, hype: np.ndarray, motion: np.ndarray, max_s: float,
               start_s: float = 0.0, end_s: float | None = None, share: float = 0.5) -> list:
    """vv37 'Best Clips': whole PLAYS, ranked by how much the crowd, the motion and the commentators reacted.
    A play is one of the chunks the normal reclip uses (a running stretch cut at camera cuts), so a picked play always runs
    to its end (miss -> rebound -> putback is never cut in the middle). Chunks that are mostly crowd / bench / interview shots
    (very little movement) are left out, nothing after the end of the game is taken (once the final buzzer sounds the clip ends),
    and the jump-ball play always opens the clip. About `share` of the playing time is kept, never more than `max_s`."""
    chunks = [list(c) for c in segs if c[1] > start_s and (end_s is None or c[0] < end_s)]
    if not chunks:
        return []
    for c in chunks:
        c[0] = max(c[0], start_s)
        if end_s is not None:
            c[1] = min(c[1], end_s)
    chunks = [c for c in chunks if c[1] - c[0] >= 3.0]
    if not chunks:
        return []
    n = max(len(rz), len(mz), len(hype), int(max(c[1] for c in chunks)) + 1)
    z = lambda x: (x - x.mean()) / (x.std() + 1e-6) if len(x) and x.std() > 0 else np.zeros(len(x))
    sc = np.zeros(n, np.float32)
    for arr, w in ((rz, 0.5), (mz, 0.2), (z(np.asarray(hype, np.float32)), 0.3)):
        m = min(n, len(arr))
        sc[:m] += w * np.asarray(arr[:m], np.float32)

    def mot(c):
        a, b = int(c[0]), max(int(c[0]) + 1, int(c[1]))
        return float(np.mean(motion[a:b])) if len(motion) > a else 0.0
    mots = np.array([mot(c) for c in chunks])
    floor = 0.5 * float(np.median(mots)) if len(mots) else 0.0                 # crowd / bench / interview shots barely move
    ranked = []
    for i, c in enumerate(chunks):
        a, b = int(c[0]), max(int(c[0]) + 1, int(c[1]))
        value = float(sc[a:b].max()) if b <= len(sc) else float(sc[a:].max())
        calm = mots[i] < floor and i != 0
        ranked.append((value - (5.0 if calm else 0.0), i, calm))
    eligible = sum(c[1] - c[0] for i, c in enumerate(chunks) if not ranked[i][2])
    target = min(float(max_s), max(share, 0.05) * max(eligible, 1.0))
    picked, total = {0}, chunks[0][1] - chunks[0][0]                            # the jump-ball play always opens the clip
    for value, i, calm in sorted(ranked, reverse=True):
        if total >= target:
            break
        if i in picked or calm:
            continue
        if total + (chunks[i][1] - chunks[i][0]) > max_s * 1.02:
            continue
        picked.add(i); total += chunks[i][1] - chunks[i][0]
    out: list = []
    for i in sorted(picked):
        a, b = chunks[i]
        if out and a <= out[-1][1] + 0.01:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def plan(path: str, cfg: dict, log=print, cues: list | None = None) -> dict:
    progress.set("analysing the video")
    info = media.probe(path)
    m, s = divmod(int(info["duration"]), 60)
    log(f"video: {info['width']}x{info['height']}, {info['codec']}, {m}:{s:02d} long")
    secs = int(info["duration"])
    with tempfile.TemporaryDirectory() as tmp:
        clk, mot, aud, thumbs = _extract(path, info, cfg["clock_roi"], tmp)
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
    try:                                                  # vv19: where the score bug is on screen: the game starts and ends there
        track = bug_track(thumbs)
    except Exception as e:                                # noqa: BLE001 - never let this stop a clip
        log(f"(score bug search skipped: {e})")
        track = None
    # vv13: the post-game interview is cut unless "Include post-game interview" is ticked
    end_s = float(secs)
    end_known = False
    interview_cut = 0.0
    if not cfg.get("include_interview", False) and secs > 120:
        if clock_ok:
            runs = _runs(live)
            if runs:
                end_s = min(float(secs), game_end(runs) + END_PAD_S)
                end_known = True
        elif track is not None:                           # vv19: no clock - the game ends where the score bug goes for good
            end_s = min(float(secs), track["end"] + END_PAD_S)
            end_known = True
        else:                                             # vv19: cannot tell where the game ends: cut NOTHING (a guess cut real play)
            log("note: could not tell where the game ends (no readable clock or score bug) - nothing was cut at the end")
        ce = final_from_cues(cues, secs, 0.6 if clock_ok else 0.8) if cues else None     # vv38: "... win the ball game"
        if ce is not None and ce < end_s - 5 and (not clock_ok or live[int(ce):int(end_s)].sum() < 25):
            log(f"the announcers close the game at {int(ce) // 60}:{int(ce) % 60:02d} (the final score) - the clip ends there, "
                f"{(end_s - ce) / 60:.1f} min earlier than the score bug / clock alone would say")
            end_s = max(1.0, min(float(secs), ce))
            end_known = True
        if end_s < secs:
            live[int(end_s):] = False
            interview_cut = secs - end_s
            log(f"post-game: the last {interview_cut / 60:.1f} min of the video (after the final play) is left out "
                f"- tick 'Include post-game interview' to keep it")
    # vv14: "Start at the jump ball" - cut the long opening (intros, warm-up, pre-game show) before tip-off
    start_s = 0.0
    if cfg.get("start_at_tipoff", False):
        tip = tipoff(live) if clock_ok else None
        how = "scoreboard clock"
        if tip is None:                                                     # vv18: clock unreadable - find the score bug instead
            tip = tipoff_from_bug(thumbs, track=track) if track is not None else None
            how = "score bug"
        if tip is not None:
            start_s = max(0.0, tip - float(cfg.get("tip_lead_s", 1)))
            live[:int(start_s)] = False
            log(f"jump ball found at {int(tip) // 60}:{int(tip) % 60:02d} (from the {how}) - the clip starts at "
                f"{int(start_s) // 60}:{int(start_s) % 60:02d} (the first {start_s / 60:.1f} min are left out)")
        else:
            log("WARNING: could not find the jump ball (the scoreboard clock was not readable, or no running clock was seen) "
                "- the clip is not shortened at the start")
    try:                                                  # vv26: the channel's own 'GAMETIME HIGHLIGHTS' stats card is never kept
        card = gametime_card(thumbs)[:secs]
        cut = _cut_runs(live, np.r_[card, np.zeros(max(0, secs - len(card)), bool)])
        if cut:
            log(f"'GAMETIME HIGHLIGHTS' stats card found and cut ({cut}s)")
    except Exception as e:                                # noqa: BLE001 - never let this stop a clip
        log(f"(stats card search skipped: {e})")
    hl = bool(cfg.get("highlights"))
    if hl:
        # highlights: short gaps in the scoreboard read are kept as play
        for r in _runs(~live):
            if r[1] - r[0] <= 8 and r[0] > 0 and r[1] < secs:
                live[r[0]:r[1]] = True
        # start a few seconds before tip-off (first stretch of running clock), like the reference reclip
        tip = next((a for a, b in _runs(live) if b - a >= 20), None) if start_s <= 0 else None   # 20 s of running clock = game on
        if tip is not None:                              # (vv18: not when "Start at the jump ball" already placed the start)
            lead = int(cfg.get("highlight_lead_s", 1))
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
    if start_s > 0 and merged:                           # vv18: padding must not pull in the shot before the jump ball
        merged[0][0] = max(merged[0][0], start_s)
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

    if cfg.get("best_clips"):                           # vv24: Best Clips - the loudest moments, not the normal reclip
        hz = hype_track(cues or [], secs)
        final = best_plays(segs, rz, mz, hz, motion, max_s, start_s, end_s, float(cfg.get("best_clips_share", 0.5)))   # vv37: whole plays; always opens at the jump ball
        if start_s > 0 and live[int(start_s):int(start_s) + 6].any() and (not final or final[0][0] > start_s + 0.01):
            final.insert(0, [start_s, min(start_s + 6.0, final[0][0] if final else start_s + 6.0, float(secs))])   # vv32: always opens at the jump ball
        final, added = ensure_ending(final, end_s, end_known)
        if added:
            log(f"the clip is closed with the last {added:.0f}s up to the final score (Best Clips always ends at the finish)")
        kept_s = sum(b - a for a, b in final)
        log(f"Best Clips: {total:.0f}s source -> {len(final)} plays, {kept_s:.0f}s ({kept_s / 60:.1f} min; limit {max_s / 60:.0f} min)"
            + (" - picked by crowd noise, motion and the commentators' words" if cues else " - picked by crowd noise and motion (no captions)"))
        return {"info": info, "segments": final, "kept_s": kept_s, "source_s": total, "after_dead_s": after_dead,
                "game_end_s": end_s, "interview_cut_s": interview_cut, "start_s": start_s}
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
    final, added = ensure_ending(final, end_s, end_known)
    if added:
        log(f"the clip is closed with the last {added:.0f}s up to the final score")
    kept_s = sum(b - a for a, b in final)
    if kept_s < min_s * 0.97:                           # too short to follow: add the most active stretches that were cut
        final = _top_up(final, secs, motion, interest, min_s, max_s, end_s, start_s)
        final, _ = ensure_ending(final, end_s, end_known)
        kept_s = sum(b - a for a, b in final)
    log(("highlights mode - " if hl else "") + f"analysis: {total:.0f}s source -> live play {after_dead:.0f}s -> final {kept_s:.0f}s "
        f"({kept_s / 60:.1f} min; you asked for {min_s / 60:.0f}-{max_s / 60:.0f} min) in {len(final)} clips")
    if not end_known and not cfg.get("include_interview", False):
        log("note: the end of the game could not be found, so the clip is not forced to end at the final score")
    if kept_s < min_s * 0.9:
        log(f"note: only {kept_s / 60:.1f} min could be kept - the rest of the video had no activity worth keeping")
    return {"info": info, "segments": final, "kept_s": kept_s, "source_s": total, "after_dead_s": after_dead,
            "game_end_s": end_s, "interview_cut_s": interview_cut, "start_s": start_s}
