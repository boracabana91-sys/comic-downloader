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
    test_cleaner()
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
            Image.new("RGB", (800, 4200), "white").save(os.path.join(d, name, "002.png"))
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
            dr.text((120, 1100), "luacomic.org", fill="black", font=font)
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


if __name__ == "__main__":
    main()
