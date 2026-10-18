"""Page tools for EBZ CNVRTR, copied word for word from the proven Comic Downloader engine
(core.py and covers.py, series-v5-test6). Only the parts needed to fit pages and write
CBZ, EPUB and PDF files are here; nothing about downloading.

Do not change these without a reason: they are what made pages fit every device."""
import os
import zipfile

from PIL import Image

QUIET = 6        # a row whose brightness spread is below this is empty background
STRIP = 1.6      # a picture taller than 1.6 x its width is part of a webtoon strip


class Stopped(Exception):
    pass


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


def _vjoin(a, b):
    out = Image.new(a.mode, (a.width, a.height + b.height))
    out.paste(a, (0, 0))
    out.paste(b, (0, a.height))
    return out


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


# ----- cover (from covers.py) -----
def load_cover(path):
    with Image.open(path) as opened:
        opened.load()
        if opened.mode in ("RGBA", "LA") or (opened.mode == "P" and "transparency" in opened.info):
            rgba = opened.convert("RGBA")
            bg = Image.new("RGB", rgba.size, "white")
            bg.paste(rgba, mask=rgba.split()[3])
            return bg
        return opened.convert("RGB")


def _edge_color(im):
    w, h = im.size
    pts = [im.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    return tuple(sum(c[i] for c in pts) // 4 for i in range(3))


def fit_cover(cover_path, width, height, gray, out_path):
    """The whole picture, fitted to the screen size (nothing cropped), as a JPEG."""
    im = load_cover(cover_path)
    scale = min(width / im.width, height / im.height)
    nw, nh = max(1, round(im.width * scale)), max(1, round(im.height * scale))
    bg = _edge_color(im)
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (width, height), bg)
    canvas.paste(im, ((width - nw) // 2, (height - nh) // 2))
    if gray:
        canvas = canvas.convert("L")
    canvas.save(out_path, "JPEG", quality=90)
    return out_path
