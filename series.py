"""Series logic for Comic Series Downloader (no window code, so it can be tested alone).

Give it the link of a page that lists many chapters. It finds the chapters, then for each one:
download -> hide promo -> cover -> make the gadget's file(s). It remembers what is finished,
so running it again only does the new or unfinished chapters.
It reuses the proven v11 engine in core.py / cleaner.py / covers.py unchanged."""
import json
import math
import os
import re
import shutil
import tempfile
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import cleaner
import core
import covers

STATE_NAME = ".series-state.json"
CHAPTER_TEXT = re.compile(r"^(chapter|chap\.?|ch\.?|episode|ep\.?)\s*\d", re.I)
SCRIPT_PATH = re.compile(r"[\"'](/[^\"'\s<>\\]*chapter[^\"'\s<>\\]*)[\"']", re.I)


class _Links(HTMLParser):
    """Like core._Page but also keeps the words written on each link."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []         # (href, text)
        self.scripts = []
        self.title = ""
        self.og_title = ""
        self._href = None
        self._text = []
        self._in_title = False
        self._in_script = False

    def _flush(self):
        if self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "a" and a.get("href"):
            self._flush()
            self._href = a["href"].strip()
        elif tag == "meta" and a.get("property") == "og:title":
            self.og_title = a.get("content", "").strip()
        elif tag == "title":
            self._in_title = True
        elif tag == "script":
            self._in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "a":
            self._flush()
        elif tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_script and self.scripts:
            self.scripts[-1] += data
        elif self._href is not None:
            self._text.append(data)

    def close(self):
        super().close()
        self._flush()


def chapter_number(url):
    """The chapter number hidden in the last part of the link, or None."""
    last = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    m = re.findall(r"\d+(?:[.-]\d+)?", last)
    return float(m[-1].replace("-", ".")) if m else None


def find_chapters(parsed, base_url):
    """Chapter links on a series page, oldest first. Returns a list of URLs."""
    host = urlparse(base_url).netloc
    base_path = urlparse(base_url).path.rstrip("/")
    cand, seen = [], set()

    def add(href):
        u = urljoin(base_url, href).split("#")[0]
        p = urlparse(u)
        if p.netloc != host or u in seen or u.rstrip("/") == base_url.rstrip("/"):
            return
        seen.add(u)
        cand.append(u)

    for href, text in parsed.links:
        path = urlparse(urljoin(base_url, href)).path.lower()
        if "chapter" in path or CHAPTER_TEXT.match(text or ""):
            add(href)
    if len(cand) < 2:  # pages drawn by script keep their links inside the page's data
        for s in parsed.scripts:
            for m in SCRIPT_PATH.finditer(core._unescape_js(s)):
                add(m.group(1))

    # A sidebar may list other series' chapters: keep the ones under this series' address.
    if base_path:
        mine = [u for u in cand if urlparse(u).path.startswith(base_path + "/")]
        if len(mine) >= 2:
            cand = mine

    nums = [chapter_number(u) for u in cand]
    if cand and all(n is not None for n in nums):
        best = {}
        for n, u in zip(nums, cand):
            best.setdefault(n, u)  # the same number twice: keep the first link
        return [best[n] for n in sorted(best)]
    cand.reverse()  # most sites list the newest chapter first
    return cand


SERIES_ID = re.compile(r'series_id\\*"\s*:\s*(\d+)')


def _chapters_from_api(url, html, fetch_text, api_base=None):
    """Sites like luacomic.org fill the chapter list in after the page opens, from their own
    server. The page source holds the series number; the server returns 30 chapters a page.
    Returns (urls oldest first, total the site reports) or None if this is not such a site."""
    m = SERIES_ID.search(core._unescape_js(html).replace('\\"', '"')) or SERIES_ID.search(html)
    if not m:
        return None
    u = urlparse(url)
    host = u.netloc[4:] if u.netloc.startswith("www.") else u.netloc
    api = api_base or f"{u.scheme}://api.{host}"
    slug = u.path.rstrip("/").rsplit("/", 1)[-1]
    urls, total, page, last = [], None, 1, 1
    while page <= 300:
        data = json.loads(fetch_text(
            f"{api}/chapter/query?page={page}&perPage=30&query=&order=desc&series_id={m.group(1)}"))
        meta = data.get("meta") or {}
        total = meta.get("total", total)
        last = meta.get("last_page") or 0
        rows = data.get("data") or []
        before = len(urls)
        for ch in rows:
            cs = ch.get("chapter_slug")
            if not cs or ch.get("price"):   # a paid chapter cannot be downloaded
                continue
            ss = (ch.get("series") or {}).get("series_slug") or slug
            urls.append(f"{u.scheme}://{u.netloc}/series/{ss}/{cs}")
        # any number of chapters and pages: stop when the site runs out, not at a fixed count
        if not rows or (last and page >= last) or (not last and len(rows) < 30 and before == len(urls)):
            break
        page += 1
    return urls, total


def _sort_chapters(urls):
    seen = list(dict.fromkeys(urls))
    nums = [chapter_number(x) for x in seen]
    if seen and all(n is not None for n in nums):
        best = {}
        for n, x in zip(nums, seen):
            best.setdefault(n, x)
        return [best[n] for n in sorted(best)]
    return list(reversed(seen))


def inspect_series(url, fetch_text=None, api_base=None):
    """Read the series page. Returns {'title': str, 'chapters': [urls oldest first],
    'total': number the site says it has, or None}."""
    ft = fetch_text or core.fetch_text
    html = ft(url)
    p = _Links()
    p.feed(html)
    p.close()
    title = core.clean_title(p.og_title or p.title, "Series")
    try:
        got = _chapters_from_api(url, html, ft, api_base)
    except Exception:
        got = None
    if got and got[0]:
        return {"title": title, "chapters": _sort_chapters(got[0]), "total": got[1]}
    chapters = find_chapters(p, url)
    # Some sites show the chapter list over several pages (?page=2 ...). Best effort.
    if any("page=" in h for h, _t in p.links):
        for n in range(2, 40):
            sep = "&" if "?" in url else "?"
            try:
                q = _Links()
                q.feed(ft(f"{url}{sep}page={n}"))
                q.close()
            except Exception:
                break
            more = [c for c in find_chapters(q, url) if c not in chapters]
            if not more:
                break
            chapters = _sort_chapters(chapters + more)
    return {"title": title, "chapters": chapters, "total": None}


def chapter_names(series_title, urls):
    """Folder names like 'Series - Chapter 012' (or by list position when links have no numbers)."""
    nums = [chapter_number(u) for u in urls]
    use_nums = all(n is not None for n in nums) and len(set(nums)) == len(nums)
    out = []
    for i, (u, n) in enumerate(zip(urls, nums), 1):
        if use_nums:
            label = f"{int(n):03d}" if n == int(n) else f"{int(n):03d}.{str(n).split('.')[1]}"
        else:
            label = f"{i:03d}"
        out.append(f"{series_title} - Chapter {label}")
    return out


# ----- remembering what is finished -----
def load_state(series_dir):
    try:
        with open(os.path.join(series_dir, STATE_NAME), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"done": {}}


def save_state(series_dir, state):
    tmp = os.path.join(series_dir, STATE_NAME + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, os.path.join(series_dir, STATE_NAME))


def signature(opts):
    """What the finished files depend on. If it changes, the chapter is made again."""
    return json.dumps({
        "layout": opts.get("layout", "one"), "badge": bool(opts.get("badge")), "fit": opts.get("fit", "new"), "device": opts.get("device"), "epub": bool(opts.get("epub")), "size": opts.get("size"),
        "convert": bool(opts.get("convert")), "custom": opts.get("custom"),
        "cover": os.path.basename(opts["cover"]) if opts.get("cover") else None,
        "words": sorted(opts.get("words") or [])}, sort_keys=True)


class ChapterFailed(Exception):
    pass


def _inspect_with_retry(inspect, url, stop, tries=3):
    last = None
    for k in range(tries):
        if stop.is_set():
            raise core.Stopped()
        try:
            return inspect(url)
        except Exception as e:
            last = e
            time.sleep(1.5 * (k + 1))
    raise last



# ----- window size memory (its own file, so the old Comic Downloader is not affected) -----
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".comic_series_downloader.json")
_GEO = re.compile(r"^(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?$")


def load_settings(path=None):
    try:
        with open(path or SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data, path=None):
    try:
        with open(path or SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass  # remembering the size is only a nicety


def fit_geometry(saved, screen_w, screen_h, default=(760, 900), minimum=(700, 560)):
    """The window size/position to open with: the remembered one if it still fits this
    screen, otherwise a size that fits (never taller than the screen)."""
    max_h = max(minimum[1], screen_h - 90)
    m = _GEO.match(saved or "")
    if not m:
        return f"{min(default[0], screen_w)}x{min(default[1], max_h)}"
    w = min(max(int(m.group(1)), minimum[0]), screen_w)
    h = min(max(int(m.group(2)), minimum[1]), max_h)
    if m.group(3) is not None:
        x, y = int(m.group(3)), int(m.group(4))
        if -w + 120 < x < screen_w - 120 and 0 <= y < screen_h - 120:
            return f"{w}x{h}{x:+d}{y:+d}"
    return f"{w}x{h}"


# ----- chapter number on the cover -----
def badge_text(name):
    """'Series - Chapter 052' -> '#52'  (None when the name has no chapter number)."""
    m = re.search(r"Chapter\s+(\d+)(?:\.(\d+))?\s*$", name)
    if not m:
        return None
    return f"#{int(m.group(1))}" + (f".{m.group(2)}" if m.group(2) else "")


_FONTS = ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
          "/System/Library/Fonts/Supplemental/Arial Black.ttf",
          "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf")


def _badge_font(px):
    from PIL import ImageFont
    for f in _FONTS:
        try:
            return ImageFont.truetype(f, px)
        except Exception:
            continue
    try:
        return ImageFont.load_default(px)
    except Exception:
        return ImageFont.load_default()


def stamp_cover(cover_path, text, out_path):
    """The cover picture with the chapter number in the upper right corner: bold dark
    numbers with a white edge, readable on any picture, about 7% of the cover's height."""
    from PIL import Image, ImageDraw
    im = covers.load_cover(cover_path).convert("RGB")
    w, h = im.size
    px = max(16, int(h * 0.07))
    font = _badge_font(px)
    d = ImageDraw.Draw(im)
    edge = max(2, px // 7)
    box = d.textbbox((0, 0), text, font=font, stroke_width=edge)
    while box[2] - box[0] > w * 0.4 and px > 12:   # long numbers like #112.5 stay modest
        px -= 2
        font = _badge_font(px)
        edge = max(2, px // 7)
        box = d.textbbox((0, 0), text, font=font, stroke_width=edge)
    margin = int(w * 0.05)
    xy = (w - margin - (box[2] - box[0]) - box[0], margin - box[1])
    d.text(xy, text, font=font, fill=(255, 255, 255), stroke_width=edge, stroke_fill=(255, 255, 255))
    d.text(xy, text, font=font, fill=(25, 25, 60), stroke_width=max(1, px // 28),
           stroke_fill=(25, 25, 60))
    im.save(out_path, "PNG")
    return out_path


LAYOUTS = {"one": "Sample 1", "parts": "Sample 2"}


def chapter_folder(name, series_title):
    """'Series - Chapter 012' -> 'Chapter 012' (the folder of that chapter)."""
    pre = f"{series_title} - "
    return name[len(pre):] if name.startswith(pre) else name


def layout_preview(layout, series_title, ext, epub, size):
    """A little picture of the folders, shown in the window before downloading."""
    t = series_title or "Series name"
    files = ([f"{{n}}{ext}"] if ext else []) + ([f"{{n}}.epub"] if epub and ext != ".epub" else [])
    one = layout != "parts"
    lines = [f"{t}/", "  Chapter 001/"]
    if one:
        lines.append("    001.webp  002.webp  003.webp ...")
        lines += ["    " + f.format(n=f"{t} - Chapter 001") for f in files]
    else:
        lines.append("    Pages/  (001.webp 002.webp ... all the pictures)")
        for a, b in ((1, size), (size + 1, size * 2)):
            lines += ["    " + f.format(n=f"{t} - Chapter 001 - Pages {a}-{b}") for f in files]
        if files:
            lines.append("    ...")
    lines += ["  Chapter 002/", "    ...", "  Chapter 003/ ..."]
    return "\n".join(lines)


def _finish_layout(work_root, name, total, size, series_dir, folder, layout, device_folder, cover):
    """Move the finished work out of the hidden work area into the chapter's own folder."""
    final = os.path.join(series_dir, folder)
    if os.path.isdir(final):
        shutil.rmtree(final)  # an older copy of this chapter made by this program
    os.makedirs(final)
    pages_dir = final if layout == "one" else os.path.join(final, "Pages")
    os.makedirs(pages_dir, exist_ok=True)
    for g in range(math.ceil(total / size)):
        gf = os.path.join(work_root, core.group_folder_name(name, g * size + 1, total, size))
        if not os.path.isdir(gf):
            continue
        for f in sorted(os.listdir(gf)):
            if f.lower().endswith(core.IMG_EXT) and f.lower() != covers.COVER_NAME:
                os.replace(os.path.join(gf, f), os.path.join(pages_dir, f))
        shutil.rmtree(gf, ignore_errors=True)
    dev = os.path.join(work_root, device_folder) if device_folder else None
    if dev and os.path.isdir(dev):
        for f in sorted(os.listdir(dev)):
            base, ext = os.path.splitext(f)
            if layout == "one" and base == core.group_folder_name(name, 1, total, total):
                f2 = name + ext  # one file per chapter: no "Pages 1-40" in its name
            else:
                f2 = f
            os.replace(os.path.join(dev, f), os.path.join(final, f2))
        shutil.rmtree(dev, ignore_errors=True)
    if cover:
        try:
            covers.save_folder_cover(final, cover)
            covers.set_folder_icon(final, cover)
        except Exception:
            pass  # the thumbnail is only a nicety
    try:
        os.rmdir(work_root)  # only succeeds when empty
    except OSError:
        pass
    return final


def do_chapter(url, name, series_dir, opts, progress, stop, say, inspect, series_title=""):
    """Everything for one chapter. Returns the number of pages. Raises on any problem."""
    info = _inspect_with_retry(inspect, url, stop)
    imgs = info["images"]
    if not imgs:
        raise core.NoImages()
    say(f"  {len(imgs)} pages found.")
    layout = opts.get("layout", "one")
    total = len(imgs)
    size = total if layout == "one" else max(1, opts["size"])   # Sample 1: the whole chapter is one part
    work = os.path.join(series_dir, ".work")                    # hidden work area, tidied afterwards
    failed = core.download_images(imgs, name, work, url, progress, stop, size,
                                  opts.get("convert", False))
    if failed:
        raise ChapterFailed(f"pages {failed} did not download")
    words = opts.get("words")
    if words:
        try:
            c = cleaner.clean_chapter(work, name, total, size, words, progress, stop)
            hidden = c["cut"] + c["blurred"] + c["deleted"]
            if c["scanned"]:
                say(f"  Promo hidden on {hidden} of {c['scanned']} page(s).")
        except core.Stopped:
            raise
        except Exception as e:
            say(f"  Could not look for the promo words ({e}). Continuing without it.")
    cover = opts.get("cover")
    tmp = tempfile.mkdtemp(prefix="csd_")
    try:
        if cover and opts.get("badge", True):
            txt = badge_text(name)
            if txt:
                try:
                    cover = stamp_cover(cover, txt, os.path.join(tmp, "cover.png"))
                except Exception as e:
                    say(f"  Could not put the chapter number on the cover ({e}).")
        device = opts.get("device", "images")
        target = device if device != "images" else ("epub_only" if opts.get("epub") else None)
        device_folder = None
        if target:
            build = core.build_device_files
            if opts.get("fit", "new") == "new":
                import fitpage            # TEST: snug fit, whole scenes per screen
                build = fitpage.build_files_fit
            _made, bad = build(work, name, total, size, target, progress, stop,
                               opts.get("custom"), cover, epub=bool(opts.get("epub")))
            device_folder = core.resolve_device(target, opts.get("custom"))["folder"]
            if bad:
                say(f"  {len(bad)} image(s) could not be used and were skipped.")
        _finish_layout(work, name, total, size, series_dir, chapter_folder(name, series_title),
                       layout, device_folder, cover)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return total


def run_series(series_title, chapter_urls, out_root, opts, progress=None, stop=None, say=None,
               inspect=None, pause=1.0):
    """Do every chapter in order. One bad chapter never stops the rest.
    Returns {'done': [...], 'skipped': [...], 'failed': [(name, reason), ...], 'dir': path}."""
    import threading
    stop = stop or threading.Event()
    say = say or (lambda m: None)
    progress = progress or (lambda d, t, s: None)
    inspect = inspect or core.inspect_page
    series_dir = os.path.join(out_root, series_title)
    os.makedirs(series_dir, exist_ok=True)
    state = load_state(series_dir)
    sig = signature(opts)
    names = dict(zip(chapter_urls, chapter_names(series_title, chapter_urls)))
    # numbering must not depend on which chapters were ticked
    all_urls = opts.get("all_urls") or chapter_urls
    names.update(zip(all_urls, chapter_names(series_title, all_urls)))
    result = {"done": [], "skipped": [], "failed": [], "dir": series_dir}
    todo = []
    for u in chapter_urls:
        rec = state["done"].get(u)
        if rec and rec.get("sig") == sig and not opts.get("redo"):
            result["skipped"].append(names[u])
        else:
            todo.append(u)
    if result["skipped"]:
        say(f"Skipping {len(result['skipped'])} chapter(s) that are already finished.")

    def one_pass(urls, label):
        failed = []
        n = len(urls)
        for k, u in enumerate(urls, 1):
            if stop.is_set():
                raise core.Stopped()
            name = names[u]
            say(f"{label} {k} of {n}: {name}")

            def prog(d, t, s, k=k, n=n):
                progress(d, t, f"[{k}/{n}] {s}")
            try:
                pages = do_chapter(u, name, series_dir, opts, prog, stop, say, inspect, series_title)
                state["done"][u] = {"name": name, "pages": pages, "sig": sig}
                save_state(series_dir, state)
                result["done"].append(name)
                say(f"  Done: {name}")
            except core.Stopped:
                raise
            except Exception as e:
                reason = str(e) or e.__class__.__name__
                if isinstance(e, core.NoImages):
                    reason = "no images found on that chapter page"
                say(f"  Problem with {name}: {reason}")
                failed.append((u, name, reason))
            if k < n:
                time.sleep(pause)
        return failed

    failed = one_pass(todo, "Chapter") if todo else []
    if failed:
        say(f"Trying {len(failed)} problem chapter(s) once more...")
        time.sleep(min(5, pause * 5))
        failed = one_pass([u for u, _n, _r in failed], "Retry")
    result["failed"] = [(n, r) for _u, n, r in failed]
    return result
