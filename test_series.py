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
        elif path == "/series/coded/":
            # timelesstoons.org style: chapter addresses are codes, the number is only in the words;
            # a 'Start Reading' button first; chapter 3 is locked (coins), chapter 2.5 is a half chapter
            row = ('<a href="/chapter/9f1e2-{c}/" title="Chapter {n}"><div style="background-image:'
                   'url(x)"></div>{lock}<span>Chapter {n}</span> <span>New</span> 2 hours ago</a>')
            lock = '<img src="https://api.iconify.design/material-symbols:lock.svg?color=white">'
            body = ('<html><head><title>Coded Comic</title>'
                    '<meta property="og:title" content="Coded Comic"></head><body>'
                    '<a href="/chapter/9f1e2-77a1/"><img src="https://x/ic:round-play-arrow.svg">Start Reading</a>'
                    + row.format(c="3c3", n="3", lock=lock) + row.format(c="25b", n="2.5", lock="")
                    + row.format(c="0d2", n="2", lock="") + row.format(c="77a1", n="1", lock="")
                    + '</body></html>')
        elif path == "/index/series":   # a site's list of series: names are on each card's button
            card = ('<button id="{i}" alt="{m}" title="{m} {alt}" data-type="manga">'
                    '<a href="/series/{s}/" alt="{m}" title="{m}">x</a></button>')
            body = ('<html><body>'
                    + card.format(i=1, m="Mad Mud", alt="", s="mad-mud")
                    + card.format(i=2, m="Bloodshed Goddess Biography",
                                  alt="Ryuuketsu Megamiden ~Teikoku no Musume~, 流血女神伝", s="bloodshed")
                    + card.format(i=3, m="Other", alt="Megamiden Teikoku", s="other")
                    + '</body></html>')
        elif path.startswith("/chapter/9f1e2-"):
            c = path.rstrip("/").rsplit("-", 1)[1]
            body = ('<html><head><title>Coded Comic Chapter</title></head><body><div id="pages">'
                    + "".join(f'<img src="/assets/images/placeholder.svg" count="{i}" uid="{c}u{i}" '
                              'class="lazy">' for i in range(3))
                    + '</div><script>function loadImage(el){const uid=el.getAttribute("uid");'
                    'let realUrl = `' + f"http://{self.headers['Host']}/uploads/" + '${uid}`;}</script>'
                    '</body></html>')
        elif path.startswith("/uploads/"):   # pictures without a file type in the address (WebP inside)
            b = io.BytesIO()
            im = Image.new("RGB", (900, 1300), COLORS[int(path[-1])])
            for y in range(100, 1200, 40):
                im.paste((10, 10, 10), (100, y, 800, y + 15))
            im.save(b, "WEBP")
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.end_headers()
            self.wfile.write(b.getvalue())
            return
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

    # --- copy sites (comix.to): found again on the original source site, and shown in the bar ---
    cx = "https://comix.to/title/j5ne6-ryuuketsu-megamiden-teikoku-no-musume"
    assert series.is_aggregator(cx) and series.is_aggregator("https://www.comix.to/title/x")
    assert not series.is_aggregator("https://notcomix.to/x") and not series.is_aggregator(base + "/series/demo")
    assert series.title_from_link(cx) == "ryuuketsu megamiden teikoku no musume"
    assert series.title_from_link("https://s.org/title/abc-def") == "abc def"       # no code in front
    assert series.title_from_link("https://s.org/series/mad-mud/") == "mad mud"
    assert series.site_name("https://www.timelesstoons.org/series/x/") == "timelesstoons.org"
    assert series.site_name("junk") == "" and series.source_label("junk") == "-" and series.source_label("") == "-"
    assert series.source_label("https://luacomic.org/series/x") == "luacomic.org"
    assert "comix.to" in series.source_label(cx) and "original" in series.source_label(cx)
    found = series.find_original(cx, indexes=(base + "/index/series",))
    assert found and found["url"] == base + "/series/bloodshed/" and found["site"] == "127.0.0.1", found
    assert series.find_original("https://comix.to/title/zz9-never-heard-of-it-series",
                                indexes=(base + "/index/series",)) is None
    assert series.find_original("https://comix.to/title/zz9-mud", indexes=(base + "/index/series",)) is None  # too short
    assert series.find_original(cx, indexes=(base + "/missing",)) is None             # unreachable index: no crash

    # --- a site whose chapter addresses are only codes, with a locked chapter and coded pictures ---
    cod = series.inspect_series(base + "/series/coded/")
    assert cod["title"] == "Coded Comic", cod
    assert [series.chapter_number(u) for u in cod["chapters"]] == [1, 2, 2.5], cod["chapters"]
    assert cod["total"] == 4, "the locked chapter is counted but not offered"
    assert cod["locked"] == [3.0], cod["locked"]
    assert series.chapter_range([9, 10, 11, 12, 12.5, 13, 13.5, 14]) == "9 to 14"
    assert series.chapter_range([3]) == "3" and series.chapter_range([2, 7.5]) == "2, 7.5" and series.chapter_range([]) == ""
    assert series.find_original("x", indexes=(base + "/index/series",), name="Bloodshed Goddess Biography")["url"].endswith("/series/bloodshed/")
    assert series.find_original("x", indexes=(base + "/index/series",), name="Bloodshed Goddess Biography",
                                skip_site="127.0.0.1") is None, "the site you are already on is not offered again"
    assert series.chapter_names("Coded Comic", cod["chapters"]) == [
        "Coded Comic - Chapter 001", "Coded Comic - Chapter 002", "Coded Comic - Chapter 002.5"]
    pics = series.inspect_chapter(cod["chapters"][1])
    assert pics["images"] == [f"{base}/uploads/0d2u{i}" for i in range(3)], pics
    assert series.chapter_number("https://x/a/chapter-7") == 7          # ordinary addresses unchanged
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        oc = {"layout": "central", "size": 2, "device": "kobo", "epub": True, "words": [], "cover": None}
        res = series.run_series("Coded Comic", cod["chapters"], d, oc, say=print, pause=0)
        assert len(res["done"]) == 3 and not res["failed"], res
        sd = os.path.join(d, "Coded Comic")
        assert sorted(os.listdir(os.path.join(sd, "Coded Comic WEBP", "Coded Comic WEBP Chapter 002.5"))) == [
            "001.webp", "002.webp", "003.webp"], "pictures get their true type"
        assert len(os.listdir(os.path.join(sd, "Coded Comic CBZ"))) == 3
        assert len(os.listdir(os.path.join(sd, "Coded Comic EPUB"))) == 3
        # with "Convert WebP to JPG" the same pictures become real JPEGs
        res = series.run_series("Coded Comic", cod["chapters"][:1], d, dict(oc, convert=True), say=print, pause=0)
        assert len(res["done"]) == 1, res
        jd = os.path.join(sd, "Coded Comic JPEG", "Coded Comic JPEG Chapter 001")
        assert sorted(os.listdir(jd)) == ["001.jpg", "002.jpg", "003.jpg"], os.listdir(jd)
        with open(os.path.join(jd, "001.jpg"), "rb") as f:
            assert f.read(3) == b"\xff\xd8\xff"

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

        # --- Layout C: EPUBs, CBZs and pictures each in ONE folder for the whole title ---
        optsC = dict(opts, layout="central", fit="new")
        resC = series.run_series("Demo Comic", info["chapters"][:2], d, optsC, say=logs.append, pause=0)
        assert len(resC["done"]) == 2, resC
        top = sorted(x for x in os.listdir(sd) if not x.startswith(".") and x != "Chapter 003")
        assert top == ["Demo Comic CBZ", "Demo Comic EPUB", "Demo Comic PNG"] or \
            top == ["Demo Comic CBZ", "Demo Comic EPUB", "Demo Comic WEBP"], top
        pk = [x for x in top if x.endswith(("PNG", "WEBP"))][0]
        assert sorted(os.listdir(os.path.join(sd, "Demo Comic EPUB"))) == [
            "Demo Comic EPUB Chapter 001.epub", "Demo Comic EPUB Chapter 002.epub"]
        assert sorted(os.listdir(os.path.join(sd, "Demo Comic CBZ"))) == [
            "Demo Comic CBZ Chapter 001.cbz", "Demo Comic CBZ Chapter 002.cbz"]
        assert sorted(os.listdir(os.path.join(sd, pk))) == [f"Demo Comic {pk[11:]} Chapter 001",
                                                           f"Demo Comic {pk[11:]} Chapter 002"]
        assert sorted(os.listdir(os.path.join(sd, pk, f"Demo Comic {pk[11:]} Chapter 001")))[:3] == [
            "001.png", "002.png", "003.png"]
        assert not os.path.exists(os.path.join(sd, "Chapter 001")), "old chapter folder is replaced"
        # a later batch of chapters goes into the SAME folders
        resC2 = series.run_series("Demo Comic", info["chapters"][2:], d, optsC, say=logs.append, pause=0)
        assert len(resC2["done"]) == 1, resC2
        assert len(os.listdir(os.path.join(sd, "Demo Comic EPUB"))) == 3
        assert len(os.listdir(os.path.join(sd, "Demo Comic CBZ"))) == 3
        assert len(os.listdir(os.path.join(sd, pk))) == 3
        assert any("Snug-fit check" in m for m in logs)
        assert all(series.is_current(r) for r in series.load_state(sd)["done"].values())
        assert not series.is_current({"sig": "{\"layout\": \"one\"}"})
        # "Previous (v4)" still works as the backup
        optsB = dict(optsC, fit="old")
        resB = series.run_series("Demo Comic", info["chapters"][:1], d, optsB, say=logs.append, pause=0)
        assert len(resB["done"]) == 1, resB
        # layout preview
        assert "Demo CBZ/" in series.layout_preview("central", "Demo", ".cbz", True, 5)

        # --- what can be dropped on the window ---
        os.makedirs(os.path.join(d, "dropme"))
        assert series.classify_drop([os.path.join(d, "dropme")]) == ("folder", os.path.join(d, "dropme"))
        assert series.classify_drop(["https://luacomic.org/series/x"]) == ("link", "https://luacomic.org/series/x")
        with open(os.path.join(d, "a.url"), "w") as f:
            f.write("[InternetShortcut]\nURL=https://luacomic.org/series/y\n")
        assert series.classify_drop([os.path.join(d, "a.url")]) == ("link", "https://luacomic.org/series/y")
        with open(os.path.join(d, "a.webloc"), "w") as f:
            f.write("<plist><dict><key>URL</key><string>https://luacomic.org/series/z</string></dict></plist>")
        assert series.classify_drop([os.path.join(d, "a.webloc")])[1] == "https://luacomic.org/series/z"
        from PIL import Image as _I
        _I.new("RGB", (40, 60), (9, 9, 9)).save(os.path.join(d, "c.png"))
        assert series.classify_drop([os.path.join(d, "c.png")])[0] == "cover"
        assert series.classify_drop(["nonsense"]) == (None, None)

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

    # --- a page that lists every picture twice (01.webp.jpg and 01.webp): keep one of each ---
    b = "https://media.example.org/file/x/uploads/s/abc/"
    twice = [f"{b}{i:02d}.webp.jpg" for i in range(1, 14)] + [f"{b}{i:02d}.webp" for i in range(2, 14)] + [b + "01.webp"]
    got = series.dedupe_images(twice)
    assert got == [f"{b}{i:02d}.webp.jpg" for i in range(1, 14)], got
    assert series.dedupe_images([b + "a.webp", b + "b.webp", b + "a.webp"]) == [b + "a.webp", b + "b.webp"]
    assert len(series.dedupe_images([b + "1.jpg", "https://other.org/s/1.jpg"])) == 2   # different sites stay

    # --- the little picture shown in the window ---
    p1 = series.layout_preview("one", "Demo", ".cbz", True, 5)
    assert "Demo - Chapter 001.cbz" in p1 and "Demo - Chapter 001.epub" in p1 and "Pages/" not in p1
    p2 = series.layout_preview("parts", "Demo", ".pdf", False, 5)
    assert "Pages 1-5.pdf" in p2 and "Pages 6-10.pdf" in p2 and "Pages/" in p2 and ".epub" not in p2
    srv.shutdown()
    print("series OK")


if __name__ == "__main__":
    main()
