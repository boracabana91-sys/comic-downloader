"""Self-test: serves a fake chapter page locally and checks the 5-page folder grouping."""
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import core

N = 12
PAGE = """<html><head><title>My Comic - Chapter 7 - Lua Comic</title></head><body>
<img src="/static/logo.png">
%s
<img src="/ads/promo.jpg">
<img src="/thumbs/other1.jpg"><img src="/thumbs/other2.jpg">
<script>var x = {"p": ["%s"]};</script>
</body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/chapter":
            tags = "".join(f'<img data-src="/img/{i:02d}.webp" src="data:image/gif;base64,AAAA">'
                           for i in range(1, 10))
            extra = '","'.join(f"http:\\/\\/127.0.0.1:{self.server.server_port}\\/img\\/{i:02d}.webp"
                               for i in range(10, N + 1))
            body = (PAGE % (tags, extra)).encode()
        elif self.path.startswith("/img/"):
            body = os.urandom(500)
        else:
            body = b"x" * 300
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)


def test_epub_and_padding():
    """Extra EPUB next to the gadget's own file, full-screen pages, no white bars on dark art."""
    if not core.HAS_PIL:
        return
    import zipfile
    from PIL import Image, ImageDraw
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        # dark webtoon strip split over two files, with a dark gap between panels
        title = "Book"
        folder = os.path.join(d, core.group_folder_name(title, 1, 2, 5))
        os.makedirs(folder)
        for i in (1, 2):
            im = Image.new("RGB", (800, 3000), (12, 12, 12))
            dr = ImageDraw.Draw(im)
            for y in range(100, 2900, 700):
                dr.rectangle((60, y, 740, y + 520), fill=(150, 40, 60))
                dr.text((120, y + 200), "panel", fill="white")
            im.save(os.path.join(folder, f"{i:03d}.webp"))
        before = {f: os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder)}
        made, bad = core.build_device_files(d, title, 2, 5, "kobo", epub=True)
        assert bad == [], bad
        names = sorted(os.path.basename(m) for m in made)
        assert names == ["Book - Pages 1-2.cbz", "Book - Pages 1-2.epub"], names
        after = {f: os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder)}
        assert before == after  # the original images (master files) are never changed
        cbz = [m for m in made if m.endswith(".cbz")][0]
        with zipfile.ZipFile(cbz) as z:
            pages = sorted(z.namelist())
            for n in pages:
                with z.open(n) as fh:
                    im = Image.open(fh).convert("RGB")
                    assert im.size == (1072, 1448)
                    for xy in ((3, 3), (536, 2), (536, 1445), (1068, 1444)):
                        assert min(im.getpixel(xy)) < 120, (n, xy, im.getpixel(xy))  # no white bars
        epub = [m for m in made if m.endswith(".epub")][0]
        with zipfile.ZipFile(epub) as z:
            info = z.infolist()
            assert info[0].filename == "mimetype" and info[0].compress_type == zipfile.ZIP_STORED
            assert z.read("mimetype") == b"application/epub+zip"
            opf = z.read("OEBPS/content.opf").decode()
            assert "cover-image" in opf and 'properties="svg"' in opf
            pics = [n for n in z.namelist() if n.startswith("OEBPS/Images/")]
            assert len(pics) == len(pages), (len(pics), len(pages))  # every picture is inside
            page1 = z.read("OEBPS/Text/0001.xhtml").decode()
            assert "../Images/0001.jpg" in page1
        # Kindle gets its PDF plus the EPUB, with a note
        made, bad = core.build_device_files(d, title, 2, 5, "kindle_6", epub=True)
        assert sorted(os.path.splitext(m)[1] for m in made) == [".epub", ".pdf"], made
        assert "Kindle" in core.epub_note("kindle_6")
        # "Just the images" + EPUB
        made, bad = core.build_device_files(d, title, 2, 5, "epub_only")
        assert len(made) == 1 and made[0].endswith(".epub"), made
    print("EPUB and full-screen pages OK")


def main():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/chapter"
    info = core.inspect_page(url)
    assert info["title"] == "My Comic - Chapter 7", info["title"]
    assert len(info["images"]) == N, (len(info["images"]), info["images"])
    with tempfile.TemporaryDirectory() as d:
        failed = core.download_images(info["images"], info["title"], d, url)
        assert failed == [], failed
        folders = sorted(os.listdir(d))
        assert folders == ["My Comic - Chapter 7 - Pages 1-5",
                           "My Comic - Chapter 7 - Pages 11-12",
                           "My Comic - Chapter 7 - Pages 6-10"], folders
        assert sorted(os.listdir(os.path.join(d, folders[2]))) == [
            "006.webp", "007.webp", "008.webp", "009.webp", "010.webp"]
    test_devices()
    test_all_presets()
    test_epub_and_padding()
    test_cleaner()
    test_covers()
    print("ALL TESTS PASSED")


def test_devices():
    """Kobo .cbz and Kindle .pdf: tall strips are cut at blank rows, every page is screen-sized."""
    if not core.HAS_PIL:
        print("(skipped e-reader test: Pillow not installed)")
        return
    import io
    import zipfile
    from PIL import Image, ImageDraw

    title, total, size = "Strip", 7, 5
    for key, ext in (("kobo", ".cbz"), ("kindle_68", ".pdf")):
        W, H = core.DEVICES[key]["size"]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            for i in range(1, total + 1):
                folder = os.path.join(d, core.group_folder_name(title, i, total, size))
                os.makedirs(folder, exist_ok=True)
                if i == 2:  # tall webtoon strip with dark "text" bars and white gaps
                    im = Image.new("RGB", (800, 7000), "white")
                    dr = ImageDraw.Draw(im)
                    for y in range(60, 6900, 140):
                        dr.rectangle((100, y, 700, y + 60), fill="black")
                    im.save(os.path.join(folder, f"{i:03d}.png"))
                else:
                    Image.new("RGBA", (900, 1300), (240, 240, 240, 255)).save(
                        os.path.join(folder, f"{i:03d}.webp"))
            made, bad = core.build_device_files(d, title, total, size, key)
            assert bad == [], bad
            names = sorted(os.path.basename(m) for m in made)
            assert names == [f"Strip - Pages 1-5{ext}", f"Strip - Pages 6-7{ext}"], names
            first = [m for m in made if "Pages 1-5" in m][0]
            if ext == ".cbz":
                with zipfile.ZipFile(first) as z:
                    files = sorted(z.namelist())
                    assert len(files) > 5, len(files)  # the strip became several pages
                    for f in files:
                        im = Image.open(io.BytesIO(z.read(f)))
                        assert im.size == (W, H), (f, im.size)
                        g = im.convert("L")
                        # cuts land on blank rows: top and bottom edge of every page are clear
                        for edge in (0, H - 1):
                            row = g.crop((0, edge, W, edge + 1))
                            assert row.getextrema()[0] > 200, (f, edge)
            else:
                with open(first, "rb") as fh:
                    data = fh.read()
                assert data.startswith(b"%PDF")
                import re
                pages = re.findall(rb"/Type\s*/Page(?![A-Za-z])", data)
                assert len(pages) > 5, len(pages)  # the strip became several PDF pages
    print("e-reader files OK")


def test_all_presets():
    """Every gadget in the Send to menu (and Custom size) makes correctly sized files."""
    if not core.HAS_PIL:
        return
    import io
    import zipfile
    from PIL import Image

    custom = {"width": 1000, "height": 1500, "ext": ".cbz", "gray": True}
    count = 0
    for key in core.DEVICE_KEYS:
        if key == "images":
            continue
        dev = core.resolve_device(key, custom if key == "custom" else None)
        W, H = dev["size"]
        assert dev["next"].startswith("Next:") and dev["folder"] in dev["next"], key
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            name = core.group_folder_name("Book", 1, 2, 5)
            os.makedirs(os.path.join(d, name))
            Image.new("RGB", (900, 1300), (200, 220, 240)).save(os.path.join(d, name, "001.png"))
            strip = Image.new("RGB", (800, 4200), "white")
            for y in range(100, 4100, 300):
                strip.paste((30, 30, 30), (80, y, 720, y + 200))  # panels with white gaps
            strip.save(os.path.join(d, name, "002.png"))
            made, bad = core.build_device_files(d, "Book", 2, 5, key,
                                                custom=custom if key == "custom" else None)
            assert bad == [] and len(made) == 1, (key, made, bad)
            assert made[0].endswith(dev["ext"]) and os.path.basename(
                os.path.dirname(made[0])) == dev["folder"], (key, made)
            if dev["ext"] == ".cbz":
                with zipfile.ZipFile(made[0]) as z:
                    names = sorted(z.namelist())
                    assert len(names) >= 3, (key, names)
                    im = Image.open(io.BytesIO(z.read(names[0])))
                    assert im.size == (W, H), (key, im.size)
                    if dev["gray"]:
                        assert im.mode == "L", (key, im.mode)
            else:
                with open(made[0], "rb") as fh:
                    assert fh.read(5) == b"%PDF-", key
        count += 1
    # colour devices keep colour; gray devices become black and white
    assert core.DEVICES["kindle_color"]["gray"] is False
    assert core.DEVICES["kindle_68"]["gray"] is True
    print(f"all {count} gadget choices OK")


def test_cleaner():
    """The words are found anywhere on a page and hidden: banner cut, plain text painted out."""
    import cleaner
    from PIL import Image, ImageDraw, ImageFont

    assert cleaner.text_matches("READATLUACOMIC.ORGTO", ["luacomic.org"])
    assert cleaner.text_matches("read at LUACOM1C.ORG to", ["luacomic.org"])  # reader slip
    assert not cleaner.text_matches("hello there", ["luacomic.org"])
    dw = cleaner.all_words("")
    assert cleaner.text_matches("LUA SCANS", dw) and cleaner.text_matches("THIS CHAPTER IS TRANSLATED", dw)
    assert not cleaner.text_matches("a valuable thing", dw)
    assert not cleaner.text_matches("Translator: Sam / Editor: Joy", dw)  # credits stay
    assert cleaner.parse_words("luacomic.org, other site") == ["luacomic.org", "other site"]
    if not cleaner.ocr_available():
        print("(skipped page-reading test: text reader not installed)")
        return

    font = ImageFont.load_default(size=36)
    words = ["luacomic.org"]

    def page(path, kind):
        im = Image.new("RGB", (600, 1600), "white")
        dr = ImageDraw.Draw(im)
        dr.rectangle((100, 100, 500, 900), fill=(190, 200, 230))  # some artwork
        if kind == "bottom":
            dr.rectangle((0, 1300, 600, 1600), fill=(18, 18, 18))
            dr.text((70, 1420), "READ AT LUACOMIC.ORG TO", fill="white", font=font)
        elif kind == "top":
            im = Image.new("RGB", (600, 1600), "white")
            dr = ImageDraw.Draw(im)
            dr.rectangle((100, 500, 500, 1300), fill=(190, 200, 230))
            dr.rectangle((0, 0, 600, 300), fill=(18, 18, 18))
            dr.text((70, 120), "READ AT LUACOMIC.ORG TO", fill="white", font=font)
        elif kind == "middle":
            dr.text((120, 400), "luacomic.org", fill="black", font=font)
        elif kind == "banner_only":
            im = Image.new("RGB", (600, 300), (18, 18, 18))
            ImageDraw.Draw(im).text((70, 120), "READ AT LUACOMIC.ORG TO", fill="white", font=font)
        elif kind == "clean":
            dr.text((120, 1100), "hello world", fill="black", font=font)
        im.save(path)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        eng = cleaner.get_engine()
        for kind, expect in (("bottom", "cut"), ("top", "cut"), ("middle", "blurred"),
                             ("banner_only", "deleted"), ("clean", "none")):
            p = os.path.join(d, kind + ".png")
            page(p, kind)
            with open(p, "rb") as fh:
                before = fh.read()
            got = cleaner.clean_image(p, words, eng)
            assert got == expect, (kind, got)
            if kind in ("bottom", "top"):
                h = Image.open(p).size[1]
                assert 1250 <= h <= 1330, (kind, h)  # the 300 px banner is gone
            if kind == "clean":
                with open(p, "rb") as fh:
                    assert fh.read() == before  # pages without the words are never touched
            if kind == "banner_only":
                assert not os.path.exists(p)
            elif os.path.exists(p):
                assert cleaner.clean_image(p, words, eng) == "none", kind  # nothing left to find

        # whole chapter: group folders, then a second run skips pages already done
        title = "Book"
        folder = os.path.join(d, core.group_folder_name(title, 1, 3, 5))
        os.makedirs(folder)
        page(os.path.join(folder, "001.png"), "clean")
        page(os.path.join(folder, "002.png"), "bottom")
        page(os.path.join(folder, "003.png"), "middle")
        c = cleaner.clean_chapter(d, title, 3, 5, words)
        assert c == {"scanned": 3, "cut": 1, "blurred": 1, "deleted": 0, "skipped": 0}, c
        c2 = cleaner.clean_chapter(d, title, 3, 5, words)
        assert c2["scanned"] == 0, c2
    print("word hiding OK")


def test_covers():
    """Cover picture: fitted as page 1, saved as cover.jpg, shown on the folder (Mac, Windows)."""
    import io
    import re
    import sys
    import zipfile
    import covers
    from PIL import Image
    if not core.HAS_PIL:
        return

    def is_red(px):
        return px[0] > 180 and px[1] < 80 and px[2] < 80

    def is_blue(px):
        return px[2] > 150 and px[0] < 100

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cover = os.path.join(d, "my cover.png")
        Image.new("RGB", (300, 500), (220, 20, 20)).save(cover)
        fake = os.path.join(d, "x.png")
        with open(fake, "wb") as fh:
            fh.write(b"not a picture")
        assert covers.is_cover_file(cover)
        assert not covers.is_cover_file(fake)
        assert not covers.is_cover_file(os.path.join(d, "missing.png"))

        fit = covers.fit_cover(cover, 1072, 1448, False, os.path.join(d, "fit.jpg"))
        im = Image.open(fit)
        assert im.size == (1072, 1448) and is_red(im.getpixel((536, 724)))

        title = "Cov"
        folder = os.path.join(d, core.group_folder_name(title, 1, 2, 5))
        os.makedirs(folder)
        for i in (1, 2):
            Image.new("RGB", (900, 1300), (30, 30, 200)).save(os.path.join(folder, f"{i:03d}.png"))
        res = covers.apply_folder_covers(d, title, 2, 5, cover)
        assert res["folders"] == 1 and res["problems"] == [], res
        assert os.path.exists(os.path.join(folder, "cover.jpg"))
        if sys.platform == "darwin":  # Finder keeps a custom picture in a hidden "Icon" file
            assert res["icons"] == 1 and os.path.exists(os.path.join(folder, "Icon\r")), res
        elif sys.platform.startswith("win"):
            assert res["icons"] == 1, res
            with open(os.path.join(folder, "desktop.ini"), encoding="utf-8") as fh:
                assert "IconResource=cover.ico" in fh.read()
            assert os.path.exists(os.path.join(folder, "cover.ico"))
        else:
            assert res["icons"] == 0, res

        made, bad = core.build_device_files(d, title, 2, 5, "kobo", cover=cover)
        assert bad == [] and len(made) == 1, (made, bad)
        with zipfile.ZipFile(made[0]) as z:
            names = sorted(z.namelist())
            assert len(names) == 3, names  # cover + 2 pages; cover.jpg is not counted as a page
            assert is_red(Image.open(io.BytesIO(z.read(names[0]))).getpixel((536, 724)))
            assert is_blue(Image.open(io.BytesIO(z.read(names[1]))).getpixel((536, 724)))

        made, bad = core.build_device_files(d, title, 2, 5, "kindle_68", cover=cover)
        with open(made[0], "rb") as fh:
            data = fh.read()
        assert len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", data)) == 3

        import cleaner
        if cleaner.ocr_available():
            c = cleaner.clean_chapter(d, title, 2, 5, ["luacomic.org"])
            assert c["scanned"] == 2, c  # the cover.jpg is never scanned or changed
    print("covers OK")


if __name__ == "__main__":
    main()
