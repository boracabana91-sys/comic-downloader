"""vv14: start at the jump ball; up to 3 photos per player; roster re-check."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from sportsclipper import analyze, config, preview, roster, thumbnail  # noqa: E402
from sportsclipper.selfcheck import make_video  # noqa: E402


def add(root, acr, player, files=("cutout.png",), col=(235, 235, 235, 255)):
    for k, f in enumerate(files):
        c = tuple(max(0, v - 40 * k) for v in col[:3]) + (255,)
        im = Image.new("RGBA", (600, 900), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((200, 10, 400, 170), fill=c)
        d.rounded_rectangle((120, 190, 480, 560), 50, fill=c)
        d.rectangle((180, 540, 420, 890), fill=c)
        path = os.path.join(root, roster.folder_name(acr, player), f)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        im.save(path)


class JumpBall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.vid = os.path.join(cls.tmp, "g.mp4")
        # a long opening: 0-200 s nothing, tip-off at 200 s, the clock runs 200-260 and 290-350 s; then a quiet end
        make_video(cls.vid, secs=420, live="between(t,200,260)+between(t,290,350)")

    def cfg(self, lo, hi, **kw):
        c = config.load("/nonexistent")
        c.update(min_minutes=lo, max_minutes=hi, pad_s=0.5, min_clip_s=3, allow_upscale=False, **kw)
        return c

    def test_default_off(self):
        self.assertFalse(config.load("/nonexistent")["start_at_tipoff"])

    def test_tipoff_helper(self):
        live = np.zeros(300, bool); live[40:50] = True; live[100:200] = True
        self.assertEqual(analyze.tipoff(live), 100)               # a 10 s blip is not the jump ball
        self.assertIsNone(analyze.tipoff(np.zeros(50, bool)))

    def test_clip_starts_at_the_jump_ball(self):
        logs = []
        p = analyze.plan(self.vid, self.cfg(1.0, 10.0, start_at_tipoff=True), log=logs.append)
        self.assertGreaterEqual(p["segments"][0][0], 195)
        self.assertLessEqual(p["segments"][0][0], 205)
        self.assertTrue(any("jump ball found" in m for m in logs))
        self.assertAlmostEqual(p["start_s"], 197, delta=3)

    def test_top_up_never_adds_the_opening_back(self):
        p = analyze.plan(self.vid, self.cfg(4.0, 10.0, start_at_tipoff=True, include_interview=True), log=lambda *_: None)
        self.assertGreaterEqual(min(a for a, _ in p["segments"]), 194)

    def test_without_the_tick_the_opening_can_come_back_for_the_minimum(self):
        p = analyze.plan(self.vid, self.cfg(5.0, 10.0, include_interview=True), log=lambda *_: None)
        self.assertLess(min(a for a, _ in p["segments"]), 190)     # unchanged vv13 behaviour: top-up may use the opening

    def test_unreadable_clock_says_so_and_keeps_the_start(self):
        c = self.cfg(1.0, 5.0, start_at_tipoff=True); c["clock_roi"] = [0.02, 0.02, 0.05, 0.05]
        logs = []
        analyze.plan(self.vid, c, log=logs.append)
        self.assertTrue(any("could not find the jump ball" in m for m in logs))


class Photos(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        r = self.d.name
        add(r, "DEN", "Nikola Jokic", ("cutout.png", "cutout2.png", "cutout3.png"))
        add(r, "DEN", "Jamal Murray", ("cutout.png", "cutout2.png"))
        add(r, "LAC", "Darius Garland")
        self.p = mock.patch.dict(os.environ, {"SPORTSCLIPPER_PLAYERS": r}); self.p.start()
        self.b = mock.patch.object(roster, "bundled_dir", lambda: os.path.join(r, "none")); self.b.start()

    def tearDown(self):
        self.b.stop(); self.p.stop(); self.d.cleanup()

    def test_options_list_all_photos_in_order(self):
        o = roster.options("DEN")[0]
        self.assertEqual([os.path.basename(x) for x in o["cutouts"]], ["cutout.png", "cutout2.png", "cutout3.png"])
        self.assertEqual(o["cutout"], o["cutouts"][0])
        self.assertEqual(len(roster.options("LAC")[0]["cutouts"]), 1)

    def test_numbers_sort_numerically_and_underscore_files_are_skipped(self):
        fol = os.path.join(self.d.name, roster.folder_name("DEN", "Nikola Jokic"))
        Image.new("RGBA", (10, 10)).save(os.path.join(fol, "cutout10.png"))
        Image.new("RGBA", (10, 10)).save(os.path.join(fol, "_try.png"))
        names = [os.path.basename(x) for x in roster.options("DEN")[0]["cutouts"]]
        self.assertEqual(names, ["cutout.png", "cutout2.png", "cutout3.png", "cutout10.png"])

    def test_find_star_photo_choice(self):
        base = os.path.basename
        self.assertEqual(base(roster.find_star("DEN")[0]), "cutout.png")
        self.assertEqual(base(roster.find_star("DEN", photos={"Nikola Jokic": 2})[0]), "cutout3.png")
        self.assertEqual(base(roster.find_star("DEN", photos={"Nikola Jokic": 9})[0]), "cutout3.png")       # clamped
        self.assertEqual(base(roster.find_star("DEN", choice="Jamal Murray", photos={"Nikola Jokic": 2})[0]), "cutout.png")
        self.assertEqual(base(roster.find_star("DEN", choice="Jamal Murray", photos={"Jamal Murray": 1})[0]), "cutout2.png")
        self.assertEqual(base(roster.find_star("LAC", photos={"Darius Garland": 2})[0]), "cutout.png")

    def test_preview_slots_and_image(self):
        st = preview.analyse("DEN vs LAC", {}, {"Nikola Jokic": 1})
        s0, s1 = st["slots"]
        self.assertEqual((s0["photos"], s0["photo"]), (3, 1))
        self.assertEqual((s1["photos"], s1["photo"]), (1, 0))
        self.assertEqual(s0["photo_counts"], [3, 2])
        st = preview.analyse("DEN vs LAC", {"DEN": "Jamal Murray"}, {"Jamal Murray": 1})
        self.assertEqual((st["slots"][0]["photos"], st["slots"][0]["photo"]), (2, 1))
        a = preview.render_png("DEN vs LAC"); b = preview.render_png("DEN vs LAC", photos={"Nikola Jokic": 1})
        self.assertNotEqual(a, b)

    def test_final_thumbnail_uses_the_photo(self):
        o1 = os.path.join(self.d.name, "a.jpg"); o2 = os.path.join(self.d.name, "b.jpg")
        thumbnail.make_thumbnail("x.mp4", "DEN vs LAC", 600, o1, lambda *_: None)
        thumbnail.make_thumbnail("x.mp4", "DEN vs LAC", 600, o2, lambda *_: None, photos={"Nikola Jokic": 2})
        self.assertNotEqual(open(o1, "rb").read(), open(o2, "rb").read())


class Roster(unittest.TestCase):
    def test_two_players_per_team_and_all_teams_covered(self):
        self.assertEqual(len(roster.PLAYERS), 30)
        for a, v in roster.PLAYERS.items():
            self.assertTrue(1 <= len(v) <= 2, a)
            self.assertEqual(len({n for n, _ in v}), len(v), a)
        self.assertEqual(sum(len(v) for v in roster.PLAYERS.values()), 60)

    def test_known_2026_moves(self):
        names = lambda a: [n for n, _ in roster.PLAYERS[a]]
        self.assertEqual(names("MIA")[0], "Giannis Antetokounmpo")
        self.assertIn("Bam Adebayo", names("MIA"))
        self.assertIn("Kevin Durant", names("HOU"))
        self.assertIn("LeBron James", names("PHI"))
        self.assertIn("Kawhi Leonard", names("TOR"))
        self.assertIn("LaMelo Ball", names("MIN"))
        self.assertIn("Tyler Herro", names("MIL"))
        self.assertIn("Jaren Jackson Jr.", names("UTA"))
        self.assertIn("Pascal Siakam", names("IND"))
        self.assertIn("Stephon Castle", names("SAS"))


class Fetcher(unittest.TestCase):
    """tools/get_players.py makes up to 3 different photos per player (offline: pictures and Commons are faked)."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
        import get_players
        cls.gp = get_players

    def hits(self):
        ii = lambda t: {"url": "x", "extmetadata": {"Artist": {"value": "A"}, "LicenseShortName": {"value": "CC BY 4.0"}}, "descriptionurl": "u/" + t}
        titles = ["File:Nikola Jokic a.jpg", "File:Nikola Jokic a (cropped).jpg", "File:Nikola Jokic bad.jpg",
                  "File:Nikola Jokic b.jpg", "File:Nikola Jokic c.jpg", "File:Nikola Jokic d.jpg"]
        return [(10 - i, t, ii(t), "current" if i == 0 else "unknown") for i, t in enumerate(titles)]

    def run_one(self, root, **kw):
        gp = self.gp
        def fake_cut(src, out, check=True, strict_edge=True, trim=False):
            if "bad" in open(src).read():
                raise RuntimeError("2 bodies in the picture")
            Image.new("RGBA", (50, 100), (255, 0, 0, 255)).save(out)
        hits = self.hits()
        def fake_dl(session, ii, dest):
            open(dest, "w").write(ii["descriptionurl"])
        with mock.patch.object(gp, "search", lambda *a, **k: hits), mock.patch.object(gp, "_download", fake_dl), \
                mock.patch.object(gp, "cut_out", fake_cut):
            return gp.do_player("DEN", "Nikola Jokic", root, True, None, **kw)

    def test_three_different_photos(self):
        with tempfile.TemporaryDirectory() as r:
            msg = self.run_one(r, pics=3, tries=20)
            fol = os.path.join(r, roster.folder_name("DEN", "Nikola Jokic"))
            self.assertEqual(sorted(f for f in os.listdir(fol) if f.endswith(".png")), ["cutout.png", "cutout2.png", "cutout3.png"])
            self.assertIn("3 photo(s)", msg)
            self.assertNotIn("(cropped)", msg)                 # the crop of photo a counts as the same photo
            self.assertNotIn("bad", msg)                       # the rejected one is skipped
            cr = open(os.path.join(fol, "credit.txt")).read()
            self.assertIn("[cutout.png]", cr); self.assertIn("[cutout3.png]", cr)
            self.assertEqual(len(roster._cutouts_in(fol)), 3)

    def test_candidates_keep_going_and_redo_cleans_up(self):
        with tempfile.TemporaryDirectory() as r:
            fol = os.path.join(r, roster.folder_name("DEN", "Nikola Jokic")); os.makedirs(fol)
            Image.new("RGBA", (5, 5)).save(os.path.join(fol, "cutout9.png"))                     # an old leftover
            self.run_one(r, pics=2, cands=4, tries=20)
            self.assertEqual(sorted(f for f in os.listdir(fol) if f.endswith(".png")), ["cutout.png", "cutout2.png"])
            idx = open(os.path.join(r, "_cands", roster.folder_name("DEN", "Nikola Jokic"), "index.txt")).read().splitlines()
            self.assertEqual(len(idx), 4)

    def test_forced_list(self):
        gp = self.gp
        ii = {"url": "x", "extmetadata": {}, "descriptionurl": "u"}
        with tempfile.TemporaryDirectory() as r, mock.patch.object(gp, "file_info", lambda t, s: (0, t, ii)), \
                mock.patch.object(gp, "_download", lambda s, i, d: open(d, "w").write("x")), \
                mock.patch.object(gp, "cut_out", lambda src, out, **k: Image.new("RGBA", (5, 5)).save(out)):
            msg = gp.do_player("DEN", "Nikola Jokic", r, False, None, forced=["File:A.jpg", "File:B.jpg", "File:C.jpg"])
            fol = os.path.join(r, roster.folder_name("DEN", "Nikola Jokic"))
            self.assertEqual(sorted(f for f in os.listdir(fol) if f.endswith(".png")), ["cutout.png", "cutout2.png", "cutout3.png"])
            self.assertIn("3 picture(s)", msg)

    def test_same_photo_key(self):
        f = self.gp._same_photo
        self.assertEqual(f("File:Kevin Durant dunk (cropped).jpg"), f("File:Kevin Durant dunk.jpg"))
        self.assertNotEqual(f("File:Kevin Durant (123).jpg"), f("File:Kevin Durant (456).jpg"))


try:
    import tkinter as tk
except ImportError:
    tk = None


@unittest.skipIf(tk is None, "no Tk here")
class Window(unittest.TestCase):
    def test_photo_dropdown_and_jump_ball_tick(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        from sportsclipper import gui
        with tempfile.TemporaryDirectory() as r:
            add(r, "DEN", "Nikola Jokic", ("cutout.png", "cutout2.png", "cutout3.png")); add(r, "DEN", "Jamal Murray", ("cutout.png", "cutout2.png"))
            add(r, "LAC", "Darius Garland")
            saved = {}
            with mock.patch.dict(os.environ, {"SPORTSCLIPPER_PLAYERS": r}), \
                    mock.patch.object(roster, "bundled_dir", lambda: os.path.join(r, "none")), \
                    mock.patch.object(config, "save", lambda c, *a, **k: saved.update(c)):
                app = gui.App(root)
                self.assertFalse(app.tip.get())
                app.pv_title.set("DEN vs LAC"); app.pv_update()
                self.assertEqual(str(app.pv_photo_cbs[0].cget("state")), "readonly")      # 3 photos: you can choose
                self.assertEqual(str(app.pv_photo_cbs[1].cget("state")), "disabled")      # 1 photo: nothing to choose
                self.assertEqual(len(app.pv_photo_cbs[0].cget("values")), 3)
                app.pv_photo_cbs[0].current(2); app.pv_photo_pick(0)
                self.assertEqual(app.cfg["photo_choice"]["Nikola Jokic"], 2)
                app.pv_combos[0].current(1); app.pv_pick(0)                              # switch to Murray: his own 2 photos
                self.assertEqual(len(app.pv_photo_cbs[0].cget("values")), 2)
                app.tip.set(True); app.save()
                self.assertTrue(saved["start_at_tipoff"])
                self.assertEqual(saved["photo_choice"]["Nikola Jokic"], 2)
        root.destroy()


if __name__ == "__main__":
    unittest.main()
