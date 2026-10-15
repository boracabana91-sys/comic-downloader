"""End-to-end test of the series downloader against a small local website (no internet needed)."""
import http.server
import io
import os
import tempfile
import threading
import zipfile

from PIL import Image

import core
import series

COLORS = [(200, 30, 30), (30, 200, 30), (30, 30, 200)]


def png(color):
    b = io.BytesIO()
    im = Image.new("RGB", (900, 1300), color)
    for y in range(100, 1200, 40):  # stripes, so the page is not "empty background"
        im.paste((10, 10, 10), (100, y, 800, y + 15))
    im.save(b, "PNG")
    return b.getvalue()


class Site(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/series/hidden":  # chapter list is NOT in the page: only the series number
            body = ('<html><head><title>Hidden Comic - Lua Comic</title></head><body>'
                    '<script>self.__next_f.push([1,"{\\"series_id\\":769}"])</script></body></html>')
        elif path == "/chapter/query":
            page = int(self.path.split("page=")[1].split("&")[0])
            rows = [3, 2, 1][(page - 1) * 2: page * 2]  # 2 per page here, newest first
            import json as _j
            body = _j.dumps({"meta": {"total": 3, "last_page": 2, "current_page": page},
                             "data": [{"chapter_name": f"Chapter {n}", "chapter_slug": f"chapter-{n}",
                                       "price": 0, "series": {"series_slug": "hidden"}}
                                      for n in rows]})
        elif path == "/series/demo":
            # newest first, one link twice, a sidebar link to ANOTHER series, one broken chapter
            links = "".join(f'<a href="/series/demo/chapter-{n}">Chapter {n}</a>' for n in (3, 2, 1))
            body = ('<html><head><title>Demo Comic | Lua Comic</title></head><body>'
                    + links + '<a href="/series/demo/chapter-1">Chapter 1</a>'
                    '<a href="/series/other/chapter-99">Chapter 99</a></body></html>')
        elif path.startswith("/series/demo/chapter-"):
            n = path.rsplit("-", 1)[1]
            if n == "2" and not getattr(Site, "fixed", False):
                self.send_response(404)
                self.end_headers()
                return
            body = ('<html><head><title>Demo Comic Chapter %s</title></head><body>' % n
                    + "".join(f'<img src="/img/c{n}/{i}.png">' for i in (1, 2, 3)) + "</body></html>")
        elif path.startswith("/img/"):
            data = png(COLORS[int(path.rsplit("/", 1)[1][0]) - 1])
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(data)
            return
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    # --- finding the chapters ---
    info = series.inspect_series(base + "/series/demo")
    assert info["title"] == "Demo Comic", info["title"]
    assert [u.rsplit("-", 1)[1] for u in info["chapters"]] == ["1", "2", "3"], info["chapters"]
    hid = series.inspect_series(base + "/series/hidden", api_base=base)
    assert hid["title"] == "Hidden Comic" and hid["total"] == 3, hid
    assert [u.rsplit("/", 1)[1] for u in hid["chapters"]] == ["chapter-1", "chapter-2", "chapter-3"], hid
    assert hid["chapters"][0] == base + "/series/hidden/chapter-1"
    names = series.chapter_names("Demo Comic", info["chapters"])
    assert names[0] == "Demo Comic - Chapter 001" and names[2] == "Demo Comic - Chapter 003"
    assert series.chapter_number("https://x/a/chapter-12-5") == 12.5
    names2 = series.chapter_names("S", ["https://x/a/b", "https://x/a/c"])  # no numbers: by position
    assert names2 == ["S - Chapter 001", "S - Chapter 002"], names2

    # --- downloading: chapter 2 is broken at first, the others must still finish ---
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        opts = {"size": 2, "device": "kobo", "epub": True, "words": [], "cover": None}
        logs = []
        res = series.run_series("Demo Comic", info["chapters"], d, opts, say=logs.append, pause=0)
        assert len(res["done"]) == 2 and len(res["failed"]) == 1, res
        assert res["failed"][0][0].endswith("Chapter 002"), res["failed"]
        kobo = os.path.join(d, "Demo Comic", "For Kobo Clara")
        files = sorted(os.listdir(kobo))
        # 2 good chapters x 2 groups (pages 1-2, 3-3) x (.cbz + .epub)
        assert len([f for f in files if f.endswith(".cbz")]) == 4, files
        assert len([f for f in files if f.endswith(".epub")]) == 4, files
        with zipfile.ZipFile(os.path.join(kobo, "Demo Comic - Chapter 001 - Pages 1-2.cbz")) as z:
            assert len(z.namelist()) == 2
        assert os.path.isdir(os.path.join(d, "Demo Comic", "Demo Comic - Chapter 003 - Pages 1-2"))

        # --- run again after the website is fixed: only chapter 2 is done, others skipped ---
        Site.fixed = True
        res = series.run_series("Demo Comic", info["chapters"], d, opts, say=logs.append, pause=0)
        assert len(res["done"]) == 1 and len(res["skipped"]) == 2 and not res["failed"], res
        assert len([f for f in os.listdir(kobo) if f.endswith(".cbz")]) == 6

        # --- changing the gadget makes finished chapters be made again ---
        opts2 = dict(opts, device="kindle_68", epub=False)
        res = series.run_series("Demo Comic", info["chapters"], d, opts2, say=logs.append, pause=0)
        assert len(res["done"]) == 3 and not res["skipped"], res

        # --- ticking only some chapters keeps the numbering ---
        res = series.run_series("Demo Comic", info["chapters"][2:], d, dict(opts2, all_urls=info["chapters"], redo=True),
                                say=logs.append, pause=0)
        assert res["done"] == ["Demo Comic - Chapter 003"], res
    srv.shutdown()
    print("series OK")


if __name__ == "__main__":
    main()
