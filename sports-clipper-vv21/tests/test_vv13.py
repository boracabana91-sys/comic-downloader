"""vv13: no score on the thumbnail, date under VS, font styles, post-game interview, YouTube thumbnail checks,
1-second thumbnail intro and cover picture."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from sportsclipper import analyze, config, cover, finish, media, preview, render, roster, thumbnail, uploader  # noqa: E402
from sportsclipper.selfcheck import make_video  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def add(root, acr, player, col=(235, 235, 235, 255)):
    im = Image.new("RGBA", (600, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((200, 10, 400, 170), fill=col)
    d.rounded_rectangle((120, 190, 480, 560), 50, fill=col)
    d.rectangle((180, 540, 420, 890), fill=col)
    path = os.path.join(root, roster.folder_name(acr, player), "cutout.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


class Thumbnail(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        r = self.d.name
        add(r, "DEN", "Nikola Jokic"); add(r, "LAC", "Darius Garland")
        self.p = mock.patch.dict(os.environ, {"SPORTSCLIPPER_PLAYERS": r}); self.p.start()
        self.b = mock.patch.object(roster, "bundled_dir", lambda: os.path.join(r, "none")); self.b.start()
        thumbnail.set_layout("stars")                       # these tests describe the full-body layout (vv21 default is closeup)

    def tearDown(self):
        thumbnail.set_layout("closeup")
        self.b.stop(); self.p.stop(); self.d.cleanup()

    def test_no_score_anywhere(self):
        def boom(_):
            raise AssertionError("the score must not be looked up for the two-star thumbnail")
        with mock.patch.object(thumbnail, "score_line", boom):
            thumbnail.preview_rgb("DEN vs LAC - October 14, 2026", duration_s=600)
            out = os.path.join(self.d.name, "t.jpg")
            thumbnail.make_thumbnail("missing.mp4", "DEN vs LAC - October 14, 2026", 600, out, log=lambda *_: None)
            self.assertTrue(os.path.exists(out))

    def test_date_is_in_the_middle_under_vs(self):
        a = thumbnail.preview_rgb("DEN vs LAC", duration_s=600)
        b = thumbnail.preview_rgb("DEN vs LAC - October 14, 2026", duration_s=600)
        H, W = a.shape[:2]
        diff = (a.astype(int) != b.astype(int)).any(2)
        ys, xs = np.nonzero(diff)
        self.assertGreater(len(ys), 500)                                   # the date is drawn
        self.assertGreater(ys.min(), 0.5 * H)                              # below the VS
        self.assertLess(ys.max(), H - thumbnail.BAND_H)                    # and not in the bottom band any more
        self.assertGreater(xs.min(), 0.3 * W); self.assertLess(xs.max(), 0.7 * W)    # in the middle part

    def test_bottom_band_has_only_the_duration(self):
        a = thumbnail.preview_rgb("DEN vs LAC - October 14, 2026", duration_s=0)
        H, W = a.shape[:2]
        band = a[H - thumbnail.BAND_H + 8:, :int(W * 0.8)]
        self.assertLess(int(band.max()), 40)                               # dark, empty on the left and middle

    def test_every_font_style_renders_and_differs(self):
        imgs = {}
        for st in thumbnail.font_styles():
            imgs[st] = thumbnail.preview_rgb("DEN vs LAC - October 14, 2026", duration_s=300, style=st)
            self.assertEqual(imgs[st].shape, (1080, 1920, 3))
        names = list(imgs)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if {names[i], names[j]} == {"Impact"} :
                    continue
                self.assertFalse((imgs[names[i]] == imgs[names[j]]).all(), f"{names[i]} looks like {names[j]}")
        self.assertTrue((thumbnail.preview_rgb("DEN vs LAC", style="no such font") == thumbnail.preview_rgb("DEN vs LAC")).all())

    def test_bundled_font_files_are_there(self):
        for st, f in thumbnail.FONT_STYLES.items():
            if f:
                self.assertTrue(os.path.exists(os.path.join(thumbnail.HERE, "fonts", f)), f)

    def test_preview_png_takes_a_style(self):
        a = preview.render_png("DEN vs LAC", style="Anton"); b = preview.render_png("DEN vs LAC", style="Bangers")
        self.assertNotEqual(a, b)

    def test_make_versus_only(self):
        out = os.path.join(self.d.name, "v.jpg")
        self.assertEqual(thumbnail.make_versus_only("DEN vs LAC", 300, out, lambda *_: None), out)
        self.assertIsNone(thumbnail.make_versus_only("DEN vs BOS", 300, out + "2", lambda *_: None))


class Interview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.vid = os.path.join(cls.tmp, "g.mp4")
        make_video(cls.vid, secs=300)         # play ends at 50 s, the other 250 s have no running clock (the "interview")

    def cfg(self, lo, hi, **kw):
        c = config.load("/nonexistent")
        c.update(min_minutes=lo, max_minutes=hi, pad_s=0.5, min_clip_s=3, allow_upscale=False, **kw)
        return c

    def test_default_is_off(self):
        self.assertFalse(config.load("/nonexistent")["include_interview"])

    def test_game_end_ignores_lonely_flicker(self):
        self.assertEqual(analyze.game_end([[0, 100], [110, 400], [900, 905]]), 400.0)
        self.assertEqual(analyze.game_end([[0, 100], [110, 400], [450, 470]]), 470.0)    # real late play stays
        self.assertEqual(analyze.game_end([[10, 20]]), 20.0)
        self.assertEqual(analyze.game_end([]), 0.0)

    def test_top_up_never_reaches_past_the_end_of_the_game(self):
        p = analyze.plan(self.vid, self.cfg(2.0, 3.0), log=lambda *_: None)      # wants 2 min, game is only ~50 s
        self.assertLessEqual(max(b for _, b in p["segments"]), 50 + 20 + 1)
        self.assertGreater(p["interview_cut_s"], 200)

    def test_tick_brings_it_back(self):
        p = analyze.plan(self.vid, self.cfg(2.0, 3.0, include_interview=True), log=lambda *_: None)
        self.assertGreaterEqual(p["kept_s"], 2.0 * 60 * 0.95)
        self.assertGreater(max(b for _, b in p["segments"]), 100)
        self.assertEqual(p["interview_cut_s"], 0)

    def test_unreadable_clock_and_no_bug_cuts_nothing_at_the_end(self):
        """vv19: no clock and no score bug = we cannot tell where the game ends, so nothing is cut (a fixed guess cut real play)."""
        c = self.cfg(1.5, 2.5); c["clock_roi"] = [0.02, 0.02, 0.05, 0.05]
        logs = []
        p = analyze.plan(self.vid, c, log=logs.append)
        self.assertEqual(p["interview_cut_s"], 0)
        self.assertTrue(any("nothing was cut at the end" in m for m in logs))
        p2 = analyze.plan(self.vid, dict(c, include_interview=True), log=lambda *_: None)
        self.assertEqual(p2["interview_cut_s"], 0)


class YouTubeThumbnail(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.pic = os.path.join(self.d.name, "t.jpg")
        with open(self.pic, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"0" * 1000)

    def tearDown(self):
        self.d.cleanup()

    def err(self, status, text):
        import httplib2
        from googleapiclient.errors import HttpError
        return HttpError(httplib2.Response({"status": status}), text.encode())

    def service(self, results):
        calls = []
        class Req:
            def __init__(s, r): s.r = r
            def execute(s):
                calls.append(1)
                if isinstance(s.r, Exception):
                    raise s.r
                return s.r
        svc = mock.MagicMock()
        it = iter(results)
        svc.thumbnails.return_value.set.side_effect = lambda **kw: Req(next(it))
        return svc, calls

    def test_classify(self):
        retry, msg = uploader.classify_thumbnail_error(403, "The authenticated user doesn't have permissions to upload and set custom video thumbnails.")
        self.assertFalse(retry); self.assertIn("verif", msg.lower())
        self.assertTrue(uploader.classify_thumbnail_error(404, "videoNotFound")[0])
        self.assertTrue(uploader.classify_thumbnail_error(503, "")[0])
        self.assertFalse(uploader.classify_thumbnail_error(403, "quotaExceeded")[0])

    def test_success_is_confirmed(self):
        svc, calls = self.service([{"items": [{"default": {"url": "https://i.ytimg.com/x.jpg"}}]}])
        url = uploader.set_thumbnail({}, "abc", self.pic, service=svc, sleep=lambda s: None)
        self.assertEqual(url, "https://i.ytimg.com/x.jpg"); self.assertEqual(len(calls), 1)

    def test_retries_while_the_video_is_processing(self):
        svc, calls = self.service([self.err(404, "videoNotFound"), self.err(503, "x"), {"items": [{"default": {"url": "u"}}]}])
        logs, sleeps = [], []
        self.assertEqual(uploader.set_thumbnail({}, "abc", self.pic, log=logs.append, service=svc, sleep=sleeps.append), "u")
        self.assertEqual(len(calls), 3); self.assertEqual(len(sleeps), 2)

    def test_unverified_channel_gives_a_clear_message_without_retrying(self):
        svc, calls = self.service([self.err(403, "doesn't have permissions to upload and set custom video thumbnails")])
        with self.assertRaises(uploader.ThumbnailError) as cm:
            uploader.set_thumbnail({}, "abc", self.pic, service=svc, sleep=lambda s: None)
        self.assertIn("verif", str(cm.exception).lower()); self.assertEqual(len(calls), 1)

    def test_gives_up_after_the_retries(self):
        svc, calls = self.service([self.err(404, "videoNotFound")] * 4)
        with self.assertRaises(uploader.ThumbnailError):
            uploader.set_thumbnail({}, "abc", self.pic, service=svc, sleep=lambda s: None)
        self.assertEqual(len(calls), 4)

    def test_empty_answer_is_not_success(self):
        svc, _ = self.service([{}] * 4)
        with self.assertRaises(uploader.ThumbnailError):
            uploader.set_thumbnail({}, "abc", self.pic, service=svc, sleep=lambda s: None)

    def test_too_big_or_missing(self):
        with self.assertRaises(uploader.ThumbnailError):
            uploader.set_thumbnail({}, "abc", os.path.join(self.d.name, "none.jpg"))
        big = os.path.join(self.d.name, "big.jpg")
        with open(big, "wb") as f:
            f.write(b"0" * (2 * 1024 * 1024 + 1))
        with self.assertRaises(uploader.ThumbnailError):
            uploader.set_thumbnail({}, "abc", big)


class Embedding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.vid = os.path.join(cls.tmp, "g.mp4")
        make_video(cls.vid, secs=30)
        add(cls.tmp, "DEN", "Nikola Jokic"); add(cls.tmp, "LAC", "Darius Garland")
        cls.pic = os.path.join(cls.tmp, "thumb.jpg")
        with mock.patch.dict(os.environ, {"SPORTSCLIPPER_PLAYERS": cls.tmp}), \
                mock.patch.object(roster, "bundled_dir", lambda: os.path.join(cls.tmp, "none")):
            thumbnail.make_versus_only("DEN vs LAC", 30, cls.pic, lambda *_: None)

    def cfg(self, **kw):
        c = config.load("/nonexistent")
        c.update(resolutions=[720], allow_upscale=False, encoder="libx264", preset="ultrafast", parallel_renders=1, **kw)
        return c

    def test_intro_adds_one_second_with_the_picture_first(self):
        info = media.probe(self.vid)
        segs = [[0.0, 10.0]]
        plain = render.render(self.vid, segs, info, self.cfg(), os.path.join(self.tmp, "plain", "a"), lambda *_: None)
        withi = render.render(self.vid, segs, info, self.cfg(), os.path.join(self.tmp, "intro", "a"), lambda *_: None, intro=self.pic)
        dp = media.probe(plain[720])["duration"]; di = media.probe(withi[720])["duration"]
        self.assertAlmostEqual(di - dp, render.INTRO_S, delta=0.25)
        self.assertTrue(media.probe(withi[720])["has_audio"])
        # frame 0 is the thumbnail (rich in colour), a later frame is the dark fake broadcast
        f0 = os.path.join(self.tmp, "f0.png"); f2 = os.path.join(self.tmp, "f2.png")
        for t, f in ((0.1, f0), (3.0, f2)):
            subprocess.run([media.need("ffmpeg"), "-v", "error", "-y", "-ss", str(t), "-i", withi[720], "-frames:v", "1", f], check=True)
        from PIL import Image
        a0 = np.asarray(Image.open(f0).convert("RGB")).astype(float); a2 = np.asarray(Image.open(f2).convert("RGB")).astype(float)
        self.assertGreater(a0.std(), 3 * a2.std() + 1)

    def test_intro_without_audio(self):
        s = render._script([[0.0, 5.0]], 720, 720, "30", False, True, 1280)
        try:
            self.assertIn("concat=n=2:v=1:a=0", open(s).read())
        finally:
            os.unlink(s)

    def test_cover_art_keeps_streams_and_adds_picture(self):
        v = os.path.join(self.tmp, "cov.mp4")
        make_video(v, secs=5)
        before = media.probe(v)["duration"]
        self.assertTrue(cover.add_cover_art(v, self.pic))
        err = subprocess.run([media.need("ffmpeg"), "-hide_banner", "-i", v], capture_output=True, text=True).stderr
        self.assertIn("attached pic", err)
        self.assertAlmostEqual(media.probe(v)["duration"], before, delta=0.3)
        self.assertFalse(os.path.exists(v + ".cover.mp4"))
        self.assertFalse(cover.add_cover_art(os.path.join(self.tmp, "none.mp4"), self.pic))

    def test_finish_helpers_respect_the_ticks(self):
        c = config.load("/nonexistent")
        self.assertIsNone(finish.intro_picture(c, "DEN vs LAC", 60, os.path.join(self.tmp, "x"), lambda *_: None))
        outs = {720: os.path.join(self.tmp, "none.mp4")}
        finish.add_cover(c, outs, self.pic)                                  # off: nothing happens, no error
        self.assertEqual(finish.style_of({"thumb_font": "nope"}), thumbnail.DEFAULT_STYLE)
        self.assertEqual(finish.style_of({"thumb_font": "Anton"}), "Anton")


class PictureFetcher(unittest.TestCase):
    """The picture fetcher: whole players only (no arm cut off at the photo's edge), and it knows old-team jerseys."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
        import get_players
        cls.gp = get_players

    def _img(self, boxes, size=(900, 1200)):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for b in boxes:
            d.rectangle(b, fill=(200, 200, 200, 255))
        return im

    def test_edge_cut_players_are_rejected(self):
        ok = self.gp.judge(self._img([(300, 150, 600, 1150)]))
        self.assertTrue(ok[0])
        left = self.gp.judge(self._img([(0, 150, 300, 1150)]))                 # arm runs off the left edge of the photo
        self.assertFalse(left[0]); self.assertIn("side", left[2])
        right = self.gp.judge(self._img([(600, 150, 900, 1150)]))
        self.assertFalse(right[0])
        top = self.gp.judge(self._img([(300, 0, 600, 1100)]))
        self.assertFalse(top[0]); self.assertIn("top", top[2])
        self.assertTrue(self.gp.judge(self._img([(300, 150, 600, 1200)]))[0])   # legs cut by the bottom edge are fine
        self.assertTrue(self.gp.judge(self._img([(0, 150, 300, 1150)]), strict_edge=False)[0])   # last-resort pass

    def test_tidy_removes_specks_and_opponents(self):
        im = self._img([(300, 150, 600, 1150), (320, 20, 340, 40), (700, 600, 830, 1000)])      # player, a floating speck, a smaller opponent
        self.assertFalse(self.gp.judge(im)[0])                                  # two bodies: rejected as is
        t = self.gp.tidy(im, drop_big=True)
        self.assertTrue(self.gp.judge(t)[0])
        import numpy as np
        a = np.asarray(t.getchannel("A"))
        self.assertEqual(int(a[30, 330]), 0); self.assertEqual(int(a[800, 760]), 0); self.assertGreater(int(a[600, 450]), 200)
        t2 = self.gp.tidy(im)                                                   # without drop_big the opponent stays, the speck goes
        self.assertEqual(int(np.asarray(t2.getchannel("A"))[30, 330]), 0); self.assertGreater(int(np.asarray(t2.getchannel("A"))[800, 760]), 200)

    def test_team_status(self):
        f = self.gp.team_status
        self.assertEqual(f("HOU", "File:Kevin Durant Houston Rockets 2025.jpg Category:Houston Rockets players"), "current")
        self.assertEqual(f("HOU", "File:Kevin Durant (51914124577).jpg Oklahoma City Thunder v Wizards"), "other")
        self.assertEqual(f("HOU", "File:Kevin Durant dunk.jpg Category:Kevin Durant"), "unknown")
        self.assertEqual(f("POR", "Portland Trail Blazers at Wizards"), "current")
        self.assertEqual(f("PHI", "Philadelphia 76ers vs Lakers"), "current")
        self.assertLess(self.gp.TEAM_BONUS["other"], 0)
        self.assertGreater(self.gp.TEAM_BONUS["current"], 0)


try:
    import tkinter as tk
except ImportError:
    tk = None


@unittest.skipIf(tk is None, "no Tk here")
class Window(unittest.TestCase):
    def test_font_dropdown_and_ticks(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        from sportsclipper import gui
        with tempfile.TemporaryDirectory() as r:
            add(r, "DEN", "Nikola Jokic"); add(r, "LAC", "Darius Garland")
            saved = {}
            with mock.patch.dict(os.environ, {"SPORTSCLIPPER_PLAYERS": r}), \
                    mock.patch.object(roster, "bundled_dir", lambda: os.path.join(r, "none")), \
                    mock.patch.object(config, "save", lambda c, *a, **k: saved.update(c)):
                app = gui.App(root)
                self.assertFalse(app.iv.get()); self.assertFalse(app.cov.get()); self.assertFalse(app.intro.get())
                self.assertEqual(app.font_var.get(), thumbnail.DEFAULT_STYLE)
                app.pv_title.set("DEN vs LAC"); app.pv_update()
                app.font_cb.current(thumbnail.font_styles().index("Anton"))
                app.font_pick()
                self.assertEqual(app.cfg["thumb_font"], "Anton")
                app.iv.set(True); app.cov.set(True); app.intro.set(True); app.save()
                self.assertTrue(saved["include_interview"] and saved["thumb_cover_art"] and saved["thumb_intro"])
                self.assertEqual(saved["thumb_font"], "Anton")
        root.destroy()


if __name__ == "__main__":
    unittest.main()
