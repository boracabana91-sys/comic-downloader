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
    dev["next"] = _next_text(dev["kind"], dev["ext"], dev["folder"])
    return dev


def _page_to_rgb_or_gray(im, gray):
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.split()[3])
        im = bg
    return im.convert("L" if gray else "RGB")


def _quietest_row(gray_im, lo, hi):
    """Row between lo and hi with the least ink (blank gap between panels or text)."""
    width = gray_im.width
    best_y, best = hi, None
    for y in range(lo, hi):
        s = ImageStat.Stat(gray_im.crop((0, y, width, y + 1))).stddev[0]
        if best is None or s <= best:
            best, best_y = s, y
    return best_y


def make_pages(src, tmp_dir, start_no, width, height, gray):
    """Fit one downloaded image to the screen. Tall strips are cut into screen-sized
    pages at blank rows. Returns the JPEG page files written to tmp_dir."""
    with Image.open(src) as opened:  # closed right away so Windows can delete files later
        opened.load()
        im = _page_to_rgb_or_gray(opened, gray)
    scale = min(width / im.width, 2.0)
    new_w = max(1, round(im.width * scale))
    new_h = max(1, round(im.height * scale))
    im = im.resize((new_w, new_h), Image.LANCZOS)
    lum = im if im.mode == "L" else im.convert("L")

    chunks, y = [], 0
    while True:
        remaining = new_h - y
        if remaining <= height * 1.12:
            chunks.append((y, new_h))
            break
        target = y + height
        lo = max(y + int(height * 0.6), target - int(height * 0.25))
        cut = _quietest_row(lum, lo, target)
        chunks.append((y, cut))
        y = cut

    white = 255 if im.mode == "L" else (255, 255, 255)
    out = []
    for n, (a, b) in enumerate(chunks):
        piece = im.crop((0, a, new_w, b))
        if piece.height > height:  # slightly too tall: shrink to fit
            f = height / piece.height
            piece = piece.resize((max(1, round(piece.width * f)), height), Image.LANCZOS)
        canvas = Image.new(im.mode, (width, height), white)
        canvas.paste(piece, ((width - piece.width) // 2, (height - piece.height) // 2))
        path = os.path.join(tmp_dir, f"p{start_no + n:05d}.jpg")
        canvas.save(path, "JPEG", quality=85, optimize=True)
        out.append(path)
    return out


def _write_device_file(pages, dest, ext):
    if ext == ".cbz":
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
                       custom=None, cover=None):
    """Turn each downloaded 'Pages A-B' folder into one .cbz (Kobo) or .pdf (Kindle).
    If a cover picture is given it becomes page 1 of every file.
    Returns (list_of_files_made, list_of_images_that_could_not_be_used)."""
    if not HAS_PIL:
        raise RuntimeError("The picture tools are missing from this copy of the program.")
    stop = stop or threading.Event()
    dev = resolve_device(device_key, custom)
    width, height = dev["size"]
    out_dir = os.path.join(out_root, dev["folder"])
    os.makedirs(out_dir, exist_ok=True)
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
            pages = []
            if cover:
                pages.append(covers.fit_cover(cover, width, height, dev["gray"],
                                              os.path.join(tmp, "cover_page.jpg")))
            for f in files:
                try:
                    pages += make_pages(os.path.join(folder, f), tmp, len(pages), width, height,
                                        dev["gray"])
                except Exception:
                    problems.append(f"{name}/{f}")
            if not pages:
                continue
            dest = os.path.join(out_dir, name + dev["ext"])
            _write_device_file(pages, dest, dev["ext"])
            made.append(dest)
    if progress:
        progress(groups, groups, "E-reader files are ready.")
    return made, problems


def selftest_device():
    """Used by the build to prove the packaged app can make both file types."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        src = os.path.join(d, "x.png")
        Image.new("RGB", (400, 1500), "white").save(src)
        for ext in (".cbz", ".pdf"):
            pages = make_pages(src, d, 0, 1072, 1448, ext == ".pdf")
            dest = os.path.join(d, "t" + ext)
            _write_device_file(pages, dest, ext)
            if os.path.getsize(dest) < 100:
                raise RuntimeError("empty " + ext)
