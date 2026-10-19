"""Series logic for Comic Series GOKU Downloader (no window code, so it can be tested alone).

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
TEXT_NUMBER = re.compile(r"^(?:chapter|chap\.?|ch\.?|episode|ep\.?)\s*(\d+(?:\.\d+)?)", re.I)
LOCK_ICON = re.compile(r"[:/_-]lock(?:ed)?\b", re.I)    # 'lock.svg', 'icon-locked' (not 'unlock')
NUMBER_TAG = re.compile(r"^chapter-(\d+(?:\.\d+)?)$")


class _Links(HTMLParser):
    """Like core._Page but also keeps the words written on each link."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []         # (href, text)
        self.locked = set()     # hrefs of links showing a lock (coin / paid chapters)
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
        elif tag == "img" and self._href is not None and LOCK_ICON.search(a.get("src", "")):
            self.locked.add(self._href)
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
    """The chapter number hidden in the last part of the link, or None.
    Links whose address is only a code (timelesstoons.org: /chapter/652b2080e4d-65e2be0202a/)
    carry the number from the link's words as '#chapter-14'; the website never sees that part."""
    tag = NUMBER_TAG.match(urlparse(url).fragment)
    if tag:
        return float(tag.group(1))
    last = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    m = re.findall(r"\d+(?:[.-]\d+)?", last)
    return float(m[-1].replace("-", ".")) if m else None


def _text_numbers(parsed, base_url):
    """{link: chapter number written on it} ('Chapter 13.5' -> 13.5). A link may appear
    several times (a 'Start Reading' button, then 'Chapter 1' in the list): any one with words counts."""
    out = {}
    for href, text in parsed.links:
        m = TEXT_NUMBER.match(text or "")
        if m:
            out.setdefault(urljoin(base_url, href).split("#")[0], float(m.group(1)))
    return out


def find_chapters(parsed, base_url, locked=None):
    """Chapter links on a series page, oldest first. Returns a list of URLs.
    Chapters showing a lock (paid with coins) are left out and put in `locked` if given."""
    host = urlparse(base_url).netloc
    base_path = urlparse(base_url).path.rstrip("/")
    cand, seen = [], set()
    shut = {urljoin(base_url, h).split("#")[0] for h in getattr(parsed, "locked", ())}
    words = _text_numbers(parsed, base_url)

    def add(href):
        u = urljoin(base_url, href).split("#")[0]
        p = urlparse(u)
        if p.netloc != host or u in seen or u.rstrip("/") == base_url.rstrip("/"):
            return
        seen.add(u)
        if u in shut:
            if locked is not None:
                n = words.get(u)
                locked.append(u + (f"#chapter-{n:g}" if n is not None else ""))
            return
        n = words.get(u)
        if n is not None and chapter_number(u) != n:   # the address has no real number: use the words
            u += f"#chapter-{n:g}"
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
    locked = []
    chapters = find_chapters(p, url, locked)
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
            more = [c for c in find_chapters(q, url, locked) if c not in chapters]
            if not more:
                break
            chapters = _sort_chapters(chapters + more)
    shut = sorted({n for n in (chapter_number(u) for u in locked) if n is not None})
    count = len({u.split("#")[0] for u in locked})
    return {"title": title, "chapters": chapters, "locked": shut,
            "total": len(chapters) + count if count else None}


def chapter_range(numbers):
    """[9, 10, 11, 12, 12.5, 13, 13.5, 14] -> '9 to 14' ; [3] -> '3' ; [2, 7] -> '2, 7'."""
    nums = sorted(numbers)
    label = lambda n: f"{n:g}"
    if not nums:
        return ""
    if len(nums) > 2:
        return f"{label(nums[0])} to {label(nums[-1])}"
    return ", ".join(label(n) for n in nums)


# ----- original source site -----
# Copy sites collect chapters from the translation groups and hide behind a bot check
# ("Just a moment...") that this program does not and will not get past. For their links we
# look for the group's own site instead. SOURCE_INDEXES = pages that list every series of a
# site we can read, with each series' names written on it.
AGGREGATORS = ("comix.to",)
SOURCE_INDEXES = ("https://timelesstoons.org/series",)


def site_name(url):
    """'https://www.timelesstoons.org/series/x/' -> 'timelesstoons.org' ('' if not a web address)."""
    host = urlparse((url or "").strip()).netloc.lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def is_aggregator(url):
    host = site_name(url)
    return any(host == a or host.endswith("." + a) for a in AGGREGATORS)


def source_label(url):
    """The words shown in the 'Original / Source site' bar for the link in the box."""
    host = site_name(url)
    if not host or not re.match(r"https?://", (url or "").strip(), re.I):
        return "-"
    if is_aggregator(url):
        return f"{host}  (only a copy site: press Find chapters and the original is looked for)"
    return host


def _words(text):
    return " ".join(re.findall(r"[^\W_]+", (text or "").lower()))


def title_from_link(url):
    """The series name written inside a link: .../title/j5ne6-ryuuketsu-megamiden-teikoku-no-musume
    -> 'ryuuketsu megamiden teikoku no musume' (a short leading code with a digit is dropped)."""
    last = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    parts = [p for p in re.split(r"[-_]+", last) if p]
    if len(parts) > 1 and len(parts[0]) <= 8 and re.search(r"\d", parts[0]):
        parts = parts[1:]
    return _words(" ".join(parts))


class _Index(HTMLParser):
    """A site's list of series: every card has the series' names in its title and a link to it."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries = []      # (href, all names written on the card)
        self._names = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "button" and a.get("title"):
            self._names = a["title"]
        elif tag == "a" and re.match(r"^/series/[^/]+/?$", a.get("href", "")):
            self.entries.append((a["href"], self._names or a.get("title", "")))
            self._names = None


def _match_score(want, names):
    """1.0 when the wanted name appears whole in `names`; otherwise the share of its words
    found there (names are spelled differently from site to site: 'Megami-den', 'Megamiden')."""
    have = _words(names)
    if f" {want} " in f" {have} ":
        return 1.0
    squeezed = want.replace(" ", "")
    if len(squeezed) >= 8 and squeezed in have.replace(" ", ""):
        return 0.95
    w, h = want.split(), set(have.split())
    return sum(1 for x in w if x in h) / len(w) if len(w) >= 3 else 0.0


def find_original(url, fetch_text=None, indexes=None, skip_site=None, name=None, say=None):
    """Look for the series named in `url` (or `name`) on the sites we can read, leaving out
    `skip_site`. Returns {'url': series page, 'site': host, 'title': name on that site} or None.
    `say` receives one line per site tried, so a failure can be understood."""
    say = say or (lambda m: None)
    want = _words(name) if name else title_from_link(url)
    if len(want) < 6:
        say(f"  The link holds no usable series name ('{want}').")
        return None
    ft = fetch_text or core.fetch_text
    say(f"  Looking for '{want}'...")
    for index in (indexes or SOURCE_INDEXES):
        site = site_name(index)
        if skip_site and site == skip_site:
            continue
        try:
            p = _Index()
            p.feed(ft(index))
            p.close()
        except Exception as e:
            say(f"  {site}: could not read its series list ({e}).")
            continue
        scored = [(_match_score(want, names), -len(names), href, names) for href, names in p.entries]
        best = max(scored, default=None)
        if best and best[0] >= 0.8:
            say(f"  {site}: found.")
            return {"url": urljoin(index, best[2]), "site": site, "title": best[3]}
        say(f"  {site}: {len(p.entries)} series read, none called that.")
    return None


def search_site(site_url, title, fetch_text=None, say=None):
    """Find a series by name on any group website: tries the usual list and search pages.
    Returns the series page address or None."""
    from urllib.parse import quote_plus
    say = say or (lambda m: None)
    ft = fetch_text or core.fetch_text
    u = urlparse(site_url)
    root = f"{u.scheme}://{u.netloc}"
    q = quote_plus(title)
    want = _words(title)
    for path in ("/series", "/series/?search=" + q, "/manga", f"/?s={q}&post_type=wp-manga",
                 f"/?s={q}", "/search?q=" + q, "/comics", "/"):
        try:
            html = ft(root + path)
        except Exception:
            continue
        idx = _Index()
        idx.feed(html)
        cards = list(idx.entries)
        links = _Links()
        links.feed(html)
        cards += [(h, t) for h, t in links.links
                  if re.search(r"/(series|manga|comic|comics|title|read)/[^/]+/?$", urlparse(h).path)]
        scored = [(_match_score(want, names), -len(names), urljoin(root, h)) for h, names in cards if names]
        best = max(scored, default=None)
        if best and best[0] >= 0.8:
            say(f"  {site_name(root)}: found at {best[2]}")
            return best[2]
    say(f"  {site_name(root)}: could not find it there.")
    return None


# Sites that carry series from many groups and that a program can read. A copy-site link
# (comix.to) is looked up on these by series name; the first one that really lists the
# chapters wins. Add a site here (one line) and every copy-site link will try it too.
# Sites you paste a working link from are remembered and tried as well (see remember_site).
KNOWN_SOURCES = ("https://en-thunderscans.com",)
SLUG_PATHS = ("/comics/{}/", "/series/{}/", "/manga/{}/", "/title/{}/", "/comic/{}/")


def site_root(url):
    u = urlparse((url or "").strip())
    return f"{u.scheme}://{u.netloc}" if u.scheme in ("http", "https") and u.netloc else ""


def remember_site(url, known=()):
    """The site root to add to the remembered list after a link on it worked, or '' when it
    is a copy site, already known, or not a web address."""
    root = site_root(url)
    have = {site_name(k) for k in list(KNOWN_SOURCES) + list(known)}
    if not root or is_aggregator(url) or site_name(root) in have:
        return ""
    return root


def probe_site(root, title, fetch_text=None, say=None):
    """Open the series page a site would use for `title` (its name written as a link: the-title-words)
    and accept it only when it really lists chapters. Returns the page address or None."""
    say = say or (lambda m: None)
    words = _words(title).split()
    slugs = ["-".join(words)] + (["-".join(words[1:])] if words[:1] == ["the"] and len(words) > 3 else [])
    for slug in slugs:
        for path in SLUG_PATHS:
            page = root + path.format(slug)
            try:
                info = inspect_series(page, fetch_text=fetch_text)
            except Exception:
                continue
            if len(info["chapters"]) >= 2:
                say(f"  {site_name(root)}: found it at {page} ({len(info['chapters'])} chapters).")
                return page
    return None


def find_source(url, say=None, fetch_text=None, indexes=None, known=(), sites=None, name=None):
    """Find the series named in a copy-site link on a site we can read, in order:
    (1) each known/remembered site: the series page by name, then the site's own search,
    (2) the series lists of sites that publish one (timelesstoons.org).
    Every site tried is reported through `say`."""
    say = say or (lambda m: None)
    title = _words(name) if name else title_from_link(url)
    if len(title) < 6:
        say(f"  The link holds no usable series name ('{title}').")
        return None
    say(f"  Looking for '{title}'...")
    for root in (sites if sites is not None else list(KNOWN_SOURCES) + list(known)):
        page = probe_site(root, title, fetch_text=fetch_text, say=say)
        if not page:
            page = search_site(root, title, fetch_text=fetch_text, say=say)
        if page:
            return {"url": page, "site": site_name(page), "title": title}
    return find_original(url, fetch_text=fetch_text, indexes=indexes, name=name, say=say)


UID_ADDRESS = re.compile(r"`(https?://[^`\s$]+/)\$\{uid\}`")
UID_IMG = re.compile(r"<img\b[^>]*?\buid=[\"']([^\"'\s]+)[\"']", re.I)


def inspect_chapter(url, fetch_text=None):
    """A chapter's pictures, in reading order. Like core.inspect_page, and also knows pages
    that only name each picture by a code (<img uid="gus51jGqpjd">) and build the address
    in their script (timelesstoons.org: https://cdn.meowing.org/uploads/${uid})."""
    page = url.split("#")[0]
    html = (fetch_text or core.fetch_text)(page)
    p = core._Page()
    p.feed(html)
    title = core.clean_title(p.og_title or p.title)
    where = UID_ADDRESS.search(html)
    if where:
        uids = list(dict.fromkeys(UID_IMG.findall(html)))
        if uids:
            return {"images": [where.group(1) + u for u in uids], "chapters": [], "title": title}
    return {"images": core.find_images(p, page), "chapters": core.find_chapter_links(p, page),
            "title": title}


def _kind_of(head):
    """The real picture type from the first bytes of the file."""
    if head[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"):
        return ".avif"
    if head[:4] == b"GIF8":
        return ".gif"
    return None


def fix_picture_types(folder, convert=False):
    """Pictures from addresses without a file type were saved as .jpg whatever they really are.
    Give each its true ending (.webp, .avif, ...) and, if "Convert WebP to JPG" is ticked,
    turn WebP/AVIF into real JPG, as the download does for addresses that say .webp."""
    for f in sorted(os.listdir(folder)):
        base, ext = os.path.splitext(f)
        src = os.path.join(folder, f)
        if ext.lower() not in core.IMG_EXT or f.lower() == covers.COVER_NAME:
            continue
        try:
            with open(src, "rb") as fh:
                kind = _kind_of(fh.read(16))
        except OSError:
            continue
        if not kind or kind == ext.lower() or (kind == ".jpg" and ext.lower() == ".jpeg"):
            continue
        if convert and kind in (".webp", ".avif"):
            try:
                from PIL import Image
                tmp = os.path.join(folder, base + ".jpg.part")
                with Image.open(src) as im:
                    im.convert("RGB").save(tmp, "JPEG", quality=92)
                os.replace(tmp, os.path.join(folder, base + ".jpg"))
                if ext.lower() != ".jpg":
                    os.remove(src)
                continue
            except Exception:
                pass   # keep the original picture if it cannot be turned into JPG
        os.replace(src, os.path.join(folder, base + kind))


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


ENGINE = 4   # raise when the page engine improves: older finished chapters are then made again


def is_current(rec):
    """True when a finished chapter was made by the current snug-fit engine."""
    try:
        return json.loads(rec.get("sig", "{}")).get("engine") == ENGINE
    except Exception:
        return False


def signature(opts):
    """What the finished files depend on. If it changes, the chapter is made again."""
    return json.dumps({
        "engine": ENGINE, "layout": opts.get("layout", "one"), "badge": bool(opts.get("badge")), "fit": opts.get("fit", "new"), "device": opts.get("device"), "epub": bool(opts.get("epub")), "size": opts.get("size"),
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


LAYOUTS = {"one": "Sample 1", "parts": "Sample 2", "central": "Layout C"}
PAGES_IN_FOLDER = ("one", "central")   # pictures sit directly in the chapter folder


def chapter_folder(name, series_title):
    """'Series - Chapter 012' -> 'Chapter 012' (the folder of that chapter)."""
    pre = f"{series_title} - "
    return name[len(pre):] if name.startswith(pre) else name


def layout_preview(layout, series_title, ext, epub, size):
    """A little picture of the folders, shown in the window before downloading."""
    t = series_title or "Series name"
    files = ([f"{{n}}{ext}"] if ext else []) + ([f"{{n}}.epub"] if epub and ext != ".epub" else [])
    one = layout != "parts"
    central = layout == "central"
    if central:
        lines = [f"{t}/"]
        for kind, ex in (("EPUB", ".epub"), ) if (epub or ext == ".epub") else ():
            lines += [f"  {t} {kind}/   (all chapters together)",
                      f"    {t} {kind} Chapter 001{ex}", f"    {t} {kind} Chapter 002{ex}", "    ..."]
        if ext and ext != ".epub":
            k = ext.lstrip(".").upper()
            lines += [f"  {t} {k}/", f"    {t} {k} Chapter 001{ext}", f"    {t} {k} Chapter 002{ext}", "    ..."]
        lines += [f"  {t} WEBP/   (or JPEG)", f"    {t} WEBP Chapter 001/  001.webp 002.webp ...",
                  f"    {t} WEBP Chapter 002/  001.webp 002.webp ...", "    ..."]
        return "\n".join(lines)
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


def link_from_file(path):
    """The web address inside a dropped .url (Windows) or .webloc (Mac) shortcut, or a .txt file."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read(20000)
    except Exception:
        return None
    m = re.search(r"URL=(https?://\S+)", text) or re.search(r"<string>\s*(https?://[^<\s]+)", text) \
        or re.search(r"(https?://\S+)", text)
    return m.group(1).strip() if m else None


def classify_drop(items):
    """What was dropped on the window? Returns (kind, value): 'folder', 'cover', 'link' or (None, None)."""
    for p in items:
        p = p.strip()
        if re.match(r"https?://", p, re.I):
            return "link", p.split()[0]
        if os.path.isdir(p):
            return "folder", p
        if os.path.isfile(p):
            if covers.is_cover_file(p):
                return "cover", p
            if os.path.splitext(p)[1].lower() in (".url", ".webloc", ".txt"):
                u = link_from_file(p)
                if u:
                    return "link", u
    return None, None


def _finish_layout(work_root, name, total, size, series_dir, folder, layout, device_folder, cover,
                   series_title=""):
    """Move the finished work out of the hidden work area into the chapter's own folder."""
    if layout == "central":
        return _finish_central(work_root, name, total, size, series_dir, folder, device_folder,
                               cover, series_title)
    final = os.path.join(series_dir, folder)
    if os.path.isdir(final):
        shutil.rmtree(final)  # an older copy of this chapter made by this program
    os.makedirs(final)
    pages_dir = final if layout in PAGES_IN_FOLDER else os.path.join(final, "Pages")
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
            if layout in PAGES_IN_FOLDER and base == core.group_folder_name(name, 1, total, total):
                f2 = name + ext  # one file per chapter: no "Pages 1-40" in its name
            else:
                f2 = f
            if layout == "central" and ext.lower() == ".epub":
                # every EPUB of this title lives in ONE folder, whatever batch of chapters it came from
                title = series_title or os.path.basename(series_dir)
                epub_dir = os.path.join(series_dir, f"{title} EPUB")
                os.makedirs(epub_dir, exist_ok=True)
                os.replace(os.path.join(dev, f), os.path.join(epub_dir, f"{title} EPUB {folder}{ext}"))
                continue
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


def _central_name(series_title, series_dir):
    return series_title or os.path.basename(series_dir)


def _finish_central(work_root, name, total, size, series_dir, folder, device_folder, cover, series_title):
    """Layout C: every kind of file of this title has ONE folder for all chapters:
         <Title> EPUB/  <Title> EPUB Chapter 001.epub ...
         <Title> CBZ/   <Title> CBZ Chapter 001.cbz ...       (or PDF)
         <Title> WEBP/  <Title> WEBP Chapter 001/ 001.webp ...  (or JPEG)
       Later batches of chapters land in the same folders."""
    title = _central_name(series_title, series_dir)
    old = os.path.join(series_dir, folder)
    if os.path.isdir(old):
        shutil.rmtree(old)   # a chapter folder from another layout: this chapter is made again
    dev = os.path.join(work_root, device_folder) if device_folder else None
    if dev and os.path.isdir(dev):
        for f in sorted(os.listdir(dev)):
            ext = os.path.splitext(f)[1]
            kind = ext.lstrip(".").upper()
            kdir = os.path.join(series_dir, f"{title} {kind}")
            os.makedirs(kdir, exist_ok=True)
            os.replace(os.path.join(dev, f), os.path.join(kdir, f"{title} {kind} {folder}{ext}"))
        shutil.rmtree(dev, ignore_errors=True)
    pics, kind = None, "WEBP"
    for g in range(math.ceil(total / size)):
        gf = os.path.join(work_root, core.group_folder_name(name, g * size + 1, total, size))
        if not os.path.isdir(gf):
            continue
        files = sorted(f for f in os.listdir(gf)
                       if f.lower().endswith(core.IMG_EXT) and f.lower() != covers.COVER_NAME)
        if not files:
            continue
        if pics is None:
            ext0 = os.path.splitext(files[0])[1].lower().lstrip(".")
            kind = "JPEG" if ext0 in ("jpg", "jpeg") else ext0.upper()
            kdir = os.path.join(series_dir, f"{title} {kind}")
            pics = os.path.join(kdir, f"{title} {kind} {folder}")
            if os.path.isdir(pics):
                shutil.rmtree(pics)
            os.makedirs(pics)
        for f in files:
            os.replace(os.path.join(gf, f), os.path.join(pics, f))
        shutil.rmtree(gf, ignore_errors=True)
    if pics and cover:
        try:
            covers.save_folder_cover(pics, cover)
            covers.set_folder_icon(pics, cover)
        except Exception:
            pass
    try:
        os.rmdir(work_root)
    except OSError:
        pass
    return pics


_DOUBLE_EXT = re.compile(r"(\.(?:webp|avif|png|jpe?g|gif))\.(?:webp|avif|png|jpe?g|gif)$", re.I)


def dedupe_images(urls):
    """Some pages list each picture twice, e.g. 01.webp.jpg (what the page shows) and 01.webp
    (which may not exist). Keep one of each, the first one listed, in reading order."""
    seen, out = set(), []
    for u in urls:
        key = _DOUBLE_EXT.sub(r"\1", urlparse(u).path.lower())
        key = (urlparse(u).netloc.lower(), key)
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def _download_with_retry(imgs, name, work, url, progress, stop, size, convert, say):
    """Websites sometimes refuse a burst of downloads for a moment. Missing pages are asked for
    again, slower each time (4, then 2, then 1 at a time, with a wait). Pages already saved are kept."""
    failed = []
    for rnd, (workers, wait) in enumerate(((4, 0), (2, 5), (1, 12), (1, 25))):
        if rnd:
            say(f"  {len(failed)} page(s) did not download. Waiting {wait} seconds, then trying again...")
            for _ in range(wait):
                if stop.is_set():
                    raise core.Stopped()
                time.sleep(1)
        failed = core.download_images(imgs, name, work, url, progress, stop, size, convert,
                                      workers=workers)
        if not failed:
            return []
    return failed


def do_chapter(url, name, series_dir, opts, progress, stop, say, inspect, series_title=""):
    """Everything for one chapter. Returns the number of pages. Raises on any problem."""
    info = _inspect_with_retry(inspect, url, stop)
    url = url.split("#")[0]    # '#chapter-14' is only our own label: never sent to the website
    imgs = dedupe_images(info["images"])
    if not imgs:
        raise core.NoImages()
    say(f"  {len(imgs)} pages found.")
    layout = opts.get("layout", "one")
    total = len(imgs)
    size = total if layout in PAGES_IN_FOLDER else max(1, opts["size"])   # Sample 1: the whole chapter is one part
    work = os.path.join(series_dir, ".work")                    # hidden work area, tidied afterwards
    failed = _download_with_retry(imgs, name, work, url, progress, stop, size,
                                  opts.get("convert", False), say)
    if failed:
        why = ""
        try:
            core.fetch(imgs[failed[0] - 1], referer=url, timeout=20)
        except Exception as e:
            why = f" ({e})"
        raise ChapterFailed(f"pages {failed} did not download{why}")
    for g in range(math.ceil(total / size)):
        gf = os.path.join(work, core.group_folder_name(name, g * size + 1, total, size))
        if os.path.isdir(gf):
            fix_picture_types(gf, opts.get("convert", False))
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
            build = core.build_device_files   # "Previous (v4)": the backup page style
            if opts.get("fit", "new") == "new":
                import fitpage            # snug fit (the normal way): whole scenes per screen
                build = fitpage.build_files_fit
            _made, bad = build(work, name, total, size, target, progress, stop,
                               opts.get("custom"), cover, epub=bool(opts.get("epub")))
            if opts.get("fit", "new") == "new":
                n_pages, n_edge = fitpage.LAST_AUDIT
                say(f"  Snug-fit check: {n_pages - n_edge} of {n_pages} screens are clean"
                    + (f"; {n_edge} have art touching the screen edge." if n_edge else "."))
            device_folder = core.resolve_device(target, opts.get("custom"))["folder"]
            if bad:
                say(f"  {len(bad)} image(s) could not be used and were skipped.")
        _finish_layout(work, name, total, size, series_dir, chapter_folder(name, series_title),
                       layout, device_folder, cover, series_title)
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
    inspect = inspect or inspect_chapter
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
