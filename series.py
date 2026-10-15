"""Series logic for Comic Series Downloader (no window code, so it can be tested alone).

Give it the link of a page that lists many chapters. It finds the chapters, then for each one:
download -> hide promo -> cover -> make the gadget's file(s). It remembers what is finished,
so running it again only does the new or unfinished chapters.
It reuses the proven v11 engine in core.py / cleaner.py / covers.py unchanged."""
import json
import os
import re
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
    while page <= last and page <= 200:
        data = json.loads(fetch_text(
            f"{api}/chapter/query?page={page}&perPage=30&query=&order=desc&series_id={m.group(1)}"))
        meta = data.get("meta") or {}
        total = meta.get("total", total)
        last = meta.get("last_page", 1) or 1
        for ch in data.get("data") or []:
            cs = ch.get("chapter_slug")
            if not cs or ch.get("price"):   # a paid chapter cannot be downloaded
                continue
            ss = (ch.get("series") or {}).get("series_slug") or slug
            urls.append(f"{u.scheme}://{u.netloc}/series/{ss}/{cs}")
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
        "device": opts.get("device"), "epub": bool(opts.get("epub")), "size": opts.get("size"),
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


def do_chapter(url, name, series_dir, opts, progress, stop, say, inspect):
    """Everything for one chapter. Returns the number of pages. Raises on any problem."""
    info = _inspect_with_retry(inspect, url, stop)
    imgs = info["images"]
    if not imgs:
        raise core.NoImages()
    say(f"  {len(imgs)} pages found.")
    size = opts["size"]
    failed = core.download_images(imgs, name, series_dir, url, progress, stop, size,
                                  opts.get("convert", False))
    if failed:
        raise ChapterFailed(f"pages {failed} did not download")
    words = opts.get("words")
    if words:
        try:
            c = cleaner.clean_chapter(series_dir, name, len(imgs), size, words, progress, stop)
            hidden = c["cut"] + c["blurred"] + c["deleted"]
            if c["scanned"]:
                say(f"  Promo hidden on {hidden} of {c['scanned']} page(s).")
        except core.Stopped:
            raise
        except Exception as e:
            say(f"  Could not look for the promo words ({e}). Continuing without it.")
    cover = opts.get("cover")
    if cover:
        try:
            covers.apply_folder_covers(series_dir, name, len(imgs), size, cover)
        except Exception as e:
            say(f"  Could not add the cover to the folders ({e}).")
    device = opts.get("device", "images")
    target = device if device != "images" else ("epub_only" if opts.get("epub") else None)
    if target:
        _made, bad = core.build_device_files(series_dir, name, len(imgs), size, target, progress,
                                             stop, opts.get("custom"), cover,
                                             epub=bool(opts.get("epub")))
        if bad:
            say(f"  {len(bad)} image(s) could not be used and were skipped.")
    return len(imgs)


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
                pages = do_chapter(u, name, series_dir, opts, prog, stop, say, inspect)
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
