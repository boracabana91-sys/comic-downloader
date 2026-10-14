"""Finds chosen words (such as a website address) on comic pages and hides them.

How it works, for every downloaded page:
1. The page is read in overlapping slices with a free text reader (RapidOCR).
2. Any text that matches one of your words (even if a letter is misread) is a "hit".
3. A hit inside a dark banner that touches the top or bottom of the page: the whole
   banner is cut off. A page that is only a banner is removed.
4. Any other hit: painted over with the background color if the background is plain,
   otherwise blurred until it cannot be read.
"""
import difflib
import importlib.util
import math
import os
import re
import threading

import core

try:
    import numpy as np
    from PIL import Image, ImageFilter
    HAS_TOOLS = True
except Exception:  # pragma: no cover
    HAS_TOOLS = False

DARK = 100        # a row darker than this (0-255) counts as part of a dark banner
EDGE = 8          # a banner this close to the page edge counts as touching it
TILE = 900        # height of each slice that is read
OVERLAP = 150     # slices overlap so no line of text is ever cut in half
SIZES = (".jpg", ".jpeg", ".png", ".webp")

_engine = None
_lock = threading.Lock()


def ocr_available():
    try:
        return HAS_TOOLS and importlib.util.find_spec("rapidocr_onnxruntime") is not None
    except Exception:
        return False


def get_engine():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        return _engine


def parse_words(text):
    """'luacomic.org, other words' -> ['luacomic.org', 'other words']"""
    return [w.strip() for w in re.split(r"[,\n;]", text or "") if len(w.strip()) >= 3]


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def text_matches(text, words):
    """True if the text contains one of the words, allowing for small reading slips."""
    t = _norm(text)
    if not t:
        return False
    for w in words:
        wn = _norm(w)
        if len(wn) < 3:
            continue
        if wn in t:
            return True
        n = len(wn)
        for length in (n - 1, n, n + 1):
            if length < 3 or length > len(t):
                continue
            for i in range(len(t) - length + 1):
                if difflib.SequenceMatcher(None, wn, t[i:i + length]).ratio() >= 0.82:
                    return True
    return False


def _merge(boxes, gap=6):
    out = []
    for b in sorted(boxes, key=lambda b: (b[1], b[0])):
        for i, o in enumerate(out):
            if (b[0] <= o[2] + gap and o[0] <= b[2] + gap
                    and b[1] <= o[3] + gap and o[1] <= b[3] + gap):
                out[i] = (min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3]))
                break
        else:
            out.append(b)
    return out


def find_hits(im, words, engine, stop=None):
    """Boxes (x0, y0, x1, y1) of text matching the words, in whole-page coordinates."""
    arr = np.asarray(im.convert("RGB"))
    height = arr.shape[0]
    hits, y = [], 0
    while True:
        if stop is not None and stop.is_set():
            raise core.Stopped()
        end = min(height, y + TILE)
        result, _ = engine(arr[y:end])
        for box, text, _conf in (result or []):
            if text_matches(text, words):
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                hits.append((int(min(xs)), int(min(ys)) + y, int(max(xs)), int(max(ys)) + y))
        if end >= height:
            break
        y = end - OVERLAP
    return _merge(hits)


def _hide_box(im, box):
    """Paint the words out (plain background) or blur them (busy background)."""
    w, h = im.size
    x0, y0, x1, y1 = box
    bh = max(1, y1 - y0)
    px, py = max(8, int(bh * 0.3)), max(6, int(bh * 0.6))
    rx0, ry0, rx1, ry1 = max(0, x0 - px), max(0, y0 - py), min(w, x1 + px), min(h, y1 + py)
    arr = np.asarray(im)
    m, ring = 6, []
    if ry0 - m >= 0:
        ring.append(arr[ry0 - m:ry0, rx0:rx1].reshape(-1, 3))
    if ry1 + m <= h:
        ring.append(arr[ry1:ry1 + m, rx0:rx1].reshape(-1, 3))
    if rx0 - m >= 0:
        ring.append(arr[ry0:ry1, rx0 - m:rx0].reshape(-1, 3))
    if rx1 + m <= w:
        ring.append(arr[ry0:ry1, rx1:rx1 + m].reshape(-1, 3))
    out = im.copy()
    if ring:
        pix = np.concatenate(ring).astype(np.float32)
        if pix.std(axis=0).max() <= 14:  # plain background: paint over the words
            color = tuple(int(v) for v in np.median(pix, axis=0))
            out.paste(color, (rx0, ry0, rx1, ry1))
            return out
    region = out.crop((rx0, ry0, rx1, ry1)).filter(
        ImageFilter.GaussianBlur(max(12, (ry1 - ry0) * 0.7)))
    out.paste(region, (rx0, ry0))
    return out


def _save(im, path):
    ext = os.path.splitext(path)[1].lower()
    tmp = path + ".tmp"
    try:
        if ext in (".jpg", ".jpeg"):
            im.save(tmp, "JPEG", quality=92, optimize=True)
        elif ext == ".png":
            im.save(tmp, "PNG", optimize=True)
        else:
            im.save(tmp, "WEBP", quality=92, method=4)
        os.replace(tmp, path)
    except Exception:
        # e.g. a WebP page taller than WebP allows: keep it as a JPG instead
        if os.path.exists(tmp):
            os.remove(tmp)
        new_path = os.path.splitext(path)[0] + ".jpg"
        im.save(new_path, "JPEG", quality=92, optimize=True)
        if new_path != path and os.path.exists(path):
            os.remove(path)


def clean_image(path, words, engine=None, stop=None):
    """Hide the words on one page file. Returns 'none', 'cut', 'blurred', 'deleted'
    or 'skipped'. A page with no hits is left exactly as it was."""
    if os.path.splitext(path)[1].lower() not in SIZES:
        return "skipped"
    try:
        with Image.open(path) as opened:
            opened.load()
            im = opened.convert("RGB")
    except Exception:
        return "skipped"
    w, h = im.size
    if w < 60 or h < 20:
        return "none"
    hits = find_hits(im, words, engine or get_engine(), stop)
    if not hits:
        return "none"

    rows = np.asarray(im.convert("L"), dtype=np.float32).mean(axis=1)
    top_cut, bottom_cut, others = 0, h, []
    for (x0, y0, x1, y1) in hits:
        a, b = y0, y1
        while a > 0 and rows[a - 1] < DARK:
            a -= 1
        while b < h and rows[b] < DARK:
            b += 1
        banner_like = (b - a) <= 0.8 * w + 60
        if banner_like and a <= EDGE:
            top_cut = max(top_cut, b)
        elif banner_like and h - b <= EDGE:
            bottom_cut = min(bottom_cut, a)
        else:
            others.append((x0, y0, x1, y1))

    work = im
    for box in others:
        work = _hide_box(work, box)
    if bottom_cut - top_cut < 60:  # the page was only a banner
        os.remove(path)
        return "deleted"
    cut = top_cut > 0 or bottom_cut < h
    if cut:
        work = work.crop((0, top_cut, w, bottom_cut))
    _save(work, path)
    return "cut" if cut else "blurred"


def _marker(folder):
    return os.path.join(folder, ".words-hidden.txt")


def clean_chapter(out_root, title, total, size, words, progress=None, stop=None):
    """Hide the words on every downloaded page of a chapter.
    Returns counts: {'scanned', 'cut', 'blurred', 'deleted', 'skipped'}."""
    sig = "|".join(sorted(_norm(w) for w in words))
    groups = []
    for g in range(math.ceil(total / size)):
        folder = os.path.join(out_root, core.group_folder_name(title, g * size + 1, total, size))
        if os.path.isdir(folder):
            done = set()
            if os.path.exists(_marker(folder)):
                with open(_marker(folder), encoding="utf-8") as f:
                    done = {ln.rstrip("\n") for ln in f}
            files = sorted(f for f in os.listdir(folder) if f.lower().endswith(core.IMG_EXT))
            groups.append((folder, [f for f in files if f"{f}|{sig}" not in done]))
    todo = sum(len(files) for _, files in groups)
    counts = {"scanned": 0, "cut": 0, "blurred": 0, "deleted": 0, "skipped": 0}
    if todo == 0:
        return counts
    engine = get_engine()
    n = 0
    for folder, files in groups:
        for f in files:
            if stop is not None and stop.is_set():
                raise core.Stopped()
            if progress:
                progress(n, todo, f"Looking for the words: page {n + 1} of {todo}")
            result = clean_image(os.path.join(folder, f), words, engine, stop)
            n += 1
            counts["scanned"] += 1
            if result in counts:
                counts[result] += 1
            if result != "deleted":
                with open(_marker(folder), "a", encoding="utf-8") as m:
                    m.write(f"{f}|{sig}\n")
    if progress:
        progress(todo, todo, "Finished looking for the words.")
    return counts


def selftest():
    """Used by the build to prove the packaged app can find and hide words."""
    import tempfile
    from PIL import ImageDraw, ImageFont
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        p = os.path.join(d, "t.png")
        im = Image.new("RGB", (600, 900), "white")
        ImageDraw.Draw(im).text((60, 420), "luacomic.org", fill="black",
                                font=ImageFont.load_default(size=44))
        im.save(p)
        if clean_image(p, ["luacomic.org"]) == "none":
            raise RuntimeError("the text reader did not find the words")
        if clean_image(p, ["luacomic.org"]) != "none":
            raise RuntimeError("the words are still visible")
