"""Core logic for Comic Downloader (no window code here, so it can be tested alone)."""
import os
import re
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from PIL import Image  # optional: only used for WebP -> JPG
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
