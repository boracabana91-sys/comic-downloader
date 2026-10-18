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
ARCHIVE_EXT = (".cbz", ".zip")
ALL_EXT = IMG_EXT + PDF_EXT + ARCHIVE_EXT
FORMATS = (".cbz", ".epub", ".pdf")
PLAIN_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")
MAX_PDF_PIXELS = 60_000_000   # one rendered PDF page is kept below this many pixels


class Book:
    """One book to make: a name and where its pages come from."""

    def __init__(self, name, kind, items):
        self.name = name            # file name of the result (without .cbz/.epub)
        self.kind = kind            # 'images', 'pdf' or 'archive'
        self.items = items          # list of picture paths, or [the pdf / cbz path]

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


def fit_pages(sources, tmp, width, height, gray, stop=None, problems=None, on_page=None):
    """The snug-fit pages for one screen size. Returns (page paths, screens, screens not clean)."""
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
    pager.pages[:] = pages
    fitpage.LAST_AUDIT = (0, 0)
    fitpage._audit(pager.pages, width, height)
    screens, bad = fitpage.LAST_AUDIT
    return pager.pages, screens, bad


def convert(books, device_keys, formats, out_root, custom=None, progress=None, log=None, stop=None):
    """Make the files. progress(fraction 0..1, text); log(text).
    Files go to out_root/<device folder>/<book name>.cbz|.epub|.pdf
    Returns a list of dicts, one per book and device: book, device, files, screens, bad, problems."""
    stop = stop or threading.Event()
    log = log or (lambda t: None)
    progress = progress or (lambda f, t: None)
    if not books:
        raise ValueError("There is nothing to convert yet. Drop some pictures, PDFs or folders first.")
    if not device_keys:
        raise ValueError("Tick at least one device.")
    if not any(f in formats for f in FORMATS):
        raise ValueError("Tick at least one file type (CBZ, EPUB or PDF).")
    devs = [devices.info(k, custom) for k in device_keys]
    # devices with the same screen share the same pages (made once)
    profiles = {}
    for d in devs:
        profiles.setdefault((d["size"], d["gray"]), []).append(d)
    target_w = max(d["size"][0] for d in devs)
    unique_names(books)
    steps = len(books) * (1 + len(profiles))
    step = 0
    results = []
    for b in books:
        if stop.is_set():
            raise pagecore.Stopped()
        progress(step / steps, f"Reading {b.name}")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            src_dir = os.path.join(tmp, "src")
            os.makedirs(src_dir)
            try:
                sources = page_sources(b, src_dir, target_w, stop)
            except pagecore.Stopped:
                raise
            except Exception as e:
                log(f"✗ {b.name}: could not be read ({e}).")
                step += 1 + len(profiles)
                continue
            step += 1
            if not sources:
                log(f"✗ {b.name}: no pictures found inside.")
                step += len(profiles)
                continue
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

                pages, screens, bad = fit_pages(sources, page_dir, w, h, gray, stop, problems, on_page)
                step += 1
                if not pages:
                    log(f"✗ {b.name}: none of its pictures could be used.")
                    continue
                for d in group:
                    folder = os.path.join(out_root, safe_name(d["folder"]))
                    os.makedirs(folder, exist_ok=True)
                    made = []
                    for ext in formats_for(d, formats):
                        dest = os.path.join(folder, b.name + ext)
                        pagecore._write_device_file(pages, dest, ext, b.name)
                        made.append(dest)
                    results.append({"book": b.name, "device": d["label"], "folder": d["folder"],
                                    "kind": d["kind"], "files": made, "screens": screens,
                                    "bad": bad, "problems": list(problems)})
                    clean = screens - bad
                    note = f"{clean} of {screens} screens are clean"
                    log(f"✓ {b.name} for {d['label']}: {', '.join(os.path.basename(m) for m in made)}"
                        f"  ({note})")
                    if problems:
                        log(f"   {len(problems)} picture(s) could not be used: {', '.join(problems[:5])}"
                            + (" ..." if len(problems) > 5 else ""))
    progress(1.0, "Done.")
    return results


def selftest():
    """Used by the build to prove the packaged app can read pictures, a PDF and a CBZ and
    make every file type with clean, correctly sized screens."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        pics = os.path.join(d, "My Comic")
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
        res = convert(books, ["kobo_clara", "kindle_basic"], (".cbz", ".epub"), out)
        assert len(res) == 6, res
        for r in res:
            assert r["screens"] > 0 and r["bad"] == 0, r
            for f in r["files"]:
                assert os.path.getsize(f) > 0, f
        assert any(f.endswith(".pdf") for r in res if r["kind"] == "kindle" for f in r["files"])
    return True
