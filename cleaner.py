"""Finds promo words on comic pages (the website name, "Lua Scans", "translated by", Discord and
support banners ...) and hides them.

How it works, for every downloaded page:
1. The page is read line by line, in overlapping slices, with a free text reader (RapidOCR).
2. A line that matches a banned word (even if a letter is misread) is a "hit". Lines that sit
   right next to a hit are part of the same promo text and are hidden with it.
3. Hits that belong together are joined into a promo block. A block that reaches the top or
   bottom of the page is cut away together with its empty background; a page that is only
   promo is removed.
4. A block in the middle of a page: each line is painted over with the background color if
   the background is plain, otherwise blurred until it cannot be read.
Names of artists and the story's own text are not touched.
"""
import difflib
import importlib.util
import math
import os
import re
import threading

import core
import covers

try:
    import numpy as np
    from PIL import Image, ImageFilter
    HAS_TOOLS = True
except Exception:  # pragma: no cover
    HAS_TOOLS = False

# Always hidden when the option is ticked (the box in the window adds your own words to these).
DEFAULT_WORDS = [
    "luacomic.org", "luacomic", "lua scans", "luascans", "lua", "dsc.gg",
    "translated", "translate", "translating", "translation", "transcribed", "transcribe",
    "official domain", "other domain", "is a scam", "scam",
    "our website", "visit our", "official website",
    "support us", "supporting us", "fastest releases", "latest chapters",
    "join our discord", "our discord", "discord", "is now available", "now available",
    "read it at", "read at", "read on", "scanlation", "scanlated",
]
# Words that mean credits. They are kept (never fuzzy-matched as "translate").
PROTECTED = ("translator", "editor", "proofread", "typeset", "cleaner", "redraw", "quality")

UNIFORM = 12      # a row whose brightness varies less than this is plain background
EDGE = 80         # a promo block this close to the page edge counts as touching it
NEAR = 50         # a text line this close under/over a promo line belongs to it
LINK_GAP = 520    # promo lines further apart than this are separate blocks
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


def all_words(extra_text=""):
    """The built-in list plus the words typed in the window."""
    out = list(DEFAULT_WORDS)
    for w in parse_words(extra_text):
        if w.lower() not in out:
            out.append(w.lower())
    return out


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def text_matches(text, words):
    """True if the text contains one of the words, allowing for small reading slips.
    Short words (like 'lua') must start a word, so 'valuable' is never hit."""
    t = _norm(text)
    if not t:
        return False
    tokens = [_norm(x) for x in re.split(r"[^A-Za-z0-9]+", text or "") if x]
    for w in words:
        wn = _norm(w)
        if len(wn) < 3:
            continue
        if len(wn) < 6:
            if any(tok == wn or (tok.startswith(wn) and len(wn) >= 3) for tok in tokens):
                return True
            continue
        if wn in t:
            return True
    if any(p in t for p in PROTECTED):
        return False
    for w in words:
        wn = _norm(w)
        if len(wn) < 7:
            continue
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


def read_lines(im, engine, stop=None):
    """Every text line on the page as (x0, y0, x1, y1, text), in whole-page coordinates."""
    arr = np.asarray(im.convert("RGB"))
    height = arr.shape[0]
    lines, y = [], 0
    while True:
        if stop is not None and stop.is_set():
            raise core.Stopped()
        end = min(height, y + TILE)
        result, _ = engine(arr[y:end])
        for box, text, _conf in (result or []):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append((int(min(xs)), int(min(ys)) + y, int(max(xs)), int(max(ys)) + y, text))
        if end >= height:
            break
        y = end - OVERLAP
    return lines


def find_blocks(lines, words, stats):
    """Promo blocks as (y0, y1, [boxes]) from the page's text lines. stats = (row_std, row_mean)."""
    row_std, row_mean = stats
    hits = [ln for ln in lines if text_matches(ln[4], words)]
    if not hits:
        return []
    chosen = list(hits)
    for ln in lines:  # lines right next to a hit are part of the same promo text
        if ln in chosen:
            continue
        for h in hits:
            gap = max(ln[1] - h[3], h[1] - ln[3])
            if gap <= NEAR:
                chosen.append(ln)
                break
    chosen.sort(key=lambda b: (b[1], b[0]))
    blocks = []
    for ln in chosen:
        box = (ln[0], ln[1], ln[2], ln[3])
        if blocks:
            y0, y1, boxes = blocks[-1]
            gap = ln[1] - y1
            plain = float(np.mean((row_std[y1:ln[1]] < UNIFORM) | (row_mean[y1:ln[1]] < 80))) if gap > 0 else 1
            if gap <= 300 or (gap <= LINK_GAP and plain >= 0.6):
                blocks[-1] = (y0, max(y1, ln[3]), boxes + [box])
                continue
        blocks.append((ln[1], ln[3], [box]))
    return blocks


def _extend(row_std, row_mean, y, step, limit):
    """Move from y in the given direction through plain background of the banner's own color."""
    h = len(row_std)
    r = y
    ref = None
    for k in range(1, 41):  # find the banner's plain background just outside the text
        i = y + step * k
        if i < 0 or i >= h:
            return limit  # ran into the page edge
        if row_std[i] < UNIFORM:
            ref = row_mean[i]
            y = i
            break
    if ref is None:
        return y
    r = y
    while 0 <= r + step < h and row_std[r + step] < UNIFORM and abs(row_mean[r + step] - ref) < 30:
        r += step
    return r


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
    """Hide the promo words on one page file. Returns 'none', 'cut', 'blurred', 'deleted'
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
    lines = read_lines(im, engine or get_engine(), stop)
    gray = np.asarray(im.convert("L"), dtype=np.float32)
    row_std, row_mean = gray.std(axis=1), gray.mean(axis=1)
    blocks = find_blocks(lines, words, (row_std, row_mean))
    if not blocks:
        return "none"

    top_cut, bottom_cut, others = 0, h, []
    for (y0, y1, boxes) in blocks:
        up = _extend(row_std, row_mean, y0, -1, 0)
        down = _extend(row_std, row_mean, y1, 1, h)
        if y0 <= EDGE or up <= 4:
            top_cut = max(top_cut, down if down > y1 else y1 + 1)
        elif h - y1 <= EDGE or down >= h - 4:
            bottom_cut = min(bottom_cut, up if up < y0 else y0)
        else:
            others.extend(boxes)

    work = im
    for box in _merge(others, gap=10):
        work = _hide_box(work, box)
    cut = top_cut > 0 or bottom_cut < h
    if cut:
        if bottom_cut - top_cut < 60:
            os.remove(path)
            return "deleted"
        work = work.crop((0, top_cut, w, bottom_cut))
        left = row_std[top_cut:bottom_cut]
        if int(np.sum(left >= UNIFORM)) < 40:  # only blank space (and a small credit) is left
            os.remove(path)
            return "deleted"
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
            files = sorted(f for f in os.listdir(folder)
                           if f.lower().endswith(core.IMG_EXT) and f.lower() != covers.COVER_NAME)
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
        dr = ImageDraw.Draw(im)
        dr.rectangle((40, 200, 560, 700), fill=(190, 200, 230))  # artwork behind the words
        dr.text((60, 420), "luacomic.org", fill="black", font=ImageFont.load_default(size=44))
        im.save(p)
        if clean_image(p, ["luacomic.org"]) == "none":
            raise RuntimeError("the text reader did not find the words")
        if clean_image(p, ["luacomic.org"]) != "none":
            raise RuntimeError("the words are still visible")
