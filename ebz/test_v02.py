"""Tests for what version 02 added: EPUBs from other programs, combining, covers with numbers.
Run: python test_v02.py"""
import base64
import io
import os
import sys
import tempfile
import traceback
import zipfile
import xml.dom.minidom

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bookfiles  # noqa: E402
import converter  # noqa: E402
import coverart  # noqa: E402

COLORS = [(220, 40, 40), (40, 180, 40), (40, 60, 220), (230, 200, 30), (200, 40, 200),
          (30, 200, 200), (240, 130, 20)]


def panel(h, color, w=800):
    a = np.zeros((h, w, 3), dtype=np.uint8)
    a[:] = color
    for x in range(0, w, 40):
        a[:, x:x + 20] = [int(c * 0.6) for c in color]
    return Image.fromarray(a)


def jpg_bytes(im):
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90)
    return b.getvalue()


def has(page, color, tol=45, need=400):
    a = np.asarray(page.convert("RGB"), dtype=np.int16)
    return int((np.abs(a - np.array(color)).max(axis=2) < tol).sum()) >= need


def make_epub(path, pages, style="img", opf_dir="OEBPS", extra=None, spine_extra=""):
    """An EPUB like other programs make. pages: list of PIL images.
    style: 'img' (<img> in xhtml, like Calibre), 'svg' (SVG wrapper, like KCC), 'spine'
    (pictures straight in the reading order), 'data' (picture stored inside the page),
    'strip' (several pictures per page, like webtoon EPUBs)."""
    items, spine, files = [], [], {}
    pre = f"{opf_dir}/" if opf_dir else ""
    groups = [pages[i:i + 3] for i in range(0, len(pages), 3)] if style == "strip" else [[p] for p in pages]
    for k, group in enumerate(groups):
        tags = []
        for j, im in enumerate(group):
            name = f"images/pic{k}_{j}.jpg"
            if style != "data":
                files[pre + name] = jpg_bytes(im)
                items.append(f'<item id="i{k}_{j}" href="{name}" media-type="image/jpeg"/>')
            if style in ("img", "strip"):
                tags.append(f'<div><img src="../{name}" alt="page"/></div>')
            elif style == "svg":
                tags.append(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                            f'viewBox="0 0 {im.width} {im.height}"><image width="{im.width}" '
                            f'height="{im.height}" xlink:href="../{name}"/></svg>')
            elif style == "data":
                b64 = base64.b64encode(jpg_bytes(im)).decode()
                tags.append(f'<img src="data:image/jpeg;base64,{b64}"/>')
        if style == "spine":
            spine.append(f'<itemref idref="i{k}_0"/>')
            continue
        files[f"{pre}text/page{k}.xhtml"] = (
            '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
            f'<head><title>Page {k}</title><style>img{{width:100%}}</style></head><body>'
            + "".join(tags) + "</body></html>").encode()
        items.append(f'<item id="p{k}" href="text/page{k}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="p{k}"/>')
    opf = ('<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" '
           'version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           '<dc:title>Test</dc:title><dc:identifier id="id">x</dc:identifier></metadata><manifest>'
           + "".join(items) + '</manifest><spine>' + spine_extra + "".join(spine) + '</spine></package>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   f'<rootfiles><rootfile full-path="{pre}content.opf" media-type="application/oebps-package+xml"/>'
                   '</rootfiles></container>')
        z.writestr(pre + "content.opf", opf)
        for n, b in files.items():
            z.writestr(n, b)
        for n, b in (extra or {}).items():
            z.writestr(n, b)


def colors_of(paths):
    out = []
    for p in paths:
        with Image.open(p) as im:
            px = im.convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0))
        out.append(min(range(len(COLORS)), key=lambda i: sum(abs(a - b) for a, b in zip(px, COLORS[i]))))
    return out


# ---------------------------------------------------------------------------
def test_other_program_epubs_read_in_order():
    pages = [Image.new("RGB", (800, 1200), c) for c in COLORS[:5]]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        for style in ("img", "svg", "spine", "data"):
            p = os.path.join(d, f"{style}.epub")
            make_epub(p, pages, style, opf_dir="" if style == "spine" else "OEBPS")
            t = os.path.join(d, style)
            os.makedirs(t)
            got = bookfiles.extract_epub(p, t)
            assert colors_of(got) == [0, 1, 2, 3, 4], (style, colors_of(got))
        # a cover page that repeats page 1 is used once
        p = os.path.join(d, "cover.epub")
        make_epub(p, pages[:3], "img", spine_extra='<itemref idref="p0"/>')
        t = os.path.join(d, "cover")
        os.makedirs(t)
        assert colors_of(bookfiles.extract_epub(p, t)) == [0, 1, 2]
        # icons and decorations (small pictures) are left out
        p = os.path.join(d, "icon.epub")
        make_epub(p, [pages[0], Image.new("RGB", (60, 60), COLORS[5]), pages[1]], "img")
        t = os.path.join(d, "icon")
        os.makedirs(t)
        assert colors_of(bookfiles.extract_epub(p, t)) == [0, 1]


def test_svg_page_is_drawn():
    """A page drawn entirely as SVG (shapes and text, as some converters make) becomes a picture."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        p = os.path.join(d, "s.epub")
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="900">'
               '<rect width="600" height="900" fill="white"/>'
               '<rect x="50" y="50" width="500" height="700" fill="rgb(40,60,220)"/>'
               '<text x="60" y="850" font-size="40">Hello</text></svg>')
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("mimetype", "application/epub+zip")
            z.writestr("META-INF/container.xml",
                       '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                       '<rootfile full-path="c.opf"/></rootfiles></container>')
            z.writestr("c.opf", '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
                       '<item id="a" href="p1.svg" media-type="image/svg+xml"/></manifest>'
                       '<spine><itemref idref="a"/></spine></package>')
            z.writestr("p1.svg", svg)
        got = bookfiles.extract_epub(p, d)
        assert len(got) == 1
        with Image.open(got[0]) as im:
            assert has(im, (40, 60, 220)), "the SVG page was not drawn"


def test_refusals_are_plain():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        pages = [Image.new("RGB", (800, 1200), c) for c in COLORS[:2]]
        drm = os.path.join(d, "drm.epub")
        make_epub(drm, pages, "img", extra={"META-INF/encryption.xml": (
            '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
            'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
            '<enc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
            '<enc:CipherData><enc:CipherReference URI="OEBPS/text/page0.xhtml"/></enc:CipherData>'
            '</enc:EncryptedData></encryption>')})
        fonts = os.path.join(d, "fonts.epub")   # only scrambled fonts: normal, must work
        make_epub(fonts, pages, "img", extra={"META-INF/encryption.xml": (
            '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
            'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
            '<enc:EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/>'
            '<enc:CipherData><enc:CipherReference URI="OEBPS/font.ttf"/></enc:CipherData>'
            '</enc:EncryptedData></encryption>')})
        novel = os.path.join(d, "novel.epub")
        with zipfile.ZipFile(novel, "w") as z:
            z.writestr("mimetype", "application/epub+zip")
            z.writestr("META-INF/container.xml",
                       '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                       '<rootfile full-path="c.opf"/></rootfiles></container>')
            items = "".join(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>'
                            for i in range(5))
            z.writestr("c.opf", f'<package xmlns="http://www.idpf.org/2007/opf"><manifest>{items}'
                       '<item id="cov" href="cover.jpg" media-type="image/jpeg"/></manifest><spine>'
                       + "".join(f'<itemref idref="c{i}"/>' for i in range(5)) + '</spine></package>')
            z.writestr("cover.jpg", jpg_bytes(pages[0]))
            for i in range(5):
                z.writestr(f"c{i}.xhtml", "<html><body>" + "<p>It was a dark and stormy night. " * 80
                           + "</p></body></html>")
        broken = os.path.join(d, "broken.epub")
        open(broken, "wb").write(b"PK\x03\x04 not really")
        books, _ = converter.collect([drm, fonts, novel, broken])
        msgs = []
        res = converter.convert(books, ["kobo_clara"], (".epub",), os.path.join(d, "o"), log=msgs.append)
        text = "\n".join(msgs)
        assert [r["book"] for r in res] == ["fonts"], (res, text)
        assert "copy-protected" in text and "text book" in text and "not a working EPUB" in text, text


def test_numbers_and_names():
    cases = {"Solo Leveling - Chapter 052": "52", "Ep 3.5": "3.5", "Tower Ch.10": "10",
             "Series 2 Chapter 7": "7", "Manhwa #14": "14", "My Book 15": "15", "No number": None,
             "Chapter 001": "1", "Vol 3": "3"}
    for name, want in cases.items():
        assert coverart.number_in(name) == want, (name, coverart.number_in(name))
    assert coverart.badge_text(["X Chapter 1", "X Chapter 2", "X Chapter 6"]) == "#1-6"
    assert coverart.badge_text(["X Chapter 12"]) == "#12"
    assert coverart.badge_text(["Nothing"]) is None
    assert converter.combined_name([f"Empress Chapter {n:03d}" for n in range(1, 7)]) == "Empress Chapter 001-006"
    assert converter.combined_name(["epub 1", "epub 2", "epub 6"]) == "epub 1-6"
    assert converter.combined_name(["Alpha", "Beta", "Gamma"]) == "Alpha + 2 more"


def test_stamp_corners():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        src = os.path.join(d, "c.png")
        Image.new("RGB", (600, 900), (120, 160, 200)).save(src)
        for corner in ("ur", "ul", "lr", "ll"):
            out = coverart.stamp_cover(src, "#1-6", os.path.join(d, f"{corner}.png"), corner, 0.10, "dark")
            with Image.open(out) as im:
                a = np.asarray(im.convert("L"), dtype=np.int16)
            h, w = a.shape
            quads = {"ul": a[:h // 2, :w // 2], "ur": a[:h // 2, w // 2:],
                     "ll": a[h // 2:, :w // 2], "lr": a[h // 2:, w // 2:]}
            changed = {k: int((np.abs(v - 154) > 40).sum()) for k, v in quads.items()}
            assert max(changed, key=changed.get) == corner, (corner, changed)


def _chapters(d, n=3, h=1100):
    """n chapter folders 'Webtoon Chapter k', each 2 pictures of its own colour."""
    out = []
    for k in range(1, n + 1):
        f = os.path.join(d, f"Webtoon Chapter {k}")
        os.makedirs(f)
        for j in range(2):
            im = Image.new("RGB", (800, h), "white")
            im.paste(panel(h - 200, COLORS[k - 1], 700), (50, 100))
            im.save(os.path.join(f, f"{j}.png"))
        out.append(f)
    return out


def _epub_toc(path):
    with zipfile.ZipFile(path) as z:
        nav = z.read("OEBPS/nav.xhtml").decode()
        for n in z.namelist():
            if n.endswith((".opf", ".xhtml", ".ncx", ".xml")):
                xml.dom.minidom.parseString(z.read(n))
        imgs = sorted(n for n in z.namelist() if n.startswith("OEBPS/Images/"))
    import re
    return re.findall(r'href="Text/(\d+)\.xhtml">([^<]+)<', nav), imgs


def test_combine_fit_and_cover():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        folders = _chapters(d, 3)
        # chapter 2 arrives as an EPUB made by another program
        ep = os.path.join(d, "Webtoon Chapter 2.epub")
        make_epub(ep, [Image.open(os.path.join(folders[1], f"{j}.png")).convert("RGB") for j in range(2)], "svg")
        books, _ = converter.collect([folders[0], ep, folders[2]])
        cov = os.path.join(d, "cover.png")
        Image.new("RGB", (600, 900), (120, 160, 200)).save(cov)
        out = os.path.join(d, "out")
        res = converter.combine(books, "", True, ["kobo_clara", "kindle_pw7"], (".epub", ".cbz"), out,
                                cover={"mode": "picture", "path": cov, "number": True, "corner": "ur",
                                       "size": 0.07, "style": "dark"})
        assert len(res) == 2
        kobo = [r for r in res if "Kobo" in r["device"]][0]
        kepub = [f for f in kobo["files"] if f.endswith(".epub")][0]
        assert os.path.basename(kepub) == "Webtoon Chapter 1-3.epub", kobo["files"]
        toc, imgs = _epub_toc(kepub)
        assert [t for _, t in toc] == ["Webtoon Chapter 1", "Webtoon Chapter 2", "Webtoon Chapter 3"], toc
        assert toc[0][0] == "0001", "the contents starts at page 1 (the cover)"
        assert len(imgs) == 1 + 3 * 2, imgs
        with zipfile.ZipFile(kepub) as z, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            z.extractall(t)
            ims = [Image.open(os.path.join(t, n)) for n in imgs]
            assert all(im.size == (1072, 1448) for im in ims)
            assert colors_of([os.path.join(t, n) for n in imgs[1:]]) == [0, 0, 1, 1, 2, 2]
            cover = ims[0].convert("L")
            assert np.asarray(cover)[:300, 700:].min() < 80, "the #1-3 is on the cover, upper right"
            for im in ims:
                im.close()
        # each chapter starts on its own screen: the contents points at the right pages
        assert [int(p) for p, _ in toc] == [1, 4, 6], toc
        kindle = [r for r in res if "Kindle" in r["device"]][0]
        assert any(f.endswith(".pdf") for f in kindle["files"])
        # originals untouched
        assert os.path.isfile(ep) and len(os.listdir(folders[0])) == 2


def test_combine_keep_as_is():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        folders = _chapters(d, 2)
        Image.open(os.path.join(folders[1], "0.png")).save(os.path.join(folders[1], "2.webp"))
        books, _ = converter.collect(folders)
        out = os.path.join(d, "out")
        res = converter.combine(books, "My Joined Book", False, [], (".epub", ".cbz", ".pdf"), out)
        assert len(res) == 1 and res[0]["folder"] == os.path.join(out, "Combined")
        ep = [f for f in res[0]["files"] if f.endswith(".epub")][0]
        toc, imgs = _epub_toc(ep)
        assert len(imgs) == 5 and [t for _, t in toc] == ["Webtoon Chapter 1", "Webtoon Chapter 2"]
        assert all(n.endswith((".png", ".jpg")) for n in imgs), "WebP turned into JPEG for readers"
        with zipfile.ZipFile(ep) as z:
            with z.open(imgs[0]) as f, Image.open(f) as im:
                assert im.size == (800, 1100), "kept at its own size"


def test_combine_needs_two_and_skips_bad():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        folders = _chapters(d, 2)
        bad = os.path.join(d, "bad.epub")
        open(bad, "wb").write(b"nope")
        try:
            converter.combine(converter.collect(folders[:1])[0], "", False, [], (".epub",), d)
        except ValueError as e:
            assert "two" in str(e)
        else:
            raise AssertionError("one book cannot be combined")
        msgs = []
        books = converter.collect([folders[0], bad, folders[1]])[0]
        res = converter.combine(books, "", False, [], (".epub",), os.path.join(d, "o"), log=msgs.append)
        assert res and res[0]["parts"] == 2 and any("left out" in m for m in msgs), msgs


def test_own_epub_round_trip():
    """An EPUB made by EBZ CNVRTR, converted again for the same device, keeps its pages exactly
    (no second frame); for another device its pages are refitted to the new screen."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        folders = _chapters(d, 1)
        r1 = converter.convert(converter.collect(folders)[0], ["kobo_clara"], (".epub",),
                               os.path.join(d, "a"))
        ep = r1[0]["files"][0]
        n1 = r1[0]["pages"]
        r2 = converter.convert(converter.collect([ep])[0], ["kobo_clara", "kobo_sage"], (".epub",),
                               os.path.join(d, "b"))
        for r in r2:
            assert r["pages"] == n1, (r["device"], r["pages"], n1)
        _, imgs = _epub_toc([r for r in r2 if "Sage" in r["device"]][0]["files"][0])
        with zipfile.ZipFile([r for r in r2 if "Sage" in r["device"]][0]["files"][0]) as z:
            with z.open(imgs[0]) as f, Image.open(f) as im:
                assert im.size == (1440, 1920)


def test_first_page_cover():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        folders = _chapters(d, 1)
        res = converter.convert(converter.collect(folders)[0], ["kobo_clara"], (".cbz",),
                                os.path.join(d, "o"), cover={"mode": "first", "number": True,
                                                             "corner": "ul", "size": 0.10, "style": "light"})
        with zipfile.ZipFile(res[0]["files"][0]) as z:
            names = sorted(z.namelist())
            assert len(names) == 2, "page 1 became the cover, not an extra page"
            with z.open(names[0]) as f, Image.open(f) as im:
                a = np.asarray(im.convert("L"))
                assert a[:250, :400].max() > 240 and a[:250, :400].min() < 60, "white #1 upper left"


def test_one_page_book_with_first_page_cover():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        f = _chapters(d, 2)
        one = os.path.join(d, "One Chapter 1")
        os.makedirs(one)
        Image.open(os.path.join(f[0], "0.png")).save(os.path.join(one, "0.png"))
        first = {"mode": "first", "number": True}
        for fit in (False, True):
            r = converter.combine(converter.collect([one, f[1]])[0], "", fit, ["kobo_clara"], (".epub",),
                                  os.path.join(d, f"o{fit}"), cover=first)
            assert r[0]["pages"] == 3, r
        r = converter.convert(converter.collect([one])[0], ["kobo_clara"], (".cbz",), os.path.join(d, "c"),
                              cover=first)
        assert r and r[0]["pages"] == 1, r


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok ", name)
            except Exception:
                failed += 1
                tb = traceback.format_exc().strip().replace("\n", "%0A")
                print(f"::error title={name}::{tb}")
                print("FAILED", name)
    if failed:
        sys.exit(1)
    print("version 02 tests OK")
