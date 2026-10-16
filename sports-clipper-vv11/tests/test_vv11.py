import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

from sportsclipper import preview, roster, thumbnail  # noqa: E402


def fake_player(path, col=(235, 235, 235, 255)):
    im = Image.new("RGBA", (600, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((200, 10, 400, 170), fill=col)
    d.rounded_rectangle((120, 190, 480, 560), 50, fill=col)
    d.rectangle((180, 540, 420, 890), fill=col)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


def add(root, acr, player, col=(235, 235, 235, 255)):
    fake_player(os.path.join(root, roster.folder_name(acr, player), "cutout.png"), col)


class Rosters(unittest.TestCase):
    def test_two_players_at_most_default_first(self):
        self.assertEqual(len(roster.TEAMS), 30)
        self.assertEqual(set(roster.PLAYERS), set(roster.TEAMS))
        for acr, pl in roster.PLAYERS.items():
            self.assertTrue(1 <= len(pl) <= 2, acr)
        self.assertEqual(roster.PLAYERS["DAL"][0], ("Kyrie Irving", "UNCLE DREW"))      # Kyrie is the default ...
        self.assertEqual(roster.PLAYERS["DAL"][1], ("Cooper Flagg", "FLAGG"))           # ... Flagg is in the drop-down
        self.assertEqual(roster.STARS["DAL"][0], "Kyrie Irving")
        folders = [roster.folder_name(a, n) for a, pl in roster.PLAYERS.items() for n, _ in pl]
        self.assertEqual(len(folders), len(set(folders)))

    def test_options_and_choice(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(roster.options("DAL", root), [])
            self.assertIsNone(roster.find_star("DAL", root))
            add(root, "DAL", "Cooper Flagg")
            self.assertEqual(roster.find_star("DAL", root)[1], "FLAGG")               # only one picture: it is used
            add(root, "DAL", "Kyrie Irving")
            opts = roster.options("DAL", root)
            self.assertEqual([o["name"] for o in opts], ["Kyrie Irving", "Cooper Flagg"])
            self.assertEqual(roster.find_star("DAL", root)[1], "UNCLE DREW")           # default
            self.assertEqual(roster.find_star("DAL", root, choice="Cooper Flagg")[1], "FLAGG")
            self.assertEqual(roster.find_star("DAL", root, choice="Nobody")[1], "UNCLE DREW")
            add(root, "DAL", "Dereck Lively")                                           # a folder you add yourself
            self.assertEqual([o["alias"] for o in roster.options("DAL", root)], ["UNCLE DREW", "FLAGG", "LIVELY"])

    def test_own_folder_beats_bundled(self):
        with tempfile.TemporaryDirectory() as mine, tempfile.TemporaryDirectory() as bundled:
            add(bundled, "DEN", "Nikola Jokic")
            add(bundled, "DEN", "Jamal Murray")
            add(mine, "DEN", "Nikola Jokic", (255, 0, 0, 255))
            with mock.patch.dict(os.environ, {"SPORTSCLIPPER_PLAYERS": mine}), \
                    mock.patch.object(roster, "bundled_dir", lambda: bundled):
                opts = roster.options("DEN")
                self.assertEqual([o["name"] for o in opts], ["Nikola Jokic", "Jamal Murray"])
                self.assertTrue(opts[0]["cutout"].startswith(mine))
                self.assertTrue(opts[1]["cutout"].startswith(bundled))

    def test_bundled_pictures_all_there_when_built(self):
        b = roster.bundled_dir()
        if not os.path.isdir(b):
            self.skipTest("no bundled pictures in a source checkout without the players folder")
        have = sum(1 for a in roster.TEAMS if roster.options(a, b))
        self.assertGreaterEqual(have, 28, "most teams need at least one bundled picture")


class Preview(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        r = self.d.name
        add(r, "DEN", "Nikola Jokic", (230, 230, 230, 255)); add(r, "DEN", "Jamal Murray", (230, 120, 40, 255))
        add(r, "LAC", "Darius Garland", (200, 200, 230, 255))
        self.p = mock.patch.dict(os.environ, {"SPORTSCLIPPER_PLAYERS": r})
        self.p.start()
        self.b = mock.patch.object(roster, "bundled_dir", lambda: os.path.join(r, "none"))
        self.b.start()

    def tearDown(self):
        self.b.stop(); self.p.stop(); self.d.cleanup()

    def test_teams_read_from_title_and_slots(self):
        st = preview.analyse("DEN vs LAC | Full Game")
        self.assertEqual(st["teams"], ["DEN", "LAC"])
        self.assertEqual([s["team"] for s in st["slots"]], ["DEN", "LAC"])
        self.assertEqual(len(st["slots"][0]["labels"]), 2)                    # drop-down has two players
        self.assertEqual(st["slots"][0]["selected"], 0)
        self.assertEqual(len(st["slots"][1]["labels"]), 1)
        self.assertIn("Nikola Jokic", st["slots"][0]["labels"][0])
        st = preview.analyse("Denver Nuggets vs LA Clippers", {"DEN": "Jamal Murray"})
        self.assertEqual(st["slots"][0]["selected"], 1)                       # the remembered choice is pre-selected

    def test_messages(self):
        self.assertIn("two NBA teams", preview.message(preview.analyse("training video")))
        self.assertEqual(preview.message(preview.analyse("DEN vs LAC")), "DEN vs LAC")
        self.assertIn("no player picture yet for BOS", preview.message(preview.analyse("DEN vs BOS")))

    def test_preview_image_changes_with_choice(self):
        a = preview.render_png("DEN vs LAC")
        b = preview.render_png("DEN vs LAC", {"DEN": "Jamal Murray"})
        self.assertTrue(a.startswith(b"\x89PNG"))
        self.assertNotEqual(a, b)
        self.assertEqual(Image.open(__import__("io").BytesIO(a)).size[0], 720)
        self.assertIsNone(preview.render_png("DEN vs BOS"))                   # BOS has no picture
        self.assertIsNone(preview.render_png("no teams here"))

    def test_final_thumbnail_uses_the_choice(self):
        out1 = os.path.join(self.d.name, "a.jpg"); out2 = os.path.join(self.d.name, "b.jpg")
        logs = []
        thumbnail.make_thumbnail("missing.mp4", "DEN vs LAC", 600, out1, logs.append)
        thumbnail.make_thumbnail("missing.mp4", "DEN vs LAC", 600, out2, logs.append, picks={"DEN": "Jamal Murray"})
        self.assertTrue(any("THE JOKER" in m for m in logs))
        self.assertTrue(any("MURRAY" in m for m in logs))
        self.assertNotEqual(open(out1, "rb").read(), open(out2, "rb").read())

    def test_no_duration_badge_without_video(self):
        a = thumbnail.preview_rgb("DEN vs LAC", duration_s=0)
        b = thumbnail.preview_rgb("DEN vs LAC", duration_s=600)
        self.assertEqual(a.shape, (1080, 1920, 3))
        self.assertFalse((a == b).all())


try:
    import tkinter as tk
except ImportError:                      # the build server has no Tk; the Mac build step runs this test
    tk = None


@unittest.skipIf(tk is None, "no Tk here")
class Window(unittest.TestCase):
    def test_dropdowns_and_preview(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        from sportsclipper import config, gui
        with tempfile.TemporaryDirectory() as r:
            add(r, "DEN", "Nikola Jokic"); add(r, "DEN", "Jamal Murray"); add(r, "LAC", "Darius Garland")
            with mock.patch.dict(os.environ, {"SPORTSCLIPPER_PLAYERS": r}), \
                    mock.patch.object(config, "save", lambda *a, **k: None):
                app = gui.App(root)
                app.pv_title.set("DEN vs LAC")
                app.pv_update()
                self.assertEqual(str(app.pv_combos[0].cget("state")), "readonly")      # two players: you can choose
                self.assertEqual(str(app.pv_combos[1].cget("state")), "disabled")      # one player: nothing to choose
                app.pv_combos[0].current(1)
                app.pv_pick(0)
                self.assertEqual(app.cfg["player_choice"]["DEN"], "Jamal Murray")
                for _ in range(60):
                    root.update(); __import__("time").sleep(0.05)
                    if app._pv_photo is not None:
                        break
                self.assertIsNotNone(app._pv_photo)
        root.destroy()


if __name__ == "__main__":
    unittest.main()
