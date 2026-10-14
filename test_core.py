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
        with tempfile.TemporaryDirectory() as d:
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
                z = zipfile.ZipFile(first)
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
                data = open(first, "rb").read()
                assert data.startswith(b"%PDF")
                import re
                pages = re.findall(rb"/Type\s*/Page(?![A-Za-z])", data)
                assert len(pages) > 5, len(pages)  # the strip became several PDF pages
    print("e-reader files OK")


if __name__ == "__main__":
    main()
