import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import cv2  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from sportsclipper import roster, thumbnail  # noqa: E402


def fake_player(path, col=(235, 235, 235, 255)):
    im = Image.new("RGBA", (600, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((200, 10, 400, 170), fill=col)
    d.rounded_rectangle((120, 190, 480, 560), 50, fill=col)
    d.rectangle((180, 540, 420, 890), fill=col)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


class Roster(unittest.TestCase):
    def test_every_team_has_one_star_a_folder_and_a_colour(self):
        self.assertEqual(len(roster.TEAMS), 30)
        self.assertEqual(set(roster.TEAMS), set(roster.STARS))
        names = [roster.folder_name(a) for a in roster.TEAMS]
        self.assertEqual(len(set(names)), 30)
        self.assertEqual(roster.folder_name("DEN"), "Denver Nuggets - DEN - Nikola Jokic")
        self.assertEqual(roster.folder_name("LAL"), "Los Angeles Lakers - LAL - Luka Doncic")   # accents removed
        for a in roster.TEAMS:
            self.assertEqual(len(roster.team_color(a)), 3)

    def test_acronyms_in_nba_table_exist(self):
        for abbr in thumbnail.NBA.values():
            self.assertIn(abbr, roster.TEAMS)

    def test_find_star_listed_player_first_then_any_folder(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(roster.find_star("DEN", root))
            fake_player(os.path.join(root, "Denver Nuggets - DEN - Aaron Gordon", "cutout.png"))
            png, name = roster.find_star("DEN", root)
            self.assertEqual(name, "GORDON")                          # not the listed star: surname
            fake_player(os.path.join(root, roster.folder_name("DEN"), "cutout.png"))
            self.assertEqual(roster.find_star("DEN", root)[1], "THE JOKER")
            with open(os.path.join(root, roster.folder_name("DEN"), "alias.txt"), "w") as f:
                f.write("Joker")
            self.assertEqual(roster.find_star("DEN", root)[1], "JOKER")


class Titles(unittest.TestCase):
    def test_short_names_and_acronyms(self):
        p = thumbnail.parse_teams
        self.assertEqual(p("Nuggets vs Clippers Full Game"), ["DEN", "LAC"])
        self.assertEqual(p("LAL vs BOS | Oct 20"), ["LAL", "BOS"])
        self.assertEqual(p("Trail Blazers at 76ers"), ["POR", "PHI"])
        self.assertEqual(p("Boston Celtics vs Los Angeles Lakers"), ["BOS", "LAL"])
        self.assertEqual(p("Hornets vs Nets"), ["CHA", "BKN"])        # 'Nets' must not match inside 'Hornets'
        self.assertEqual(p("random video"), [])


class VersusThumbnail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "players")
        os.environ["SPORTSCLIPPER_PLAYERS"] = self.root

    def tearDown(self):
        os.environ.pop("SPORTSCLIPPER_PLAYERS", None)

    def test_two_stars_make_a_1080p_thumbnail_without_the_video(self):
        for a in ("DEN", "LAC"):
            fake_player(os.path.join(self.root, roster.folder_name(a), "cutout.png"))
        out = os.path.join(self.tmp, "t.jpg")
        logs = []
        thumbnail.make_thumbnail("/no/such/video.mp4", "Denver Nuggets vs LA Clippers - October 14, 2026", 580, out,
                                 log=logs.append, score="DEN 112 - 108 LAC")
        self.assertEqual(cv2.imread(out).shape[:2], (1080, 1920))
        self.assertLess(os.path.getsize(out), 2 * 1024 * 1024)
        self.assertTrue(any("THE JOKER" in m for m in logs))

    def test_missing_player_falls_back_to_photo_style(self):
        fake_player(os.path.join(self.root, roster.folder_name("DEN"), "cutout.png"))      # LAC missing
        logs = []
        self.assertIsNone(thumbnail._stars_for(["DEN", "LAC"], logs.append))
        self.assertTrue(any("LAC" in m for m in logs))

    def test_score_is_not_overwritten_when_a_face_is_found(self):
        """vv10 fix: the final score used to be replaced by the action score and crashed the band text."""
        import numpy as np
        frame = np.full((720, 1280, 3), 90, np.uint8)
        orig = thumbnail.closeups
        thumbnail.closeups = lambda path: ([(0.7, frame, (500, 200, 200, 200))], [])
        try:
            out = os.path.join(self.tmp, "p.jpg")
            thumbnail.make_thumbnail("x", "Denver Nuggets vs LA Clippers - October 14, 2026", 100, out,
                                     log=lambda *_: None, score="DEN 1 - 2 LAC")
            self.assertTrue(os.path.exists(out))
        finally:
            thumbnail.closeups = orig


class FetchTool(unittest.TestCase):
    def test_picture_scoring_and_licence(self):
        import get_players as g
        self.assertGreater(g.score("File:Nikola Jokic free throw 2024.jpg", 3000, 4000, "Nikola Jokic"),
                           g.score("File:Nikola Jokic 2024.jpg", 3000, 4000, "Nikola Jokic"))
        self.assertEqual(g.score("File:Someone Else shooting.jpg", 3000, 4000, "Nikola Jokic"), -1)
        self.assertEqual(g.score("File:Nikola Jokic small.jpg", 400, 600, "Nikola Jokic"), -1)
        self.assertEqual(g.surname("Michael Porter Jr."), "porter")
        self.assertEqual(g.surname("Luka Doncic"), "doncic")
        self.assertTrue(g.licence_ok({"LicenseShortName": {"value": "CC BY-SA 4.0"}}))
        self.assertTrue(g.licence_ok({"LicenseShortName": {"value": "Public domain"}}))
        self.assertFalse(g.licence_ok({"LicenseShortName": {"value": "CC BY-NC 2.0"}}))
        self.assertFalse(g.licence_ok({"LicenseShortName": {"value": "Fair use"}}))


if __name__ == "__main__":
    unittest.main()
