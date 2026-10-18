"""EBZ CNVRTR engine (no window code here, so it can be tested on its own).

Pictures / PDF / CBZ / folders  ->  books  ->  snug-fit pages for each chosen device
->  .cbz + .epub (and .pdf where the device needs it).

The page fitting itself is fitpage.FitPager, unchanged from Comic Series Downloader."""
import os
import re
import shutil
import tempfile
import threading
import zipfile

import numpy as np

from PIL import Image, ImageOps

import bookfiles
import coverart
import devices
import fitpage
import pagecore

Image.MAX_IMAGE_PIXELS = 400_000_000   # long webtoon strips are big but safe

try:   # iPhone photos (.heic); optional, the program still works without it
    import pillow_heif
    pillow_heif.register_heif_opener()
    HAS_HEIF = True
except Exception:
    HAS_HEIF = False

IMG_EXT = (".jpg", ".jpeg", ".jfif", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff",
           ".avif", ".heic", ".heif")
PDF_EXT = (".pdf",)
EPUB_EXT = (".epub",)
ARCHIVE_EXT = (".cbz", ".zip")
ALL_EXT = IMG_EXT + PDF_EXT + ARCHIVE_EXT + EPUB_EXT
FORMATS = (".cbz", ".epub", ".pdf")
PLAIN_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")
MAX_PDF_PIXELS = 60_000_000   # one rendered PDF page is kept below this many pixels


class Book:
    """One book to make: a name and where its pages come from."""

    def __init__(self, name, kind, items):
        self.name = name            # file name of the result (without .cbz/.epub)
        self.kind = kind            # 'images', 'pdf', 'archive' or 'epub'
        self.items = items          # list of picture paths, or [the pdf / cbz / epub path]

    def describe(self):
        if self.kind == "images":
            n = len(self.items)
            return f"{self.name}   ({n} picture{'s' if n != 1 else ''})"
        return f"{self.name}   ({os.path.basename(self.items[0])})"

    def __repr__(self):
        return f"Book({self.name!r}, {self.kind!r}, {len(self.items)})"


# ---------------------------------------------------------------------------
# What was dropped -> books
# ---------------------------------------------------------------------------
def natural_key(s):
    """'Page 2' comes before 'Page 10'."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]


def _hidden(name):
    return name.startswith(".") or name.startswith("._") or name == "__MACOSX" or name == "Thumbs.db"


def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name).strip(" .")
    return re.sub(r"\s+", " ", name) or "Book"


def _ext(p):
    return os.path.splitext(p)[1].lower()


def books_from_folder(folder):
    """A folder's own pictures make one book (named after the folder). Each PDF or CBZ inside
    is its own book, and each sub-folder is looked at the same way."""
    out, pics = [], []
    try:
        entries = sorted(os.listdir(folder), key=natural_key)
    except OSError:
        return out
    for e in entries:
        if _hidden(e):
            continue
        p = os.path.join(folder, e)
        if os.path.isdir(p):
            out.extend(books_from_folder(p))
        elif _ext(e) in IMG_EXT:
            pics.append(p)
        elif _ext(e) in PDF_EXT:
            out.append(Book(safe_name(os.path.splitext(e)[0]), "pdf", [p]))
        elif _ext(e) in ARCHIVE_EXT:
            out.append(Book(safe_name(os.path.splitext(e)[0]), "archive", [p]))
        elif _ext(e) in EPUB_EXT:
            out.append(Book(safe_name(os.path.splitext(e)[0]), "epub", [p]))
    if pics:
        out.insert(0, Book(safe_name(os.path.basename(os.path.normpath(folder))), "images", pics))
    return out


def collect(paths):
    """Turn dropped/chosen paths into books. Returns (books, skipped_paths).
    Loose pictures from the same folder become one book named after that folder."""
    books, skipped, loose = [], [], {}
    for p in paths:
        p = p.strip()
        if not p:
            continue
        if os.path.isdir(p):
            books.extend(books_from_folder(p))
        elif os.path.isfile(p):
            e = _ext(p)
            if e in IMG_EXT:
                loose.setdefault(os.path.dirname(os.path.abspath(p)), []).append(p)
            elif e in PDF_EXT:
                books.append(Book(safe_name(os.path.splitext(os.path.basename(p))[0]), "pdf", [p]))
            elif e in ARCHIVE_EXT:
                books.append(Book(safe_name(os.path.splitext(os.path.basename(p))[0]), "archive", [p]))
            elif e in EPUB_EXT:
                books.append(Book(safe_name(os.path.splitext(os.path.basename(p))[0]), "epub", [p]))
            else:
                skipped.append(p)
        else:
            skipped.append(p)
    for parent, pics in loose.items():
        pics.sort(key=lambda x: natural_key(os.path.basename(x)))
        name = os.path.basename(parent) or os.path.splitext(os.path.basename(pics[0]))[0]
        books.append(Book(safe_name(name), "images", pics))
    return books, skipped


def unique_names(books):
    """Two books with the same name would overwrite each other: number the extra ones."""
    seen = {}
    for b in books:
        base = b.name
        k = seen.get(base.lower(), 0)
        if k:
            b.name = f"{base} ({k + 1})"
        seen[base.lower()] = k + 1
    return books


# ---------------------------------------------------------------------------
# Book -> plain page pictures in reading order
# ---------------------------------------------------------------------------
def _plain_picture(src, tmp, n):
    """Pictures the page engine can read as they are are used directly. Photos turned by
    their camera setting are turned upright, and other types (HEIC, AVIF) become PNG."""
    try:
        with Image.open(src) as im:
            orient = im.getexif().get(0x0112, 1)
            if _ext(src) in PLAIN_TYPES and orient in (None, 1):
                return src
            im.load()
            im = ImageOps.exif_transpose(im)
            dest = os.path.join(tmp, f"s{n:05d}.png")
            im.save(dest, "PNG")
            return dest
    except Exception:
        return src   # the page engine reports it as a problem picture


def render_pdf(path, tmp, target_width, stop=None):
    """Every page of a PDF as a picture about target_width pixels wide."""
    import pypdfium2 as pdfium
    out = []
    pdf = pdfium.PdfDocument(path)
    try:
        for i in range(len(pdf)):
            if stop is not None and stop.is_set():
                raise pagecore.Stopped()
            page = pdf[i]
            try:
                w, h = page.get_size()
                scale = max(1.0, target_width / max(1.0, w))
                if w * h * scale * scale > MAX_PDF_PIXELS:
                    scale = (MAX_PDF_PIXELS / (w * h)) ** 0.5
                im = page.render(scale=scale).to_pil()
                dest = os.path.join(tmp, f"pdf{i + 1:05d}.png")
                im.convert("RGB").save(dest, "PNG")
                out.append(dest)
            finally:
                page.close()
    finally:
        pdf.close()
    return out


def extract_archive(path, tmp):
    """The pictures inside a .cbz / .zip, in page order."""
    out = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist()
                 if not n.endswith("/") and _ext(n) in IMG_EXT
                 and not any(_hidden(part) for part in n.split("/"))]
        names.sort(key=natural_key)
        for i, n in enumerate(names):
            dest = os.path.join(tmp, f"z{i:05d}{_ext(n)}")
            with z.open(n) as src, open(dest, "wb") as f:
                shutil.copyfileobj(src, f)
            out.append(dest)
    return out


def page_sources(book, tmp, target_width, stop=None):
    if book.kind == "pdf":
        return render_pdf(book.items[0], tmp, target_width, stop)
    if book.kind == "archive":
        files = extract_archive(book.items[0], tmp)
    elif book.kind == "epub":
        files = bookfiles.extract_epub(book.items[0], tmp)
    else:
        files = list(book.items)
    return [_plain_picture(f, tmp, i) for i, f in enumerate(files)]


# ---------------------------------------------------------------------------
# The conversion
# ---------------------------------------------------------------------------
def formats_for(dev, formats):
    """The files one device gets: what you ticked, plus a PDF if the device needs one."""
    out = [f for f in FORMATS if f in formats]
    if dev["kind"] in devices.NEEDS_PDF and ".pdf" not in out:
        out.append(".pdf")
    return out


class Pager(fitpage.FitPager):
    """The proven snug-fit pager with one extra check for EBZ CNVRTR.

    The proven engine joins a picture to the one before it when art touches both edges
    (webtoon slices). Separate photos and full-page manga art also touch their edges, so here
    they are joined only when they are also the same width AND the picture really carries on
    across the seam (the rows on both sides match). Everything else is fitpage.FitPager, unchanged."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._prev = None   # the last picture added, as it arrived (for the seam check)
        self.whole = set()  # screens that show one whole page (not cut from a strip)

    def _commit_hold(self):
        if self.hold is not None:
            h, self.hold = self.hold, None
            self._save(pagecore._fit_single(h, self.w, self.h))
            self.whole.add(self.pages[-1])

    @staticmethod
    def _edge_rows(im, top, width):
        import numpy as np
        g = im.convert("L")
        box = (0, 0, g.width, 2) if top else (0, g.height - 2, g.width, g.height)
        rows = g.crop(box).resize((width, 2), Image.BILINEAR)
        return np.asarray(rows, dtype=np.float32)

    def _continues(self, prev, im):
        if prev is None or abs(prev.width - im.width) > max(4, 0.02 * im.width):
            return False
        w = min(prev.width, im.width, 800)
        a = self._edge_rows(prev, False, w)   # last two rows before the seam
        b = self._edge_rows(im, True, w)      # first two rows after it
        seam = float(np.abs(a[1] - b[0]).mean())
        inside = (float(np.abs(a[0] - a[1]).mean()) + float(np.abs(b[0] - b[1]).mean())) / 2
        return seam <= max(14.0, 2.5 * inside)

    def add(self, src):
        with Image.open(src) as opened:
            opened.load()
            im = pagecore._page_to_rgb_or_gray(opened, self.gray)
        prev, self._prev = self._prev, im
        if im.size == (self.w, self.h):
            # already made for exactly this screen (an EPUB/CBZ from EBZ CNVRTR): kept as it is
            self.flush()
            self._save(im)
            self.whole.add(self.pages[-1])
            return
        tall = im.height / im.width > pagecore.STRIP
        cont = False
        if self._busy(im, True) and self._continues(prev, im):
            if self.hold is not None and self._busy(self.hold, False):
                cont = True
            elif self.buf is not None and self.buf.width == self.cw and self._busy(self.buf, False):
                cont = True
        if cont:
            if self.hold is not None:
                h, self.hold = self.hold, None
                self._to_strip(h)
            self._to_strip(im)
            return
        if tall:
            self._commit_hold()
            self._to_strip(im)
            return
        self.flush()
        self.hold = im


def _blank(path):
    """A screen with nothing on it (for example from an empty picture at the end of a strip)."""
    with Image.open(path) as im:
        lo, hi = im.convert("L").getextrema()
    return hi - lo < pagecore.QUIET


def fit_pages(sources, tmp, width, height, gray, stop=None, problems=None, on_page=None, cover=None):
    """The snug-fit pages for one screen size, with the cover (if any) as page 1.
    Returns (page paths, strip screens checked, strip screens not clean). Only screens cut from
    a webtoon strip are checked for cut art: a whole page or photo touches its edges on purpose."""
    pager = Pager(tmp, width, height, gray)
    for i, src in enumerate(sources):
        if stop is not None and stop.is_set():
            raise pagecore.Stopped()
        try:
            pager.add(src)
        except Exception:
            if problems is not None:
                problems.append(os.path.basename(src))
        if on_page:
            on_page(i + 1, len(sources))
    pager.flush()
    # empty screens at the very start or end are dropped (blank pages inside are kept)
    pages = list(pager.pages)
    while len(pages) > 1 and _blank(pages[-1]):
        pages.pop()
    while len(pages) > 1 and _blank(pages[0]):
        pages.pop(0)
    fitpage.LAST_AUDIT = (0, 0)
    fitpage._audit([p for p in pages if p not in pager.whole], width, height)
    screens, bad = fitpage.LAST_AUDIT
    if cover:   # also when the book was only its cover page
        pages.insert(0, pagecore.fit_cover(cover, width, height, gray,
                                           os.path.join(tmp, "cover_page.jpg")))
    return pages, screens, bad


# ---------------------------------------------------------------------------
# Covers
# ---------------------------------------------------------------------------
def make_cover(opts, names, sources, tmp, log=None):
    """The cover picture to use (with the number on it if wanted), or None.
    Returns (cover path or None, whether the book's own first page was used as the cover)."""
    opts = opts or {}
    mode = opts.get("mode", "none")
    if mode == "picture" and opts.get("path") and os.path.isfile(opts["path"]):
        src, used_first = opts["path"], False
    elif mode == "first" and sources:
        try:
            with Image.open(sources[0]) as im:
                tall = im.height / im.width > pagecore.STRIP
        except Exception:
            tall = True
        if tall:
            if log:
                log(f"   {names[0]}: the first page is part of a long strip, so it was not used as "
                    "the cover.")
            return None, False
        src, used_first = sources[0], True
    else:
        return None, False
    if opts.get("number", True):
        text = coverart.badge_text(names)
        if text:
            try:
                src = coverart.stamp_cover(src, text, os.path.join(tmp, f"cover_{len(os.listdir(tmp))}.png"),
                                           opts.get("corner", "ur"), opts.get("size", 0.07),
                                           opts.get("style", "dark"))
            except Exception as e:
                if log:
                    log(f"   Could not put the number on the cover ({e}).")
    return src, used_first


# ---------------------------------------------------------------------------
# The conversion
# ---------------------------------------------------------------------------
def _check(formats, device_keys, need_devices=True):
    if need_devices and not device_keys:
        raise ValueError("Tick at least one device.")
    if not any(f in formats for f in FORMATS):
        raise ValueError("Tick at least one file type (CBZ, EPUB or PDF).")


def _profiles(device_keys, custom):
    """Devices with the same screen share the same pages (made once)."""
    profiles = {}
    for d in (devices.info(k, custom) for k in device_keys):
        profiles.setdefault((d["size"], d["gray"]), []).append(d)
    return profiles


def _read(book, tmp, target_w, stop, log):
    """The pictures of a book in order, or None (with the reason in the log)."""
    os.makedirs(tmp, exist_ok=True)
    try:
        sources = page_sources(book, tmp, target_w, stop)
    except pagecore.Stopped:
        raise
    except bookfiles.BookError as e:
        log(f"✗ {book.name}: {e}.")
        return None
    except Exception as e:
        log(f"✗ {book.name}: could not be read ({e}).")
        return None
    if not sources:
        log(f"✗ {book.name}: no pictures found inside.")
        return None
    return sources


def _write_all(pages, folder, name, exts, toc=None, tmp=None):
    os.makedirs(folder, exist_ok=True)
    made = []
    for ext in exts:
        dest = os.path.join(folder, name + ext)
        bookfiles.write_book(pages, dest, ext, name, toc, tmp)
        made.append(dest)
    return made


def clean_note(screens, bad):
    if not screens:
        return "pages fitted whole"
    return f"{screens - bad} of {screens} strip screens are clean"


def _report(log, name, label, made, screens, bad, problems):
    log(f"✓ {name} for {label}: {', '.join(os.path.basename(m) for m in made)}"
        f"  ({clean_note(screens, bad)})")
    if problems:
        log(f"   {len(problems)} picture(s) could not be used: {', '.join(problems[:5])}"
            + (" ..." if len(problems) > 5 else ""))


def convert(books, device_keys, formats, out_root, custom=None, progress=None, log=None, stop=None,
            cover=None):
    """Make the files. progress(fraction 0..1, text); log(text).
    Files go to out_root/<device folder>/<book name>.cbz|.epub|.pdf
    Returns a list of dicts, one per book and device: book, device, files, screens, bad, problems."""
    stop = stop or threading.Event()
    log = log or (lambda t: None)
    progress = progress or (lambda f, t: None)
    if not books:
        raise ValueError("There is nothing to convert yet. Drop some pictures, PDFs, EPUBs or folders first.")
    _check(formats, device_keys)
    profiles = _profiles(device_keys, custom)
    target_w = max(size[0] for size, _g in profiles)
    unique_names(books)
    steps = len(books) * (1 + len(profiles))
    step = 0
    results = []
    for b in books:
        if stop.is_set():
            raise pagecore.Stopped()
        progress(step / steps, f"Reading {b.name}")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            sources = _read(b, os.path.join(tmp, "src"), target_w, stop, log)
            step += 1
            if sources is None:
                step += len(profiles)
                continue
            cdir = os.path.join(tmp, "cover")
            os.makedirs(cdir)
            cov, used_first = make_cover(cover, [b.name], sources, cdir, log)
            if used_first:
                sources = sources[1:]
            for (size, gray), group in profiles.items():
                if stop.is_set():
                    raise pagecore.Stopped()
                w, h = size
                page_dir = os.path.join(tmp, f"p{w}x{h}{'g' if gray else 'c'}")
                os.makedirs(page_dir)
                problems = []
                base = step

                def on_page(i, n, base=base, name=b.name):
                    progress((base + i / max(1, n)) / steps, f"Fitting {name}: page {i} of {n}")

                pages, screens, bad = fit_pages(sources, page_dir, w, h, gray, stop, problems, on_page, cov)
                step += 1
                if not pages:
                    log(f"✗ {b.name}: none of its pictures could be used.")
                    continue
                for d in group:
                    folder = os.path.join(out_root, safe_name(d["folder"]))
                    made = _write_all(pages, folder, b.name, formats_for(d, formats))
                    results.append({"book": b.name, "device": d["label"], "folder": folder,
                                    "kind": d["kind"], "files": made, "screens": screens,
                                    "bad": bad, "problems": list(problems), "pages": len(pages)})
                    _report(log, b.name, d["label"], made, screens, bad, problems)
    progress(1.0, "Done.")
    return results


# ---------------------------------------------------------------------------
# Combining several books into one
# ---------------------------------------------------------------------------
_NUM = re.compile(r"(\d+(?:\.\d+)?)(?!.*\d)")


def combined_name(names):
    """'Series Chapter 001' ... 'Series Chapter 006' -> 'Series Chapter 001-006'.
    Names without numbers -> 'First name + 5 more'."""
    if not names:
        return "Combined"
    found = [_NUM.search(n) for n in names]
    if len(names) > 1 and all(found):
        first, last = found[0], found[-1]
        return safe_name(f"{names[0][:first.start()]}{first.group(1)}-{last.group(1)}"
                         f"{names[0][first.end():]}")
    if len(names) == 1:
        return safe_name(names[0])
    return safe_name(f"{names[0]} + {len(names) - 1} more")


def combine(books, name, fit, device_keys, formats, out_root, custom=None, progress=None, log=None,
            stop=None, cover=None):
    """Join several books into one, in the order given, with a contents entry per book.
    fit=True: the pages are snug-fitted for each ticked device -> out_root/<device>/<name>.*
    fit=False: the pages are kept as they are -> out_root/Combined/<name>.*
    The original files are never changed. Returns a list of dicts like convert()."""
    stop = stop or threading.Event()
    log = log or (lambda t: None)
    progress = progress or (lambda f, t: None)
    if len(books) < 2:
        raise ValueError("Add at least two books to combine.")
    _check(formats, device_keys, need_devices=fit)
    name = safe_name(name or combined_name([b.name for b in books]))
    profiles = _profiles(device_keys, custom) if fit else {}
    target_w = max([size[0] for size, _g in profiles] or [1600])
    steps = len(books) * (1 + max(1, len(profiles)))
    step = 0
    results = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        parts = []
        for i, b in enumerate(books):
            if stop.is_set():
                raise pagecore.Stopped()
            progress(step / steps, f"Reading {b.name} ({i + 1} of {len(books)})")
            sources = _read(b, os.path.join(tmp, f"src{i:04d}"), target_w, stop, log)
            step += 1
            if sources is not None:
                parts.append((b.name, sources))
        if not parts:
            raise ValueError("None of the books could be read, so nothing was combined.")
        if len(parts) < len(books):
            log(f"   {len(books) - len(parts)} book(s) were left out of {name} (see above).")
        cdir = os.path.join(tmp, "cover")
        os.makedirs(cdir)
        cov, used_first = make_cover(cover, [p[0] for p in parts], parts[0][1], cdir, log)
        if used_first:
            parts[0] = (parts[0][0], parts[0][1][1:])
        if fit:
            for (size, gray), group in profiles.items():
                w, h = size
                pages, toc, screens, bad, problems = [], [], 0, 0, []
                if cov:
                    pages.append(pagecore.fit_cover(cov, w, h, gray,
                                                    os.path.join(tmp, f"cover_{w}x{h}{int(gray)}.jpg")))
                for k, (pname, sources) in enumerate(parts):
                    if stop.is_set():
                        raise pagecore.Stopped()
                    page_dir = os.path.join(tmp, f"p{w}x{h}{'g' if gray else 'c'}_{k:04d}")
                    os.makedirs(page_dir)
                    base = step

                    def on_page(i, n, base=base, pname=pname):
                        progress(min(0.99, (base + i / max(1, n)) / steps),
                                 f"Fitting {pname}: page {i} of {n}")

                    pp, s, bd = fit_pages(sources, page_dir, w, h, gray, stop, problems, on_page)
                    step += 1
                    if pp:
                        toc.append((pname, len(pages) if (pages and k) else 0))
                        pages.extend(pp)
                        screens += s
                        bad += bd
                if not pages:
                    log(f"✗ {name}: none of the pictures could be used.")
                    continue
                for d in group:
                    folder = os.path.join(out_root, safe_name(d["folder"]))
                    made = _write_all(pages, folder, name, formats_for(d, formats), toc)
                    results.append({"book": name, "device": d["label"], "folder": folder,
                                    "kind": d["kind"], "files": made, "screens": screens,
                                    "bad": bad, "problems": list(problems), "parts": len(parts),
                                    "pages": len(pages)})
                    _report(log, name, d["label"], made, screens, bad, problems)
        else:
            pages, toc = [], []
            first = next((src[0] for _n, src in parts if src), cov)   # the size to give the cover
            with Image.open(first) as im:
                w, h = im.size
            if cov:
                pages.append(pagecore.fit_cover(cov, w, h, False, os.path.join(tmp, "cover_keep.jpg")))
            for k, (pname, sources) in enumerate(parts):
                if sources or k == 0:
                    toc.append((pname, len(pages) if (pages and k) else 0))
                pages.extend(sources)
            conv = os.path.join(tmp, "conv")
            os.makedirs(conv)
            folder = os.path.join(out_root, "Combined")
            progress(0.9, f"Writing {name}")
            exts = [f for f in FORMATS if f in formats]
            made = _write_all(pages, folder, name, exts, toc, conv)
            results.append({"book": name, "device": "pages kept as they are", "folder": folder,
                            "kind": "combined", "files": made, "screens": 0, "bad": 0,
                            "problems": [], "parts": len(parts), "pages": len(pages)})
            log(f"✓ {name} ({len(parts)} books, {len(pages)} pages, sizes kept as they were): "
                + ", ".join(os.path.basename(m) for m in made))
    progress(1.0, "Done.")
    return results


def selftest():
    """Used by the build to prove the packaged app can read pictures, a PDF, a CBZ and an EPUB,
    make every file type with clean, correctly sized screens, add a numbered cover and combine."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        pics = os.path.join(d, "My Comic Chapter 3")
        os.makedirs(pics)
        for i in range(3):
            im = Image.new("RGB", (800, 1100), "white")
            im.paste(Image.new("RGB", (600, 800), (30 * i, 80, 160)), (100, 150))
            im.save(os.path.join(pics, f"{i + 1}.png"))
        strip = Image.new("RGB", (800, 4000), "white")
        for y in range(100, 3900, 900):
            strip.paste(Image.new("RGB", (700, 700), (200, 50, 50)), (50, y))
        strip.save(os.path.join(pics, "4.jpg"))
        pdf = os.path.join(d, "Doc.pdf")
        Image.new("RGB", (600, 900), (10, 120, 10)).save(pdf, "PDF", resolution=72)
        cbz = os.path.join(d, "Old.cbz")
        with zipfile.ZipFile(cbz, "w") as z:
            z.write(os.path.join(pics, "1.png"), "001.png")
        books, _ = collect([pics, pdf, cbz])
        assert len(books) == 3, books
        out = os.path.join(d, "out")
        cov = os.path.join(d, "cover.png")
        Image.new("RGB", (600, 900), (200, 180, 40)).save(cov)
        res = convert(books, ["kobo_clara", "kindle_basic"], (".cbz", ".epub"), out,
                      cover={"mode": "picture", "path": cov, "number": True})
        assert len(res) == 6, res
        for r in res:
            assert r["pages"] > 0 and r["bad"] == 0, r
            for f in r["files"]:
                assert os.path.getsize(f) > 0, f
        assert any(f.endswith(".pdf") for r in res if r["kind"] == "kindle" for f in r["files"])
        epubs = sorted(f for r in res if r["kind"] == "kobo" for f in r["files"] if f.endswith(".epub"))
        parts, _ = collect(epubs)
        res2 = combine(parts, "", True, ["kobo_clara"], (".epub", ".cbz"), out)
        assert res2 and all(os.path.getsize(f) > 0 for f in res2[0]["files"]), res2
        res3 = combine(parts, "Kept", False, [], (".epub",), out)
        assert res3 and os.path.isfile(res3[0]["files"][0]), res3
    return True
