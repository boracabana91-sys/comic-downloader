"""Reading EPUBs made by any program, and writing CBZ / EPUB / PDF files.

Reading: the EPUB is opened inside the program, its pictures are taken out in reading order
(the order of its pages), and they go through the same snug-fit engine as any picture.
Text books (novels) and copy-protected (DRM) books are refused with a plain message.

Writing: the EPUB is the same picture book as the proven writer in pagecore.py (every page
one full-screen picture, fixed layout), with two additions for combined books: each page
keeps its own size, and the contents list has one entry per chapter."""
import base64
import hashlib
import os
import posixpath
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import unquote

from PIL import Image

import pagecore

IMG_TYPES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".jfif")
MIN_PICTURE = 200          # pictures smaller than this (both sides) are icons or decorations
PICTURE_PAGE_TEXT = 300    # a picture page may carry this much text (a title, a credit line)
PAGE_TEXT = 150            # a page with more text than this and no picture is a text page
FONT_ONLY = ("http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC")


class BookError(Exception):
    """A plain-language reason a book cannot be used."""


# ---------------------------------------------------------------------------
# Reading any EPUB
# ---------------------------------------------------------------------------
def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _find_opf(z):
    try:
        root = ET.fromstring(z.read("META-INF/container.xml"))
        for el in root.iter():
            if _local(el.tag) == "rootfile" and el.get("full-path"):
                return el.get("full-path")
    except Exception:
        pass
    for n in z.namelist():
        if n.lower().endswith(".opf"):
            return n
    raise BookError("this EPUB is damaged (its table of pages is missing)")


def _check_protected(z):
    names = set(z.namelist())
    if "META-INF/encryption.xml" not in names:
        return
    try:
        root = ET.fromstring(z.read("META-INF/encryption.xml"))
    except Exception:
        return
    for data in root.iter():
        if _local(data.tag) != "EncryptedData":
            continue
        algo, uri = "", ""
        for el in data.iter():
            if _local(el.tag) == "EncryptionMethod":
                algo = el.get("Algorithm", "")
            if _local(el.tag) == "CipherReference":
                uri = el.get("URI", "")
        if algo in FONT_ONLY:
            continue   # only the fonts are scrambled; that is normal and harmless
        if uri.lower().endswith(IMG_TYPES + (".xhtml", ".html", ".htm", ".svg")):
            raise BookError("this EPUB is copy-protected (DRM) by the shop it came from, so its "
                            "pages cannot be opened")


_REF = re.compile(r"""(?:<img\b[^>]*?\bsrc|<image\b[^>]*?\b(?:xlink:)?href)\s*=\s*["']([^"']+)["']"""
                  r"""|url\(\s*["']?([^"')]+)["']?\s*\)""", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>", re.S)
_DATA = re.compile(r"data:image/[\w.+-]+;base64,([A-Za-z0-9+/=\s]+)", re.I)
_HEAD = re.compile(r"<(head|style|script)\b.*?</\1\s*>", re.I | re.S)


def _resolve(base_dir, ref):
    ref = unquote(ref.split("#", 1)[0].split("?", 1)[0]).strip()
    if not ref or ref.lower().startswith(("data:", "http:", "https:")):
        return None
    return posixpath.normpath(posixpath.join(base_dir, ref)).lstrip("/")


def epub_pages(path):
    """The pages of an EPUB in reading order, as a list of
    ("zip", name inside the file) - a picture,
    ("svg", name inside the file) - a whole page drawn as SVG (drawn into a picture later),
    ("data", picture bytes) - a picture stored inside the page itself."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise BookError("this is not a working EPUB file (it may be damaged or only partly downloaded)")
    with z:
        _check_protected(z)
        names = set(z.namelist())
        lower = {n.lower(): n for n in names}

        def real(n):
            return n if n in names else lower.get((n or "").lower())

        opf_path = _find_opf(z)
        opf_dir = posixpath.dirname(opf_path)
        try:
            opf = ET.fromstring(z.read(opf_path))
        except Exception:
            raise BookError("this EPUB is damaged (its table of pages cannot be read)")
        manifest, spine = {}, []
        for el in opf.iter():
            t = _local(el.tag)
            if t == "item" and el.get("id") and el.get("href"):
                manifest[el.get("id")] = (_resolve(opf_dir, el.get("href")),
                                          (el.get("media-type") or "").lower())
            elif t == "itemref" and el.get("idref"):
                spine.append(el.get("idref"))
        found, pic_pages, text_pages, any_text, words = [], 0, 0, False, 0
        for idref in spine:
            href, mtype = manifest.get(idref, (None, ""))
            href = real(href)
            if not href:
                continue
            if "svg" in mtype or href.lower().endswith((".svg", ".svgz")):
                found.append(("svg", href))   # drawn whole, text and all
                pic_pages += 1
                continue
            if mtype.startswith("image/") or href.lower().endswith(IMG_TYPES):
                found.append(("zip", href))
                pic_pages += 1
                continue
            try:
                doc = z.read(href).decode("utf-8", "replace")
            except KeyError:
                continue
            body = _HEAD.sub(" ", doc)
            chars = len(re.sub(r"\s+", "", _TAGS.sub(" ", _DATA.sub("", body))))
            any_text = any_text or chars > PAGE_TEXT
            base = posixpath.dirname(href)
            pics = []
            for m in _REF.finditer(body):
                ref = (m.group(1) or m.group(2) or "").strip()
                d = _DATA.match(ref)
                if d:
                    try:
                        pics.append(("data", base64.b64decode(d.group(1))))
                    except Exception:
                        pass
                    continue
                p = real(_resolve(base, ref))
                if p and p.lower().endswith(IMG_TYPES):
                    pics.append(("zip", p))
                elif p and p.lower().endswith((".svg", ".svgz")):
                    pics.append(("svg", p))
            found.extend(pics)
            # a comic page is a picture with (almost) no text; a page with a lot of text, with
            # or without a picture, is a text page whose words would be lost
            if pics and chars <= PICTURE_PAGE_TEXT:
                pic_pages += 1
            elif chars > PAGE_TEXT:
                text_pages += 1
                words += chars
        if text_pages > pic_pages or words > max(3000, 300 * pic_pages):
            raise BookError("this EPUB is a text book (like a novel or a magazine), not a comic - "
                            "its pages are made of words, which would be lost")
        if not found and not any_text:   # pictures listed but never shown on a page
            found = [("zip", n) for n in sorted((real(h) for h, mt in manifest.values()
                     if real(h) and mt.startswith("image/") and "svg" not in mt), key=_natural)]
        out = []
        for p in found:
            if not out or out[-1] != p:   # the same picture twice in a row is one page
                out.append(p)
        if not out:
            raise BookError("there are no pictures in this EPUB")
        return out


def epub_picture_names(path):
    """Names of the pictures (not SVG or stored-in-page ones), for tests."""
    return [v for k, v in epub_pages(path) if k == "zip"]


def _natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]


def _draw_svg(svg_path, dest, width=1600):
    """A whole SVG page drawn into a PNG picture (pictures and text inside it included)."""
    import resvg_py
    png = resvg_py.svg_to_bytes(svg_path=svg_path, resources_dir=os.path.dirname(svg_path),
                                width=width, background="#ffffff")
    with open(dest, "wb") as f:
        f.write(bytes(png))


def extract_epub(path, tmp, width=1600):
    """Take the pages out of any EPUB into tmp as pictures, in reading order. SVG pages are
    drawn into pictures. Small pictures (icons, decorations) are left out."""
    pages = epub_pages(path)
    out = []
    with zipfile.ZipFile(path) as z:
        unz = None
        if any(k == "svg" for k, _v in pages):
            unz = os.path.join(tmp, "_epub")
            z.extractall(unz)   # SVG pages need the pictures they point to next to them
        for i, (kind, val) in enumerate(pages):
            if kind == "svg":
                dest = os.path.join(tmp, f"e{i:05d}.png")
                try:
                    _draw_svg(os.path.join(unz, *val.split("/")), dest, width)
                except Exception:
                    continue
            elif kind == "data":
                dest = os.path.join(tmp, f"e{i:05d}.img")
                with open(dest, "wb") as f:
                    f.write(val)
            else:
                dest = os.path.join(tmp, f"e{i:05d}{os.path.splitext(val)[1].lower()}")
                with z.open(val) as src, open(dest, "wb") as f:
                    shutil.copyfileobj(src, f)
            try:
                with Image.open(dest) as im:
                    if max(im.size) < MIN_PICTURE:
                        os.remove(dest)
                        continue
            except Exception:
                pass   # the page engine reports pictures it cannot read
            out.append(dest)
    if not out:
        raise BookError("there are no full-size pictures in this EPUB")
    return out


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
_xml = pagecore._xml


def _image_info(p):
    with Image.open(p) as im:
        fmt, size = (im.format or "").upper(), im.size
    if fmt == "PNG":
        return ".png", "image/png", size
    return ".jpg", "image/jpeg", size


def _as_jpeg_or_png(p, tmp, n):
    """EPUB readers all show JPEG and PNG; anything else is turned into JPEG."""
    with Image.open(p) as im:
        if (im.format or "").upper() in ("JPEG", "PNG"):
            return p
        im.load()
        dest = os.path.join(tmp, f"w{n:05d}.jpg")
        pagecore._page_to_rgb_or_gray(im, im.mode == "L").save(dest, "JPEG", quality=90)
        return dest


def write_epub(pages, dest, title, toc=None):
    """A picture-book EPUB, as the proven writer makes, with each page at its own size and a
    contents entry for each (title, first page number from 0) in toc."""
    w, h = _image_info(pages[0])[2]
    t = _xml(title)
    book_id = "urn:uuid:" + pagecore._uuid_from(
        hashlib.sha1((title + str(len(pages))).encode()).hexdigest())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    toc = toc or [(title, 0)]
    infos = [_image_info(p) for p in pages]
    items, spine = [], []
    for i, (ext, mt, _s) in enumerate(infos, 1):
        cover = ' properties="cover-image"' if i == 1 else ""
        items.append(f'<item id="img{i:04d}" href="Images/{i:04d}{ext}" media-type="{mt}"{cover}/>')
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
    entries = [(_xml(name), f"Text/{min(start, len(pages) - 1) + 1:04d}.xhtml") for name, start in toc]
    nav = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
           '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
           f'<head><title>{t}</title></head><body><nav epub:type="toc"><ol>'
           + "".join(f'<li><a href="{href}">{name}</a></li>' for name, href in entries)
           + '</ol></nav></body></html>')
    toc_ncx = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
               f'<head><meta name="dtb:uid" content="{book_id}"/></head>'
               f'<docTitle><text>{t}</text></docTitle><navMap>'
               + "".join(f'<navPoint id="n{k}" playOrder="{k}"><navLabel><text>{name}</text></navLabel>'
                         f'<content src="{href}"/></navPoint>' for k, (name, href) in enumerate(entries, 1))
               + '</navMap></ncx>')
    css = ("@page{margin:0}html,body{margin:0;padding:0;height:100%;width:100%;"
           "overflow:hidden}svg{display:block;margin:0;padding:0}")
    container = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                 'media-type="application/oebps-package+xml"/></rootfiles></container>')
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/toc.ncx", toc_ncx)
        z.writestr("OEBPS/style.css", css)
        for i, (p, (ext, _mt, (pw, ph))) in enumerate(zip(pages, infos), 1):
            z.write(p, f"OEBPS/Images/{i:04d}{ext}", compress_type=zipfile.ZIP_STORED)
            z.writestr(
                f"OEBPS/Text/{i:04d}.xhtml",
                '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
                f'<head><title>{t} - {i}</title>'
                f'<meta name="viewport" content="width={pw}, height={ph}"/>'
                '<link rel="stylesheet" type="text/css" href="../style.css"/></head><body>'
                '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'version="1.1" width="100%" height="100%" viewBox="0 0 {pw} {ph}" '
                'preserveAspectRatio="xMidYMid meet">'
                f'<image width="{pw}" height="{ph}" xlink:href="../Images/{i:04d}{ext}"/></svg>'
                '</body></html>')


class _LazyImages:
    """Pages for the PDF, opened one at a time (a long book would otherwise open hundreds
    of files at once, more than Windows allows)."""

    def __init__(self, paths):
        self.paths = paths

    def __len__(self):
        return len(self.paths)

    def __iter__(self):
        for p in self.paths:
            with Image.open(p) as im:
                im.load()
                yield im if im.mode in ("RGB", "L") else im.convert("RGB")


def write_pdf(pages, dest):
    with Image.open(pages[0]) as first:
        first.load()
        first = first if first.mode in ("RGB", "L") else first.convert("RGB")
        first.save(dest, "PDF", save_all=True, append_images=_LazyImages(pages[1:]), resolution=300.0)


def write_cbz(pages, dest):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as z:
        for i, p in enumerate(pages, 1):
            z.write(p, f"{i:04d}{_image_info(p)[0]}")


def write_book(pages, dest, ext, title, toc=None, tmp=None):
    """Write one file. It is written under a temporary name first and renamed at the end,
    so a stop or a crash never leaves a half-written file with the real name."""
    if tmp and ext in (".epub", ".cbz"):
        pages = [_as_jpeg_or_png(p, tmp, i) for i, p in enumerate(pages)]
    part = dest + ".part"
    try:
        if ext == ".epub":
            write_epub(pages, part, title, toc)
        elif ext == ".cbz":
            write_cbz(pages, part)
        else:
            write_pdf(pages, part)
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
