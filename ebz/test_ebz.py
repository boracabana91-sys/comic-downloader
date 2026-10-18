"""Tests for EBZ CNVRTR (run: python test_ebz.py). No window needed."""
import os
import sys
import tempfile
import zipfile
import xml.dom.minidom

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import converter  # noqa: E402
import devices  # noqa: E402
import fitpage  # noqa: E402
import version  # noqa: E402

COLORS = [(220, 40, 40), (40, 180, 40), (40, 60, 220), (230, 200, 30), (200, 40, 200),
          (30, 200, 200), (240, 130, 20)]


# ----- helpers copied from the proven test_fitpage.py -----
def panel(h, color, w=800):
    a = np.zeros((h, w, 3), dtype=np.uint8)
    a[:] = color
    for x in range(0, w, 40):
        a[:, x:x + 20] = [int(c * 0.6) for c in color]
    return Image.fromarray(a)


def strip(heights, gap=90, w=800, bg=(255, 255, 255)):
    total = sum(heights) + gap * (len(heights) + 1)
    im = Image.new("RGB", (w, total), bg)
    y = gap
    for h, c in zip(heights, COLORS):
        im.paste(panel(h, c, w), (0, y))
        y += h + gap
    return im


def has(page, color, tol=45, need=400):
    a = np.asarray(page.convert("RGB"), dtype=np.int16)
    d = np.abs(a - np.array(color)).max(axis=2)
    return int((d < tol).sum()) >= need


def where_panels(paths, n):
    pages = [Image.open(x).convert("RGB") for x in paths]
    return {i: [k for k, pg in enumerate(pages) if has(pg, c)] for i, c in enumerate(COLORS[:n])}


# ----- tests -----
def test_version():
    assert version.full_name() == f"{version.APP_NAME} {version.VERSION}" and version.APP_NAME == "EBZ CNVRBINE"
    assert version.VERSION.isdigit()


def test_snug_fit_every_device():
    """The webtoon sliced through its panels: on EVERY device each short scene stays whole
    on one screen, every screen is exactly the device size and the self-check finds no cut."""
    s = strip([500, 650, 420, 700, 600, 480], gap=90)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        src = os.path.join(d, "Webtoon")
        os.makedirs(src)
        n = 0
        for y in range(0, s.height, 1000):   # slices cut in the MIDDLE of panels
            s.crop((0, y, 800, min(s.height, y + 1000))).save(os.path.join(src, f"{n + 1}.png"))
            n += 1
        Image.new("RGB", (800, 400), "white").save(os.path.join(src, f"{n + 1}.png"))  # empty end
        books, _ = converter.collect([src])
        keys = [k for k in devices.DEVICE_KEYS if k != "custom"]
        out = os.path.join(d, "out")
        res = converter.convert(books, keys + ["custom"], (".cbz", ".epub"), out,
                                custom={"width": 900, "height": 1600, "gray": False})
        assert len(res) == len(keys) + 1
        for r in res:
            assert r["bad"] == 0 and r["screens"] > 0, r
            cbz = [f for f in r["files"] if f.endswith(".cbz")][0]
            dev = [devices.info(k, {"width": 900, "height": 1600}) for k in keys + ["custom"]
                   if devices.info(k, {"width": 900, "height": 1600})["label"] == r["device"]][0]
            with zipfile.ZipFile(cbz) as z, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
                z.extractall(t)
                pages = sorted(os.path.join(t, x) for x in os.listdir(t))
                for p in pages:
                    with Image.open(p) as im:
                        assert im.size == dev["size"], (r["device"], im.size)
                        lo, hi = im.convert("L").getextrema()
                        assert hi - lo > 20, f"{r['device']}: an empty screen was made"
                if dev["gray"]:
                    continue   # black-and-white: the same sizes are checked on colour devices
                w = where_panels(pages, 6)
                for i in range(6):
                    assert len(w[i]) == 1, f"{r['device']}: panel {i} cut across screens {w}"
        print(f"  snug fit clean on all {len(res)} device sizes")


def test_tall_scene_and_normal_pages():
    """Proven fitpage behaviour kept: a 4-screen scene is split, short ones share a screen,
    a normal book page is fitted whole."""
    W, H = 1072, 1448
    s = strip([500, 650, 420, 1500, 5200, 600])
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cuts = [0, 1300, 5200, s.height]
        for i in range(3):
            s.crop((0, cuts[i], 800, cuts[i + 1])).save(os.path.join(d, f"{i:03d}.png"))
        out = os.path.join(d, "out")
        os.makedirs(out)
        p = fitpage.FitPager(out, W, H, False)
        for i in range(3):
            p.add(os.path.join(d, f"{i:03d}.png"))
        p.flush()
        w = where_panels(p.pages, 6)
        for i in (0, 1, 2, 3, 5):
            assert len(w[i]) == 1, w
        assert len(w[4]) >= 2 and w[0] == w[1], w
        Image.new("RGB", (900, 1300), (10, 10, 10)).save(os.path.join(d, "book.png"))
        q = fitpage.FitPager(out, W, H, True)
        q.add(os.path.join(d, "book.png"))
        q.flush()
        assert len(q.pages) == 1 and Image.open(q.pages[0]).size == (W, H)


def photo(seed, w=900, h=1200):
    """A smooth, photo-like picture (gradients and shapes) that fills its whole frame."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    c = rng.random((3, 3)) * 255
    a = np.stack([c[i, 0] + (c[i, 1] - c[i, 0]) * y / h + 30 * np.sin(x / (40 + 30 * c[i, 2] / 255))
                  for i in range(3)], axis=2)
    for _ in range(6):
        cx, cy, r = rng.integers(0, w), rng.integers(0, h), rng.integers(40, 200)
        a[(x - cx) ** 2 + (y - cy) ** 2 < r * r] = rng.random(3) * 255
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def test_photos_and_full_pages_stay_separate():
    """Separate photos (art touching every edge) are one screen each, never merged; while a
    photo-like webtoon cut into slices is still joined across the cuts."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        for i in range(4):
            photo(i).save(os.path.join(d, f"p{i}.jpg"), quality=90)
        photo(9, 1200, 900).save(os.path.join(d, "p4.jpg"), quality=90)   # one landscape
        out = os.path.join(d, "o")
        os.makedirs(out)
        pages, screens, bad = converter.fit_pages([os.path.join(d, f"p{i}.jpg") for i in range(5)],
                                                  out, 1072, 1448, False)
        assert len(pages) == 5, f"5 photos must make 5 screens, got {len(pages)}"
        # a long smooth picture cut into 4 slices (no gaps): joined, so the result is NOT
        # 4 separately fitted slices with the cuts on screen edges
        big = photo(5, 800, 4400)
        sl = os.path.join(d, "sl")
        os.makedirs(sl)
        for i in range(4):
            big.crop((0, i * 1100, 800, (i + 1) * 1100)).save(os.path.join(sl, f"{i}.jpg"), quality=92)
        p = converter.Pager(out, 1072, 1448, False)
        for i in range(4):
            p.add(os.path.join(sl, f"{i}.jpg"))
            assert i == 0 or p.hold is None, "slice was not joined to the one before"
        p.flush()


def test_collect_rules():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        a = os.path.join(d, "Series A")
        os.makedirs(os.path.join(a, "Chapter 2"))
        os.makedirs(os.path.join(a, "Chapter 10"))
        for sub in ("Chapter 2", "Chapter 10"):
            for n in (1, 2, 10):
                Image.new("RGB", (50, 70)).save(os.path.join(a, sub, f"page{n}.jpg"))
        Image.new("RGB", (50, 70)).save(os.path.join(a, "._junk.jpg"))   # Mac leftovers ignored
        open(os.path.join(a, "notes.txt"), "w").close()
        loose = os.path.join(d, "Loose")
        os.makedirs(loose)
        for n in (3, 1, 20):
            Image.new("RGB", (50, 70)).save(os.path.join(loose, f"{n}.png"))
        books, skipped = converter.collect([a] + [os.path.join(loose, f"{n}.png") for n in (3, 1, 20)]
                                           + [os.path.join(d, "missing.jpg")])
        names = [b.name for b in books]
        assert names == ["Chapter 2", "Chapter 10", "Loose"], names
        assert [os.path.basename(x) for x in books[0].items] == ["page1.jpg", "page2.jpg", "page10.jpg"]
        assert [os.path.basename(x) for x in books[2].items] == ["1.png", "3.png", "20.png"]
        assert len(skipped) == 1
        dup = converter.unique_names([converter.Book("X", "images", []), converter.Book("x", "images", [])])
        assert [b.name for b in dup] == ["X", "x (2)"]


def test_pdf_cbz_photo_inputs():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        # a 3-page PDF
        pdf = os.path.join(d, "Manual.pdf")
        pages = [Image.new("RGB", (600, 850), c) for c in COLORS[:3]]
        for pg in pages:
            pg.paste(panel(500, (0, 0, 0), 500), (50, 100))
        pages[0].save(pdf, "PDF", save_all=True, append_images=pages[1:], resolution=72)
        # a CBZ made by some other program
        cbz = os.path.join(d, "Other.cbz")
        with zipfile.ZipFile(cbz, "w") as z:
            for i in (2, 1, 10):
                p = os.path.join(d, f"c{i}.png")
                Image.new("RGB", (700, 1000), COLORS[i % 7]).save(p)
                z.write(p, f"pages/{i}.png")
            z.writestr("__MACOSX/pages/._1.png", b"junk")
        # a phone photo stored sideways with a 'turn me' tag, and a see-through PNG
        ph_dir = os.path.join(d, "Photos")
        os.makedirs(ph_dir)
        ph = Image.new("RGB", (1600, 1200), (250, 0, 0))
        ph.paste(Image.new("RGB", (100, 1200), (0, 0, 250)), (0, 0))
        ex = ph.getexif()
        ex[0x0112] = 6
        ph.save(os.path.join(ph_dir, "IMG_1.jpg"), exif=ex)
        Image.new("RGBA", (800, 1100), (0, 0, 0, 0)).save(os.path.join(ph_dir, "IMG_2.png"))
        books, _ = converter.collect([pdf, cbz, ph_dir])
        assert [b.kind for b in books] == ["pdf", "archive", "images"], books
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            srcs = converter.page_sources(books[0], t, 1072)
            assert len(srcs) == 3 and Image.open(srcs[0]).width >= 1072
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            srcs = converter.page_sources(books[1], t, 1072)
            assert len(srcs) == 3
            assert Image.open(srcs[0]).getpixel((5, 5)) == COLORS[1]   # 1, 2, 10 order
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            srcs = converter.page_sources(books[2], t, 1072)
            with Image.open(srcs[0]) as im:
                assert im.height > im.width, "the photo was turned upright"
        out = os.path.join(d, "out")
        res = converter.convert(books, ["kobo_clara", "kindle_pw7", "ipad"], (".cbz", ".epub"), out)
        assert len(res) == 9 and all(r["bad"] == 0 and not r["problems"] for r in res), res
        kindle = [r for r in res if r["kind"] == "kindle"]
        assert all(any(f.endswith(".pdf") for f in r["files"]) for r in kindle), "Kindle gets a PDF"
        kobo = [r for r in res if r["kind"] == "kobo"]
        assert all(not any(f.endswith(".pdf") for f in r["files"]) for r in kobo)
        assert os.path.isfile(os.path.join(out, "Kobo Clara", "Manual.epub"))
        # Kindle pages are black-and-white, Kobo Clara pages are colour
        with zipfile.ZipFile(os.path.join(out, "Kindle Paperwhite 7in", "Other.cbz")) as z:
            with z.open(z.namelist()[0]) as f, Image.open(f) as im:
                assert im.mode == "L" and im.size == (1264, 1680)
        with zipfile.ZipFile(os.path.join(out, "Kobo Clara", "Other.cbz")) as z:
            with z.open(z.namelist()[0]) as f, Image.open(f) as im:
                assert im.mode == "RGB" and im.size == (1072, 1448)


def test_epub_is_valid_fixed_layout():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        src = os.path.join(d, "Tom & Jerry's")
        os.makedirs(src)
        for i in range(3):
            panel(1100, COLORS[i]).save(os.path.join(src, f"{i}.png"))
        books, _ = converter.collect([src])
        res = converter.convert(books, ["kobo_libra"], (".epub",), os.path.join(d, "o"))
        ep = res[0]["files"][0]
        assert ep.endswith(".epub")
        with zipfile.ZipFile(ep) as z:
            first = z.infolist()[0]
            assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
            assert z.read("mimetype") == b"application/epub+zip"
            for n in z.namelist():
                if n.endswith((".opf", ".xhtml", ".ncx", ".xml")):
                    xml.dom.minidom.parseString(z.read(n))   # every XML part is well formed
            opf = z.read("OEBPS/content.opf").decode()
            assert "pre-paginated" in opf and "1264x1680" in opf
            imgs = [n for n in z.namelist() if n.startswith("OEBPS/Images/")]
            assert len(imgs) == 3


def test_errors_are_plain():
    for args, word in (([], "nothing"), ([converter.Book("a", "images", ["x"])], "device")):
        try:
            converter.convert(args, [] if args else ["kobo_clara"], (".cbz",), "/tmp/x")
        except ValueError as e:
            assert word in str(e).lower(), e
        else:
            raise AssertionError("no error")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        bad = os.path.join(d, "Broken.pdf")
        open(bad, "wb").write(b"not a pdf")
        msgs = []
        res = converter.convert(converter.collect([bad])[0], ["kobo_clara"], (".cbz",), d,
                                log=msgs.append)
        assert res == [] and "could not be read" in msgs[0], msgs


def test_selftest():
    assert converter.selftest()


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok ", name)
            except Exception:
                failed += 1
                tb = traceback.format_exc().strip().replace("\n", "%0A")
                print(f"::error title={name}::{tb}")   # shows as a note on the GitHub build
                print("FAILED", name)
    if failed:
        sys.exit(1)
    print("EBZ CNVRBINE tests OK")
