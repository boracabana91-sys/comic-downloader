"""Snug-fit pages: whole scenes, never zoomed in, nothing cut except a scene over ~2 screens."""
import os
import tempfile

import numpy as np
from PIL import Image

import core
import fitpage

COLORS = [(220, 40, 40), (40, 180, 40), (40, 60, 220), (230, 200, 30), (200, 40, 200),
          (30, 200, 200), (240, 130, 20)]


def panel(h, color, w=800):
    """A panel with vertical stripes, so every row has detail (is not 'empty')."""
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


def main():
    W, H = 1072, 1448
    # panels: 3 short ones (share screens), one ~1.3 screens, one ~4 screens (must be split)
    heights = [500, 650, 420, 1500, 5200, 600]
    s = strip(heights)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        # the strip arrives as 3 pictures, cut in the MIDDLE of panels (like real webtoons)
        cuts = [0, 1300, 5200, s.height]
        for i in range(3):
            s.crop((0, cuts[i], 800, cuts[i + 1])).save(os.path.join(d, f"{i:03d}.png"))
        out = os.path.join(d, "out")
        os.makedirs(out)
        p = fitpage.FitPager(out, W, H, False)
        for i in range(3):
            p.add(os.path.join(d, f"{i:03d}.png"))
        p.flush()
        pages = [Image.open(x).convert("RGB") for x in p.pages]
        assert pages and all(pg.size == (W, H) for pg in pages)
        where = {i: [n for n, pg in enumerate(pages) if has(pg, c)] for i, c in enumerate(COLORS[:6])}
        print("pages:", len(pages), "panel -> pages:", where)
        for i in (0, 1, 2, 3, 5):
            assert len(where[i]) == 1, f"panel {i} must be whole on ONE page: {where}"
        assert len(where[4]) >= 2, "the 4-screen panel is split so it stays readable"
        # never zoomed in: art is at most the width inside the frame
        m = max(4, round(W * fitpage.MARGIN))
        for pg in pages:
            a = np.asarray(pg.convert("L"), dtype=np.int16)
            assert (np.abs(a[:, :m - 1] - 255) < 12).all(), "left frame is plain background"
        # the background is the strip's own (white here), not black bars
        assert pages[0].getpixel((3, 3))[0] > 240

        # slices that are NOT tall (aspect < 1.6), cut through panels: must still be joined
        s2 = strip([500, 650, 420, 700, 600, 480], gap=90)
        sl = 1000
        n = 0
        for y in range(0, s2.height, sl):
            s2.crop((0, y, 800, min(s2.height, y + sl))).save(os.path.join(d, f"s{n:03d}.png"))
            n += 1
        o2 = os.path.join(d, "out2")
        os.makedirs(o2)
        r = fitpage.FitPager(o2, W, H, False)
        for i in range(n):
            r.add(os.path.join(d, f"s{i:03d}.png"))
        r.flush()
        pg2 = [Image.open(x).convert("RGB") for x in r.pages]
        w2 = {i: [k for k, pg in enumerate(pg2) if has(pg, c)] for i, c in enumerate(COLORS[:6])}
        print("slices: pages", len(pg2), w2)
        for i in range(6):
            assert len(w2[i]) == 1, f"panel {i} cut across pages: {w2}"
        fitpage.LAST_AUDIT = (0, 0)
        fitpage._audit(r.pages, W, H)
        assert fitpage.LAST_AUDIT == (len(r.pages), 0), fitpage.LAST_AUDIT

        # a scene whose art is a NARROW column in a wide empty strip is shown bigger, not tiny
        nar = Image.new("RGB", (800, 1500), (255, 255, 255))
        nar.paste(panel(600, COLORS[0], 280), (260, 300))
        nar.save(os.path.join(d, "n0.png"))
        o3 = os.path.join(d, "out3")
        os.makedirs(o3)
        r3 = fitpage.FitPager(o3, W, H, False)
        r3.add(os.path.join(d, "n0.png"))
        r3.flush()
        assert len(r3.pages) == 1
        g = np.asarray(Image.open(r3.pages[0]).convert("L"), dtype=np.int16)
        cols = np.where((np.abs(g - 255) > 40).any(axis=0))[0]
        art_w = cols[-1] - cols[0]
        natural = 280 * (W - 2 * max(4, round(W * fitpage.MARGIN))) / 800
        print("narrow art width on page", art_w, "natural", round(natural))
        assert art_w > natural * 1.3, "narrow art must be enlarged, not left small"
        assert art_w <= W - 2 * max(4, round(W * fitpage.MARGIN)) + 2

        # a page-shaped picture with a narrow art column and wide empty margins (the 0226 case):
        # the art must fill the screen height, whole, not sit small in the middle
        pg = Image.new("RGB", (800, 1000), (255, 255, 255))
        pg.paste(panel(560, COLORS[2], 330), (235, 220))
        pg.save(os.path.join(d, "pg.png"))
        o4 = os.path.join(d, "out4")
        os.makedirs(o4)
        r4 = fitpage.FitPager(o4, W, H, False)
        r4.add(os.path.join(d, "pg.png"))
        r4.flush()
        g4 = np.asarray(Image.open(r4.pages[0]).convert("L"), dtype=np.int16)
        rows4 = np.where((np.abs(g4 - 255) > 40).any(axis=1))[0]
        print("page-shaped slice: art height fraction", round((rows4[-1] - rows4[0]) / H, 2))
        assert (rows4[-1] - rows4[0]) / H > 0.85, "art must fill the screen height"

        # normal (book-shaped) page still fitted whole
        Image.new("RGB", (900, 1300), (10, 10, 10)).save(os.path.join(d, "book.png"))
        q = fitpage.FitPager(out, W, H, True)
        q.add(os.path.join(d, "book.png"))
        q.flush()
        assert len(q.pages) == 1 and Image.open(q.pages[0]).size == (W, H)
    print("fitpage OK")


if __name__ == "__main__":
    main()
