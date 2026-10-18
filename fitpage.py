"""Snug-fit page engine (TEST) for Comic Series Downloader.

Made to look like books from Kindle Comic Converter: every screen shows WHOLE scenes,
scaled down to fit and centred on one steady background colour. Nothing is zoomed in and
no scene is cut in half (only a single scene taller than about two screens is split, at its
quietest row, or it would be too small to read).

Webtoon strip -> scenes (split at the empty gaps between panels) -> as many whole scenes as
fit on one screen (shrunk to at most ~70%) -> one page.
Normal manga/comic pages are fitted whole, one per screen, exactly as before.

core.py is not changed: "Previous" in the window still uses the proven v11 engine."""
import math
import os
import tempfile
import threading

from PIL import Image

import core
import covers

GAP = 24           # empty rows in a row that separate two scenes
MAX_GROUP = 1.45   # several scenes may share a screen if they fit shrunk to ~69%
MIN_SCALE = 0.45   # one scene alone may be shrunk to 45%; a taller one is split
MAX_UP = 1.5       # a scene with a narrow art column may be enlarged this much (never more)
MARGIN = 0.025     # thin frame of background round the art, like a printed page
SPACE = 0.015      # background between two scenes on the same screen


LAST_AUDIT = (0, 0)   # (screens made, screens whose art touches the top/bottom edge)


def _quiet_runs(std, min_len):
    runs, y, n = [], 0, len(std)
    while y < n:
        if std[y] >= core.QUIET:
            y += 1
            continue
        e = y
        while e < n and std[e] < core.QUIET:
            e += 1
        if e - y >= min_len:
            runs.append((y, e))
        y = e
    return runs


def _trim(im):
    """Cut empty rows off the top and bottom of a scene. None if nothing is left."""
    std = core._rows(im)
    rows = [i for i, s in enumerate(std) if s >= core.QUIET]
    if not rows or rows[-1] - rows[0] < 6:
        return None
    return im.crop((0, rows[0], im.width, rows[-1] + 1))


class FitPager:
    """Same use as core._Pager: add(path) for each picture in order, then flush()."""

    def __init__(self, tmp_dir, width, height, gray, start_no=0):
        self.tmp, self.w, self.h, self.gray = tmp_dir, width, height, gray
        m = max(4, round(width * MARGIN))
        self.m = m
        self.cw, self.ch = width - 2 * m, height - 2 * m   # room for the art inside the frame
        self.buf = None
        self.scenes = []        # whole scenes waiting to be put on a screen
        self.bg_samples = []    # colours of the gaps between panels = the strip's own background
        self.pages = []
        self.n = start_no
        self.hold = None        # a normal-sized picture waiting to see if the next one continues it

    # ----- saving -----
    def _save(self, im):
        path = os.path.join(self.tmp, f"p{self.n:05d}.jpg")
        self.n += 1
        im.save(path, "JPEG", quality=90, optimize=True)
        self.pages.append(path)

    def _bg(self):
        if self.bg_samples:
            import numpy as np
            v = np.median(np.array(self.bg_samples[-60:], dtype=np.float32), axis=0)
            v = [int(round(x)) for x in np.atleast_1d(v)]
        else:
            v = [255]
        if self.gray:
            return v[0]
        return tuple((v * 3)[:3]) if len(v) == 1 else tuple(v[:3])

    def _sample_bg(self, region):
        import numpy as np
        a = np.asarray(region, dtype=np.float32)
        a = a.reshape(-1, 1) if a.ndim == 2 else a.reshape(-1, a.shape[-1])
        self.bg_samples.append(list(np.median(a, axis=0)))

    # ----- one screen -----
    @staticmethod
    def _art_cols(im):
        """First and last column that holds real art (not just the plain strip background)."""
        import numpy as np
        a = np.asarray(im.convert("L"), dtype=np.float32)
        cols = np.where(a.std(axis=0) >= core.QUIET)[0]
        if len(cols) == 0:
            return 0, im.width
        return int(cols[0]), int(cols[-1]) + 1

    def _compose(self, group):
        bg = self._bg()
        sp = max(6, round(self.ch * SPACE))
        # Webtoon strips often have wide empty side margins. Measure only the real art, so a
        # scene with a narrow art column is shown as big as the screen allows (like KCC),
        # instead of tiny in the middle of a wide empty strip.
        x0 = min(self._art_cols(s)[0] for s in group)
        x1 = max(self._art_cols(s)[1] for s in group)
        if x1 - x0 < 16:
            x0, x1 = 0, group[0].width
        group = [s.crop((x0, 0, x1, s.height)) for s in group]
        gw = x1 - x0
        gh = sum(s.height for s in group) + sp * (len(group) - 1)
        mode = group[0].mode
        img = Image.new(mode, (gw, gh), bg)
        y = 0
        for s in group:
            img.paste(s, (0, y))
            y += s.height + sp
        # as large as fits inside the frame, whole (never cut); up to MAX_UP times bigger than
        # its natural size, and always smaller if it does not fit
        scale = min(MAX_UP, self.cw / gw, self.ch / gh)
        if abs(scale - 1.0) > 0.005:
            img = img.resize((max(1, round(gw * scale)), max(1, round(gh * scale))), Image.LANCZOS)
        page = Image.new(mode, (self.w, self.h), bg)
        page.paste(img, ((self.w - img.width) // 2, (self.h - img.height) // 2))
        self._save(page)

    def _pack(self, final):
        limit = self.ch * MAX_GROUP
        sp = max(6, round(self.ch * SPACE))
        while self.scenes:
            total = sum(s.height for s in self.scenes) + sp * (len(self.scenes) - 1)
            if not final and total <= limit:
                return  # wait: the next scene may still fit on this screen
            group, gh = [], 0
            for s in self.scenes:
                add = s.height + (sp if group else 0)
                if group and gh + add > limit:
                    break
                group.append(s)
                gh += add
            self.scenes = self.scenes[len(group):]
            self._compose(group)

    def _scene(self, im):
        im = _trim(im)
        if im is None:
            return
        too_tall = int(self.ch / MIN_SCALE)
        if im.height > too_tall:
            # one scene over ~2 screens with no gap: even pieces, cut at the quietest rows
            n = math.ceil(im.height / too_tall)
            std = core._rows(im)
            top = 0
            for k in range(1, n):
                target = round(im.height * k / n)
                lo, hi = max(top + 1, int(target - im.height / n * 0.15)), min(
                    im.height - 1, int(target + im.height / n * 0.15))
                cut = min(range(lo, hi + 1), key=lambda y: (round(float(std[y])), abs(y - target)))
                self.scenes.append(im.crop((0, top, im.width, cut)))
                top = cut
            self.scenes.append(im.crop((0, top, im.width, im.height)))
        else:
            self.scenes.append(im)
        self._pack(False)

    # ----- the strip -----
    def _split(self, final):
        if self.buf is None:
            return
        std = core._rows(self.buf)
        pos = 0
        for a, b in _quiet_runs(std, GAP):
            if b >= len(std) and not final:
                break  # this gap may go on in the next picture
            self._sample_bg(self.buf.crop((0, a, self.buf.width, b)))
            if a > pos:
                self._scene(self.buf.crop((0, pos, self.buf.width, a)))
            pos = b
        if final:
            if pos < self.buf.height:
                self._scene(self.buf.crop((0, pos, self.buf.width, self.buf.height)))
            self.buf = None
            return
        self.buf = self.buf.crop((0, pos, self.buf.width, self.buf.height)) if pos else self.buf
        # A scene with no gap for more than about two screens would be too small to read
        # if shrunk whole: split it at the quietest row near the limit.
        too_tall = int(self.ch / MIN_SCALE)
        while self.buf is not None and self.buf.height > too_tall + self.ch // 2:
            std = core._rows(self.buf.crop((0, 0, self.buf.width, too_tall + 1)))
            lo = int(too_tall * 0.75)
            cut = min(range(lo, too_tall + 1), key=lambda y: std[y])
            self._scene(self.buf.crop((0, 0, self.buf.width, cut)))
            self.buf = self.buf.crop((0, cut, self.buf.width, self.buf.height))

    def _commit_hold(self):
        if self.hold is not None:
            h, self.hold = self.hold, None
            self._save(core._fit_single(h, self.w, self.h))

    def flush(self):
        self._commit_hold()
        self._split(True)
        self._pack(True)

    def _to_strip(self, im):
        if im.width != self.cw:
            nh = max(1, round(im.height * self.cw / im.width))
            im = im.resize((self.cw, nh), Image.LANCZOS)
        self.buf = im if self.buf is None else core._vjoin(self.buf, im)
        self._split(False)

    @staticmethod
    def _busy(im, top):
        std = core._rows(im.crop((0, 0, im.width, 3)) if top else
                         im.crop((0, im.height - 3, im.width, im.height)))
        return bool(std.max() >= core.QUIET)

    def add(self, src):
        with Image.open(src) as opened:   # closed right away so Windows can delete files later
            opened.load()
            im = core._page_to_rgb_or_gray(opened, self.gray)
        tall = im.height / im.width > core.STRIP
        # A picture whose top edge cuts through art, right after one whose bottom edge cut
        # through art, is the next slice of one long strip (the site serves strips in slices):
        # join them so whole scenes can be kept together instead of cut at the slice edges.
        cont = False
        if self._busy(im, True):
            if self.hold is not None and self._busy(self.hold, False):
                cont = True
            elif self.buf is not None and self.buf.width == self.cw and self._busy(self.buf, False):
                cont = True
        if cont:
            if self.hold is not None:
                h, self.hold = self.hold, None
                self._to_strip(h)
            self._to_strip(im)
            return
        if tall:
            self._commit_hold()
            self._to_strip(im)
            return
        self.flush()
        self.hold = im   # a normal page, unless the next picture turns out to continue it

def _audit(paths, width, height):
    """Check every finished screen: right size, and no art running off the top or bottom edge
    (that would mean a scene was cut). The counts are read by the program for its log."""
    global LAST_AUDIT
    bad = 0
    for p in paths:
        with Image.open(p) as im:
            im.load()
            if im.size != (width, height):
                bad += 1
                continue
            g = im.convert("L")
            if (core._rows(g.crop((0, 0, width, 3))).max() >= core.QUIET
                    or core._rows(g.crop((0, height - 3, width, height))).max() >= core.QUIET):
                bad += 1
    LAST_AUDIT = (LAST_AUDIT[0] + len(paths), LAST_AUDIT[1] + bad)


def build_files_fit(out_root, title, total, size, device_key, progress=None, stop=None,
                    custom=None, cover=None, epub=False):
    """Same as core.build_device_files, but with the snug-fit pages."""
    if not core.HAS_PIL:
        raise RuntimeError("The picture tools are missing from this copy of the program.")
    global LAST_AUDIT
    LAST_AUDIT = (0, 0)
    stop = stop or threading.Event()
    dev = core.resolve_device(device_key, custom)
    width, height = dev["size"]
    out_dir = os.path.join(out_root, dev["folder"])
    os.makedirs(out_dir, exist_ok=True)
    exts = [dev["ext"]] + ([".epub"] if epub and dev["ext"] != ".epub" else [])
    groups = math.ceil(total / size)
    made, problems = [], []
    for g in range(groups):
        if stop.is_set():
            raise core.Stopped()
        name = core.group_folder_name(title, g * size + 1, total, size)
        folder = os.path.join(out_root, name)
        if not os.path.isdir(folder):
            continue
        files = sorted(f for f in os.listdir(folder)
                       if f.lower().endswith(core.IMG_EXT) and f.lower() != covers.COVER_NAME)
        if progress:
            progress(g, groups, f"Making files for your e-reader: {g + 1} of {groups}")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            pager = FitPager(tmp, width, height, dev["gray"])
            if cover:
                pager.pages.append(covers.fit_cover(cover, width, height, dev["gray"],
                                                    os.path.join(tmp, "cover_page.jpg")))
            for f in files:
                if stop.is_set():
                    raise core.Stopped()
                try:
                    pager.add(os.path.join(folder, f))
                except Exception:
                    problems.append(f"{name}/{f}")
            pager.flush()
            _audit(pager.pages[1:] if cover else pager.pages, width, height)
            if not pager.pages:
                continue
            for ext in exts:
                dest = os.path.join(out_dir, name + ext)
                core._write_device_file(pager.pages, dest, ext, name)
                made.append(dest)
    if progress:
        progress(groups, groups, "E-reader files are ready.")
    return made, problems
