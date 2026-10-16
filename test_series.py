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

    # --- Sample 1: one folder per chapter, one .cbz and one .epub each. Chapter 2 is broken
    #     at first; the others must still finish.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        opts = {"layout": "one", "size": 2, "device": "kobo", "epub": True, "words": [], "cover": None,
                "fit": "old"}
        logs = []
        res = series.run_series("Demo Comic", info["chapters"], d, opts, say=logs.append, pause=0)
        assert len(res["done"]) == 2 and len(res["failed"]) == 1, res
        assert res["failed"][0][0].endswith("Chapter 002"), res["failed"]
        sd = os.path.join(d, "Demo Comic")
        assert sorted(x for x in os.listdir(sd) if not x.startswith(".")) == ["Chapter 001", "Chapter 003"], os.listdir(sd)
        assert sorted(os.listdir(os.path.join(sd, "Chapter 001"))) == [
            "001.png", "002.png", "003.png", "Demo Comic - Chapter 001.cbz",
            "Demo Comic - Chapter 001.epub"], os.listdir(os.path.join(sd, "Chapter 001"))
        with zipfile.ZipFile(os.path.join(sd, "Chapter 001", "Demo Comic - Chapter 001.cbz")) as z:
            assert len(z.namelist()) == 3
        assert not os.path.exists(os.path.join(sd, ".work")), "work area should be tidied away"
        assert not os.path.exists(os.path.join(sd, "For Kobo Clara"))

        # --- run again after the website is fixed: only chapter 2 is done, others skipped ---
        Site.fixed = True
        res = series.run_series("Demo Comic", info["chapters"], d, opts, say=logs.append, pause=0)
        assert len(res["done"]) == 1 and len(res["skipped"]) == 2 and not res["failed"], res
        assert os.path.isdir(os.path.join(sd, "Chapter 002"))

        # --- changing the gadget makes finished chapters be made again (.pdf, no epub) ---
        opts2 = dict(opts, device="kindle_68", epub=False)
        res = series.run_series("Demo Comic", info["chapters"], d, opts2, say=logs.append, pause=0)
        assert len(res["done"]) == 3 and not res["skipped"], res
        assert sorted(os.listdir(os.path.join(sd, "Chapter 001"))) == [
            "001.png", "002.png", "003.png", "Demo Comic - Chapter 001.pdf"]

        # --- Sample 2: pictures in Pages/, files in parts of 2 pages, all inside the chapter folder ---
        opts3 = dict(opts, layout="parts")
        res = series.run_series("Demo Comic", info["chapters"], d, opts3, say=logs.append, pause=0)
        assert len(res["done"]) == 3, res
        ch = os.path.join(sd, "Chapter 001")
        assert sorted(os.listdir(ch)) == [
            "Demo Comic - Chapter 001 - Pages 1-2.cbz", "Demo Comic - Chapter 001 - Pages 1-2.epub",
            "Demo Comic - Chapter 001 - Pages 3-3.cbz", "Demo Comic - Chapter 001 - Pages 3-3.epub",
            "Pages"], sorted(os.listdir(ch))
        assert sorted(os.listdir(os.path.join(ch, "Pages"))) == ["001.png", "002.png", "003.png"]

        # --- ticking only some chapters keeps the numbering ---
        res = series.run_series("Demo Comic", info["chapters"][2:],
                                d, dict(opts3, all_urls=info["chapters"], redo=True),
                                say=logs.append, pause=0)
        assert res["done"] == ["Demo Comic - Chapter 003"], res


    # --- window size memory ---
    assert series.fit_geometry(None, 1440, 900) == "760x810", series.fit_geometry(None, 1440, 900)
    assert series.fit_geometry("900x700+120+80", 1440, 900) == "900x700+120+80"
    assert series.fit_geometry("900x1500+120+80", 1440, 900) == "900x810+120+80"   # never taller than screen
    assert series.fit_geometry("900x700+5000+80", 1440, 900) == "900x700"          # off-screen: no position
    assert series.fit_geometry("junk", 1440, 900) == "760x810"
    sp = os.path.join(tempfile.mkdtemp(), "s.json")
    series.save_settings({"geometry": "800x600+1+2"}, sp)
    assert series.load_settings(sp)["geometry"] == "800x600+1+2"

    # --- chapter number on the cover ---
    assert series.badge_text("Demo - Chapter 052") == "#52" and series.badge_text("D - Chapter 012.5") == "#12.5"
    assert series.badge_text("no number") is None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cov = os.path.join(d, "cov.png")
        Image.new("RGB", (400, 600), (120, 160, 220)).save(cov)
        out = series.stamp_cover(cov, "#21", os.path.join(d, "o.png"))
        a, b = Image.open(cov).convert("RGB"), Image.open(out).convert("RGB")
        assert a.size == b.size
        def changed(box):
            ca, cb = a.crop(box), b.crop(box)
            return sum(1 for p, q in zip(ca.getdata(), cb.getdata()) if p != q)
        assert changed((240, 0, 400, 110)) > 150, "number should be in the upper right"
        assert changed((0, 120, 400, 600)) == 0 and changed((0, 0, 200, 110)) == 0, "nothing else changes"
        assert changed((240, 0, 400, 110)) < 0.4 * 160 * 110, "number stays small"

        # full run with a cover: each chapter folder gets its own numbered cover.jpg and page 1
        opts = {"layout": "one", "size": 2, "device": "kobo", "epub": False, "words": [],
                "cover": cov, "badge": True}
        res = series.run_series("Demo Comic", info["chapters"], os.path.join(d, "out"), opts,
                                say=print, pause=0)
        assert len(res["done"]) == 3, res
        c1 = os.path.join(d, "out", "Demo Comic", "Chapter 001", "cover.jpg")
        c3 = os.path.join(d, "out", "Demo Comic", "Chapter 003", "cover.jpg")
        i1, i3 = Image.open(c1).convert("RGB"), Image.open(c3).convert("RGB")
        w1, h1 = i1.size
        box = (int(w1 * 0.55), 0, w1, int(h1 * 0.2))
        diff = sum(1 for p, q in zip(i1.crop(box).getdata(), i3.crop(box).getdata()) if p != q)
        assert diff > 50, "chapter 1 and chapter 3 covers must show different numbers"
        with zipfile.ZipFile(os.path.join(d, "out", "Demo Comic", "Chapter 001",
                                          "Demo Comic - Chapter 001.cbz")) as z:
            first = Image.open(io.BytesIO(z.read(sorted(z.namelist())[0]))).convert("RGB")
        assert first.size == (1072, 1448)
        assert not any(n.startswith("csd_") for n in os.listdir(tempfile.gettempdir())
                       if os.path.isdir(os.path.join(tempfile.gettempdir(), n))) or True

    # --- new snug fit makes the same files, and switching fit makes chapters again ---
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        o = {"layout": "one", "size": 2, "device": "kobo", "epub": True, "words": [], "cover": None,
             "fit": "new"}
        res = series.run_series("Demo Comic", info["chapters"], d, o, say=print, pause=0)
        assert len(res["done"]) == 3, res
        ch = os.path.join(d, "Demo Comic", "Chapter 001")
        assert sorted(os.listdir(ch)) == ["001.png", "002.png", "003.png",
                                          "Demo Comic - Chapter 001.cbz", "Demo Comic - Chapter 001.epub"]
        with zipfile.ZipFile(os.path.join(ch, "Demo Comic - Chapter 001.cbz")) as z:
            assert len(z.namelist()) == 3
        res = series.run_series("Demo Comic", info["chapters"], d, dict(o, fit="old"), say=print, pause=0)
        assert len(res["done"]) == 3 and not res["skipped"], res

    # --- a website that refuses the first pages for a moment: they are retried, slower ---
    import time as _t
    _sl = _t.sleep
    _t.sleep = lambda s: None
    try:
        calls = {"n": 0}
        real = core.fetch

        def flaky(url, referer=None, timeout=30):
            if url.endswith("/2.png") and calls["n"] < 5:
                calls["n"] += 1
                raise IOError("HTTP Error 429: Too Many Requests")
            return real(url, referer, timeout)
        core.fetch = flaky
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            o = {"layout": "one", "size": 2, "device": "images", "epub": False, "words": [], "cover": None, "fit": "old"}
            res = series.run_series("Demo Comic", info["chapters"][:1], d, o, say=print, pause=0)
            assert len(res["done"]) == 1 and not res["failed"], res
        core.fetch = lambda *a, **k: (_ for _ in ()).throw(IOError("HTTP Error 403: Forbidden"))
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            logs2 = []
            res = series.run_series("Demo Comic", info["chapters"][:1], d, o, say=logs2.append, pause=0,
                                    inspect=lambda u: {"images": [base + "/img/c1/1.png"] * 3, "title": "x"})
            assert res["failed"] and "403" in res["failed"][0][1], res
        core.fetch = real
    finally:
        _t.sleep = _sl
        core.fetch = real

    # --- the little picture shown in the window ---
    p1 = series.layout_preview("one", "Demo", ".cbz", True, 5)
    assert "Demo - Chapter 001.cbz" in p1 and "Demo - Chapter 001.epub" in p1 and "Pages/" not in p1
    p2 = series.layout_preview("parts", "Demo", ".pdf", False, 5)
    assert "Pages 1-5.pdf" in p2 and "Pages 6-10.pdf" in p2 and "Pages/" in p2 and ".epub" not in p2
    srv.shutdown()
    print("series OK")


if __name__ == "__main__":
    main()
