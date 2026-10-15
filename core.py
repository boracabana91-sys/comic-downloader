"""Core logic for Comic Downloader (no window code here, so it can be tested alone)."""
import os
import re
import math
import ssl
import tempfile
import threading
import zipfile
import covers
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from PIL import Image, ImageStat  # optional: WebP -> JPG and e-reader files
    HAS_PIL = True
except Exception:  # pragma: no cover
    HAS_PIL = False

# Packaged apps (especially on Mac) have no list of trusted certificates of their
# own, which caused "CERTIFICATE_VERIFY_FAILED". We ship the certifi list with
# the app and use it for every https connection. Verification stays ON.
try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover
    SSL_CTX = ssl.create_default_context()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif")
SKIP_WORDS = ("logo", "icon", "avatar", "favicon", "sprite", "banner",
              "placeholder", "loading", "emoji", "/ads/", "/ad/")


class NoImages(Exception):
    pass


class Stopped(Exception):
    pass


def fetch(url, referer=None, timeout=30):
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read(), r.headers.get_content_charset()


def fetch_text(url, referer=None):
    data, charset = fetch(url, referer)
    return data.decode(charset or "utf-8", errors="replace")


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tag_imgs = []      # image urls from <img>/<source>, in page order
        self.links = []         # <a href>
        self.scripts = []       # inline script text
        self.title = ""
        self.og_title = ""
        self._in_title = False
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "img":
            for key in ("data-src", "data-lazy-src", "data-original", "src"):
                v = a.get(key, "").strip()
                if v and not v.startswith("data:"):
                    self.tag_imgs.append(v)
                    break
            else:
                ss = a.get("srcset", "").strip()
                if ss:
                    self.tag_imgs.append(ss.split(",")[0].split()[0])
        elif tag == "source" and a.get("srcset"):
            self.tag_imgs.append(a["srcset"].split(",")[0].split()[0])
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"].strip())
        elif tag == "meta" and a.get("property") == "og:title":
            self.og_title = a.get("content", "").strip()
        elif tag == "title":
            self._in_title = True
        elif tag == "script":
            self._in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_script and self.scripts:
            self.scripts[-1] += data


_SCRIPT_IMG = re.compile(
    r"https?://[^\s\"'<>\\)]+?\.(?:jpe?g|png|webp|avif)(?:\?[^\s\"'<>\\)]*)?", re.I)


def _unescape_js(s):
    return (s.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
             .replace("&amp;", "&"))


def clean_title(raw, fallback="Comic"):
    parts = re.split(r"\s+[|–—-]\s+", (raw or "").strip())
    parts = [p for p in parts if p and not re.search(r"lua\s*comic", p, re.I)]
    t = " - ".join(parts) if parts else (raw or "")
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", t)
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t[:100].strip(" .") or fallback


def find_images(parsed, base_url):
    seen, found = set(), []

    def add(u, from_tag):
        u = urljoin(base_url, _unescape_js(u.strip()))
        path = urlparse(u).path.lower()
        if not u.startswith("http") or u in seen:
            return
        if not path.endswith(IMG_EXT) and not from_tag:
            return
        if any(w in path for w in SKIP_WORDS):
            return
        seen.add(u)
        found.append(u)

    for u in parsed.tag_imgs:
        add(u, True)
    for s in parsed.scripts:
        for m in _SCRIPT_IMG.finditer(_unescape_js(s)):
            add(m.group(0), False)

    # Chapter pages keep all pages in one folder on the server; drop strays
    # (ads, thumbnails, recommendations) by keeping the biggest group.
    groups = {}
    for u in found:
        groups.setdefault(u.split("?")[0].rsplit("/", 1)[0], []).append(u)
    if groups:
        best = max(groups.values(), key=len)
        if len(best) >= 3:
            found = [u for u in found if u in set(best)]
    return found


def find_chapter_links(parsed, base_url):
    host = urlparse(base_url).netloc
    out, seen = [], set()
    for h in parsed.links:
        u = urljoin(base_url, h).split("#")[0]
        p = urlparse(u)
        if p.netloc != host or "chapter" not in p.path.lower() or u in seen:
            continue
        if u.rstrip("/") == base_url.rstrip("/"):
            continue
        seen.add(u)
        out.append(u)

    def num(u):
        m = re.findall(r"\d+(?:[.-]\d+)?", u.rstrip("/").rsplit("/", 1)[-1])
        return float(m[-1].replace("-", ".")) if m else None

    nums = [num(u) for u in out]
    if out and all(n is not None for n in nums):
        out = [u for _, u in sorted(zip(nums, out), key=lambda x: x[0])]
    else:
        out.reverse()  # most sites list newest first
    return out


def inspect_page(url):
    """Returns dict: images, chapters, title."""
    html = fetch_text(url)
    p = _Page()
    p.feed(html)
    return {
        "images": find_images(p, url),
        "chapters": find_chapter_links(p, url),
        "title": clean_title(p.og_title or p.title),
    }


def group_folder_name(title, index, total, size=5):
    start = ((index - 1) // size) * size + 1
    end = min(start + size - 1, total)
    return f"{title} - Pages {start}-{end}"


def _ext_of(url):
    e = os.path.splitext(urlparse(url).path)[1].lower()
    return e if e in IMG_EXT else ".jpg"


def _download_one(url, dest, referer, convert, stop):
    if stop.is_set():
        raise Stopped()
    if os.path.exists(dest):
        return
    last = None
    for _ in range(3):
        if stop.is_set():
            raise Stopped()
        try:
            data, _c = fetch(url, referer=referer, timeout=45)
            if len(data) < 200:
                raise IOError("empty image")
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            if convert and HAS_PIL and dest.lower().endswith((".webp", ".avif")):
                try:
                    jpg = os.path.splitext(dest)[0] + ".jpg"
                    Image.open(dest).convert("RGB").save(jpg, "JPEG", quality=92)
                    os.remove(dest)
                except Exception:
                    pass  # keep the original file if conversion fails
            return
        except Stopped:
            raise
        except Exception as e:  # retry
            last = e
    raise last


def download_images(images, title, out_root, referer, progress=None, stop=None,
                    size=5, convert=False, workers=4):
    """Download images into '<title> - Pages A-B' folders. Returns failed list."""
    stop = stop or threading.Event()
    total = len(images)
    width = max(3, len(str(total)))
    jobs = []
    for i, u in enumerate(images, 1):
        folder = os.path.join(out_root, group_folder_name(title, i, total, size))
        os.makedirs(folder, exist_ok=True)
        jobs.append((u, os.path.join(folder, f"{i:0{width}d}{_ext_of(u)}"), i))

    done, failed, lock = 0, [], threading.Lock()

    def run(job):
        nonlocal done
        u, dest, i = job
        try:
            _download_one(u, dest, referer, convert, stop)
        except Stopped:
            return
        except Exception:
            with lock:
                failed.append(i)
        with lock:
            done += 1
            d = done
        if progress:
            progress(d, total, f"{title}: page {d} of {total}")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(run, jobs))
    if stop.is_set():
        raise Stopped()
    return sorted(failed)


# ---------------------------------------------------------------------------
# E-reader files (Kobo -> .cbz; Kindle, PocketBook, Boox, reMarkable, tablets -> .pdf)
# Screen sizes are portrait pixels: width x height.
# ---------------------------------------------------------------------------
def _dev(label, ext, size, gray, folder, kind):
    return {"label": label, "ext": ext, "size": size, "gray": gray,
            "folder": folder, "kind": kind}


DEVICES = {
    "images": {"label": "Just the images (folders)"},
    # --- Kobo (.cbz) ---
    "kobo": _dev("Kobo Clara - HD, 2E, BW, Colour (.cbz)", ".cbz", (1072, 1448), False,
                 "For Kobo Clara", "kobo"),
    "kobo_libra": _dev("Kobo Libra 2 / Libra Colour (.cbz)", ".cbz", (1264, 1680), False,
                       "For Kobo Libra", "kobo"),
    "kobo_sage": _dev("Kobo Sage / Forma (.cbz)", ".cbz", (1440, 1920), False,
                      "For Kobo Sage", "kobo"),
    "kobo_elipsa": _dev("Kobo Elipsa / Elipsa 2E (.cbz)", ".cbz", (1404, 1872), False,
                        "For Kobo Elipsa", "kobo"),
    # --- Kindle (.pdf) ---
    "kindle_basic": _dev("Kindle - basic 6 inch, 2022 or 2024 (.pdf)", ".pdf", (1072, 1448), True,
                         "For Kindle", "kindle"),
    "kindle_6": _dev("Kindle Paperwhite - 6 inch, 2015 to 2020 (.pdf)", ".pdf", (1072, 1448), True,
                     "For Kindle Paperwhite", "kindle"),
    "kindle_68": _dev("Kindle Paperwhite - 6.8 inch, 2021 (.pdf)", ".pdf", (1236, 1648), True,
                      "For Kindle Paperwhite", "kindle"),
    "kindle_7": _dev("Kindle Paperwhite - 7 inch, 2024 (.pdf)", ".pdf", (1264, 1680), True,
                     "For Kindle Paperwhite", "kindle"),
    "kindle_color": _dev("Kindle Colorsoft - color (.pdf)", ".pdf", (1264, 1680), False,
                         "For Kindle Colorsoft", "kindle"),
    "kindle_scribe": _dev("Kindle Scribe - 10 inch (.pdf)", ".pdf", (1860, 2480), True,
                          "For Kindle Scribe", "kindle"),
    # --- PocketBook (.pdf) ---
    "pocketbook_6": _dev("PocketBook - 6 inch (Touch HD, Verse Pro) (.pdf)", ".pdf", (1072, 1448),
                         False, "For PocketBook", "pocketbook"),
    "pocketbook_7": _dev("PocketBook - 7 inch (Era) (.pdf)", ".pdf", (1264, 1680), False,
                         "For PocketBook", "pocketbook"),
    "pocketbook_78": _dev("PocketBook - 7.8 inch (InkPad) (.pdf)", ".pdf", (1404, 1872), False,
                          "For PocketBook", "pocketbook"),
    # --- Boox (.pdf) ---
    "boox_6": _dev("Boox - 6 inch (Go 6) (.pdf)", ".pdf", (1072, 1448), False,
                   "For Boox", "boox"),
    "boox_7": _dev("Boox - 7 inch (Page, Leaf) (.pdf)", ".pdf", (1264, 1680), False,
                   "For Boox", "boox"),
    "boox_103": _dev("Boox - 10.3 inch (Go 10.3) (.pdf)", ".pdf", (1860, 2480), False,
                     "For Boox", "boox"),
    "boox_note": _dev("Boox - 10.3 inch (Note Air, Tab Ultra) (.pdf)", ".pdf", (1404, 1872), False,
                      "For Boox", "boox"),
    # --- reMarkable, tablets, your own size ---
    "remarkable": _dev("reMarkable 2 (.pdf)", ".pdf", (1404, 1872), True,
                       "For reMarkable", "remarkable"),
    "tablet": _dev("Tablet or phone - iPad, Android (.pdf, color)", ".pdf", (1600, 2400), False,
                   "For Tablet or Phone", "tablet"),
    "custom": {"label": "Custom size - type your own", "kind": "custom",
               "folder": "For Custom Size", "ext": ".pdf", "size": (1072, 1448), "gray": False},
}

DEVICE_KEYS = list(DEVICES)
# Used when "Just the images" is chosen and an EPUB file is wanted too (not in the menu)
DEVICES["epub_only"] = _dev("EPUB", ".epub", (1264, 1680), False, "For EPUB", "epub")


def _next_text(kind, ext, folder):
    f = f"the folder '{folder}'"
    if kind == "kobo":
        return (f"Next: plug your Kobo into the computer with its USB cable, tap Connect on the "
                f"Kobo screen, then drag the {ext} files from {f} onto the drive named KOBOeReader. "
                "Eject it, and the comics appear in your library.")
    if kind == "kindle":
        return ("Next: plug your Kindle into the computer with its USB cable. A drive named Kindle "
                f"appears. Open it, open the 'documents' folder, and drag the {ext} files from {f} "
                "into it. Eject the Kindle, and the comics appear in your library.")
    if kind == "pocketbook":
        return ("Next: plug your PocketBook into the computer with its USB cable (choose "
                "'Connect to PC' on its screen if it asks). A drive appears. Drag the "
                f"{ext} files from {f} into its main folder or its 'Books' folder, then eject it.")
    if kind == "boox":
        return ("Next: a Boox runs Android, so copying works a little differently. On the Boox, "
                "look for its Wi-Fi file transfer (called BooxDrop on many models), open the web page "
                f"it shows on your computer, and drag the {ext} files from {f} onto it. A USB cable "
                "also works; on a Mac you may need a free helper app such as OpenMTP.")
    if kind == "remarkable":
        return ("Next: on the reMarkable, turn on the USB web interface (Settings, then Storage). "
                "Plug it into the computer with its USB cable, open http://10.11.99.1 in your "
                f"browser, and drag the {ext} files from {f} onto the page.")
    if kind == "tablet":
        return (f"Next: copy the {ext} files from {f} to your tablet or phone (AirDrop, a USB cable, "
                "or a cloud drive such as iCloud Drive or Google Drive), then open them in any PDF "
                "reader or the Books app.")
    return (f"Next: copy the {ext} files from {f} onto your gadget the way it usually receives "
            "files (most e-readers show up as a drive when plugged in with a USB cable).")


def resolve_device(key, custom=None):
    """Settings for a device. For 'custom', pass {'width','height','ext','gray'}."""
    dev = dict(DEVICES[key])
    if key == "custom":
        c = custom or {}
        dev["size"] = (int(c.get("width", 1072)), int(c.get("height", 1448)))
        dev["ext"] = c.get("ext", ".pdf")
        dev["gray"] = bool(c.get("gray", False))
    if key != "images":
        dev["next"] = _next_text(dev["kind"], dev["ext"], dev["folder"])
    return dev


def epub_note(key):
    """What to do with the extra EPUB file on this gadget."""
    kind = DEVICES.get(key, {}).get("kind")
    if kind == "kindle":
        return ("About the EPUB file: a Kindle cannot open EPUB files copied over with a USB "
                "cable. Use the PDF on your Kindle. The EPUB is for other apps and readers.")
    if kind == "kobo":
        return ("About the EPUB file: drag it onto KOBOeReader the same way as the .cbz. "
                "If you only want one copy of each chapter on the Kobo, copy just one of them.")
    return ("About the EPUB file: copy it to your gadget the same way as the other file. "
            "It opens in any EPUB reader (Apple Books, Google Play Books, PocketBook, Boox).")


# ---------------------------------------------------------------------------
# Making screen-sized pages
#   * Tall webtoon strips that are split over several files are joined into one
#     long strip first, then cut into full screen pages at empty gaps between panels.
#     A page ends where the art ends, so nearly every page fills the whole screen.
#   * Any space left on a page is filled with the exact plain background next to it
#     (it is invisible), or with plain black or white when the art has no plain edge.
#   * Normal single pages (manga style) are fitted whole, like a book page.
# ---------------------------------------------------------------------------
QUIET = 6        # a row whose brightness spread is below this is empty background
STRIP = 1.6      # a picture taller than 1.6 x its width is part of a webtoon strip


def _page_to_rgb_or_gray(im, gray):
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.split()[3])
        im = bg
    return im.convert("L" if gray else "RGB")


def _rows(im):
    import numpy as np
    a = np.asarray(im if im.mode == "L" else im.convert("L"), dtype=np.float32)
    return a.std(axis=1)


def _fill(region):
    """Color to fill next to this strip of the page: its own plain background if it has
    one (so the fill cannot be seen), otherwise plain black or white."""
    import numpy as np
    a = np.asarray(region, dtype=np.float32)
    a = a.reshape(-1, 1) if a.ndim == 2 else a.reshape(-1, a.shape[-1])
    if a.std(axis=0).max() <= 10:
        v = [int(round(x)) for x in np.median(a, axis=0)]
    else:
        v = [0] * a.shape[1] if a.mean() < 128 else [255] * a.shape[1]
    return v[0] if region.mode == "L" else tuple(v[:3])


def _bottom_padded(piece, width, height):
    """Page anchored at the top; the space under it uses the background just above it."""
    if piece.height >= height:
        return piece
    k = min(6, piece.height)
    canvas = Image.new(piece.mode, (width, height), _fill(piece.crop((0, piece.height - k,
                                                                      piece.width, piece.height))))
    canvas.paste(piece, (0, 0))
    return canvas


def _fit_single(im, width, height):
    """A normal page: the whole page fitted on the screen, centered like a book page."""
    scale = min(width / im.width, height / im.height)
    nw, nh = max(1, round(im.width * scale)), max(1, round(im.height * scale))
    if (nw, nh) == im.size:
        page = im
    else:
        page = im.resize((nw, nh), Image.LANCZOS)
    if (nw, nh) == (width, height):
        return page
    k = 4
    ring = Image.new(page.mode, (nw * 2 + nh * 2, k))
    parts = [page.crop((0, 0, nw, k)), page.crop((0, nh - k, nw, nh)),
             page.crop((0, 0, k, nh)).rotate(90, expand=True),
             page.crop((nw - k, 0, nw, nh)).rotate(90, expand=True)]
    x = 0
    for p in parts:
        ring.paste(p, (x, 0))
        x += p.width
    canvas = Image.new(page.mode, (width, height), _fill(ring))
    canvas.paste(page, ((width - nw) // 2, (height - nh) // 2))
    return canvas


def _sides_plain(im):
    """True when the left and right edges are one plain color (side space is then invisible)."""
    import numpy as np
    k = 4
    for box in ((0, 0, k, im.height), (im.width - k, 0, im.width, im.height)):
        a = np.asarray(im.crop(box), dtype=np.float32)
        a = a.reshape(-1, 1) if a.ndim == 2 else a.reshape(-1, a.shape[-1])
        if a.std(axis=0).max() > 10:
            return False
    return True


def _find_cut(buf, height):
    """Where to end a page and where the next one starts.
    Usually both are the lowest empty row that still fits on the screen. When the art has
    no empty gap there, the page is a full screen and the next page starts a little higher,
    at the quietest row, so a speech bubble cut at the bottom is shown whole on the next page."""
    std = _rows(buf.crop((0, 0, buf.width, min(buf.height, height + 1))))
    top = min(height, len(std) - 1)
    for y in range(top, int(height * 0.7) - 1, -1):
        if std[y] < QUIET:
            return y, y
    lo = int(height * 0.82)
    best = min(range(lo, top + 1), key=lambda y: std[y])
    return height, best


def _squeeze_gaps(im, max_gap):
    """Long empty gaps between panels are made shorter so pages are not half empty."""
    import numpy as np
    a = np.asarray(im if im.mode == "L" else im.convert("L"), dtype=np.float32)
    std, mean = a.std(axis=1), a.mean(axis=1)
    quiet = std < QUIET
    keep, y, n = [], 0, len(quiet)
    while y < n:
        if not quiet[y]:
            y += 1
            continue
        e = y
        while e < n and quiet[e] and abs(mean[e] - mean[y]) < 6:
            e += 1
        if e - y > max_gap:
            keep.append((y + max_gap // 2, e - max_gap // 2))  # rows to drop
        y = max(e, y + 1)
    if not keep:
        return im
    parts, last = [], 0
    for a0, a1 in keep:
        parts.append((last, a0))
        last = a1
    parts.append((last, im.height))
    total = sum(b - a for a, b in parts)
    out = Image.new(im.mode, (im.width, total))
    y = 0
    for a, b in parts:
        out.paste(im.crop((0, a, im.width, b)), (0, y))
        y += b - a
    return out


def _vjoin(a, b):
    out = Image.new(a.mode, (a.width, a.height + b.height))
    out.paste(a, (0, 0))
    out.paste(b, (0, a.height))
    return out


class _Pager:
    """Collects pictures in reading order and turns them into screen-sized pages."""

    def __init__(self, tmp_dir, width, height, gray, start_no=0):
        self.tmp, self.w, self.h, self.gray = tmp_dir, width, height, gray
        self.buf = None
        self.pages = []
        self.n = start_no

    def _save(self, im):
        path = os.path.join(self.tmp, f"p{self.n:05d}.jpg")
        self.n += 1
        im.save(path, "JPEG", quality=90, optimize=True)
        self.pages.append(path)

    def _cut_pages(self, keep):
        # keep a screen and a half in hand so the next cut can look for a gap
        while self.buf is not None and self.buf.height > keep:
            self._trim_top()
            if self.buf.height <= keep:
                break
            cut, nxt = _find_cut(self.buf, self.h)
            self._save(_bottom_padded(self.buf.crop((0, 0, self.w, cut)), self.w, self.h))
            self.buf = self.buf.crop((0, max(1, nxt), self.w, self.buf.height))

    def _trim_top(self):
        """A long empty gap at the top of a page is shortened, so pages start with the art."""
        std = _rows(self.buf.crop((0, 0, self.w, min(self.buf.height, self.h))))
        lead = 0
        while lead < len(std) and std[lead] < QUIET:
            lead += 1
        if lead > 40 and lead < len(std):
            self.buf = self.buf.crop((0, lead - 40, self.w, self.buf.height))

    def flush(self):
        """End of a strip: the last piece becomes the last page (an empty one is skipped)."""
        if self.buf is None:
            return
        self._cut_pages(int(self.h * 1.3))  # a short last bit is kept with the page before it
        if self.buf is None:
            return
        self._trim_top()
        piece = self.buf
        self.buf = None
        std = _rows(piece)
        rows = [i for i, s in enumerate(std) if s >= QUIET]
        if not rows:
            return  # just empty background
        piece = piece.crop((0, 0, piece.width, min(piece.height, rows[-1] + 24)))
        if piece.height > self.h and _sides_plain(piece):
            # a little too tall, on a plain background: shrink it slightly onto one page
            self._save(_fit_single(piece, self.w, self.h))
            return
        while piece.height > self.h:
            cut, nxt = _find_cut(piece, self.h)
            self._save(_bottom_padded(piece.crop((0, 0, self.w, cut)), self.w, self.h))
            piece = piece.crop((0, max(1, nxt), self.w, piece.height))
        self._save(_bottom_padded(piece, self.w, self.h))

    def add(self, src):
        with Image.open(src) as opened:  # closed right away so Windows can delete files later
            opened.load()
            im = _page_to_rgb_or_gray(opened, self.gray)
        if im.height / im.width <= STRIP:  # a normal page
            self.flush()
            self._save(_fit_single(im, self.w, self.h))
            return
        new_h = max(1, round(im.height * self.w / im.width))
        im = im.resize((self.w, new_h), Image.LANCZOS)
        joined = im if self.buf is None else _vjoin(self.buf, im)
        self.buf = _squeeze_gaps(joined, max(60, int(self.h * 0.08)))
        self._cut_pages(int(self.h * 2.5))


def make_pages(src, tmp_dir, start_no, width, height, gray):
    """One picture on its own turned into screen-sized pages (used by tests)."""
    p = _Pager(tmp_dir, width, height, gray, start_no)
    p.add(src)
    p.flush()
    return p.pages


def _xml(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _write_epub(pages, dest, title):
    """A picture book EPUB: every page is one full-screen picture, shown the same way in
    Kobo, Apple Books, Google Play Books, PocketBook, Boox and most EPUB readers."""
    import hashlib
    from datetime import datetime, timezone
    with Image.open(pages[0]) as first:
        w, h = first.size
    t = _xml(title)
    book_id = "urn:uuid:" + _uuid_from(hashlib.sha1((title + str(len(pages))).encode()).hexdigest())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    items, spine = [], []
    for i in range(1, len(pages) + 1):
        cover = ' properties="cover-image"' if i == 1 else ""
        items.append(f'<item id="img{i:04d}" href="Images/{i:04d}.jpg" '
                     f'media-type="image/jpeg"{cover}/>')
        items.append(f'<item id="p{i:04d}" href="Text/{i:04d}.xhtml" '
                     f'media-type="application/xhtml+xml" properties="svg"/>')
        spine.append(f'<itemref idref="p{i:04d}"/>')
    opf = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">\n'
           f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
           f'<dc:identifier id="BookId">{book_id}</dc:identifier>\n'
           f'<dc:title>{t}</dc:title>\n<dc:language>en</dc:language>\n'
           f'<meta property="dcterms:modified">{now}</meta>\n'
           f'<meta property="rendition:layout">pre-paginated</meta>\n'
           f'<meta property="rendition:spread">none</meta>\n'
           f'<meta property="rendition:orientation">portrait</meta>\n'
           f'<meta name="cover" content="img0001"/>\n'
           f'<meta name="fixed-layout" content="true"/>\n'
           f'<meta name="original-resolution" content="{w}x{h}"/>\n'
           f'<meta name="book-type" content="comic"/>\n'
           f'</metadata>\n<manifest>\n'
           f'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
           f'<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
           f'<item id="css" href="style.css" media-type="text/css"/>\n'
           + "\n".join(items) + '\n</manifest>\n<spine toc="ncx">\n' + "\n".join(spine)
           + "\n</spine>\n</package>\n")
    nav = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
           '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
           f'<head><title>{t}</title></head><body><nav epub:type="toc"><ol>'
           f'<li><a href="Text/0001.xhtml">{t}</a></li></ol></nav></body></html>')
    toc = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           f'<head><meta name="dtb:uid" content="{book_id}"/></head>'
           f'<docTitle><text>{t}</text></docTitle><navMap>'
           f'<navPoint id="n1" playOrder="1"><navLabel><text>{t}</text></navLabel>'
           '<content src="Text/0001.xhtml"/></navPoint></navMap></ncx>')
    css = ("@page{margin:0}html,body{margin:0;padding:0;height:100%;width:100%;"
           "overflow:hidden}svg{display:block;margin:0;padding:0}")
    container = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                 'media-type="application/oebps-package+xml"/></rootfiles></container>')
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)  # must be first and not compressed
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/toc.ncx", toc)
        z.writestr("OEBPS/style.css", css)
        for i, p in enumerate(pages, 1):
            z.write(p, f"OEBPS/Images/{i:04d}.jpg", compress_type=zipfile.ZIP_STORED)
            z.writestr(
                f"OEBPS/Text/{i:04d}.xhtml",
                '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
                f'<head><title>{t} - {i}</title>'
                f'<meta name="viewport" content="width={w}, height={h}"/>'
                '<link rel="stylesheet" type="text/css" href="../style.css"/></head><body>'
                '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'version="1.1" width="100%" height="100%" viewBox="0 0 {w} {h}" '
                'preserveAspectRatio="xMidYMid meet">'
                f'<image width="{w}" height="{h}" xlink:href="../Images/{i:04d}.jpg"/></svg>'
                '</body></html>')


def _uuid_from(hexdigest):
    h = hexdigest[:32]
    return f"{h[:8]}-{h[8:12]}-5{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def _write_device_file(pages, dest, ext, title="Comic"):
    if ext == ".epub":
        _write_epub(pages, dest, title)
    elif ext == ".cbz":
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as z:
            for i, p in enumerate(pages, 1):
                z.write(p, f"{i:04d}.jpg")
    else:  # .pdf
        imgs = [Image.open(p) for p in pages]
        try:
            imgs[0].save(dest, "PDF", save_all=True, append_images=imgs[1:], resolution=300.0)
        finally:
            for i in imgs:
                i.close()


def build_device_files(out_root, title, total, size, device_key, progress=None, stop=None,
                       custom=None, cover=None, epub=False):
    """Turn each downloaded 'Pages A-B' folder into the gadget's own file (.cbz or .pdf) and,
    if epub is True, also an .epub file next to it. The downloaded images are never changed.
    If a cover picture is given it becomes page 1 of every file.
    Returns (list_of_files_made, list_of_images_that_could_not_be_used)."""
    if not HAS_PIL:
        raise RuntimeError("The picture tools are missing from this copy of the program.")
    stop = stop or threading.Event()
    dev = resolve_device(device_key, custom)
    width, height = dev["size"]
    out_dir = os.path.join(out_root, dev["folder"])
    os.makedirs(out_dir, exist_ok=True)
    exts = [dev["ext"]] + ([".epub"] if epub and dev["ext"] != ".epub" else [])
    groups = math.ceil(total / size)
    made, problems = [], []
    for g in range(groups):
        if stop.is_set():
            raise Stopped()
        first = g * size + 1
        name = group_folder_name(title, first, total, size)
        folder = os.path.join(out_root, name)
        if not os.path.isdir(folder):
            continue
        files = sorted(f for f in os.listdir(folder)
                       if f.lower().endswith(IMG_EXT) and f.lower() != covers.COVER_NAME)
        if progress:
            progress(g, groups, f"Making files for your e-reader: {g + 1} of {groups}")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            pager = _Pager(tmp, width, height, dev["gray"])
            if cover:
                pager.pages.append(covers.fit_cover(cover, width, height, dev["gray"],
                                                    os.path.join(tmp, "cover_page.jpg")))
            for f in files:
                if stop.is_set():
                    raise Stopped()
                try:
                    pager.add(os.path.join(folder, f))
                except Exception:
                    problems.append(f"{name}/{f}")
            pager.flush()
            if not pager.pages:
                continue
            for ext in exts:
                dest = os.path.join(out_dir, name + ext)
                _write_device_file(pager.pages, dest, ext, name)
                made.append(dest)
    if progress:
        progress(groups, groups, "E-reader files are ready.")
    return made, problems


def selftest_device():
    """Used by the build to prove the packaged app can make every file type."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        src = os.path.join(d, "x.png")
        Image.new("RGB", (400, 1500), "white").save(src)
        for ext in (".cbz", ".pdf", ".epub"):
            pages = make_pages(src, d, 0, 1072, 1448, ext == ".pdf")
            if not pages:  # an all-white picture has nothing to show: use a real one
                im = Image.new("RGB", (400, 1500), "white")
                im.paste((0, 0, 0), (50, 200, 350, 900))
                im.save(src)
                pages = make_pages(src, d, 0, 1072, 1448, ext == ".pdf")
            dest = os.path.join(d, "t" + ext)
            _write_device_file(pages, dest, ext, "Test")
            if os.path.getsize(dest) < 100:
                raise RuntimeError("empty " + ext)
