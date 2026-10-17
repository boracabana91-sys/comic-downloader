"""vv22: the channel's rules - which videos are taken, the file name, the title, the checks."""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import config, metadata, pipeline, post, roster, rules, sources  # noqa: E402


def cfg():
    c = config.load(os.path.join(tempfile.mkdtemp(), "none.json"))
    c["ai"]["enabled"] = False
    return c


class Taking(unittest.TestCase):
    def test_game_titles_are_taken(self):
        for t in ("Oklahoma City Thunder vs Houston Rockets - FULL GAME HIGHLIGHTS | October 15, 2026",
                  "THUNDER at ROCKETS Full Game Highlights", "DEN vs LAC FULL GAME HIGHLIGHTS"):
            self.assertEqual(rules.skip_reason(t), "", t)

    def test_shorts_clips_and_other_posts_are_not(self):
        self.assertIn("Short", rules.skip_reason("Thunder vs Rockets highlights", group="Shorts"))
        self.assertIn("Short", rules.skip_reason("Thunder vs Rockets highlights", url="https://www.youtube.com/shorts/abc"))
        self.assertIn("short", rules.skip_reason("Thunder vs Rockets highlights", duration_s=58))
        self.assertTrue(rules.skip_reason("Thunder vs Rockets #shorts"))
        self.assertTrue(rules.skip_reason("Shai's best clip vs Rockets"))
        self.assertTrue(rules.skip_reason("NBA Free Agency news today"))
        self.assertTrue(rules.skip_reason("Thunder highlights"))               # one team only

    def test_a_scan_never_downloads_a_short(self):
        tmp = tempfile.mkdtemp()
        c = cfg(); c["sources"] = [{"name": "A", "kind": "youtube", "location": "UCa", "licensed": True, "license_note": "mine", "enabled": True}]
        c["scan_only"] = ["A"]
        with mock.patch.object(config, "HOME", tmp):
            pl = pipeline.Pipeline(c, lambda m: None)
        pl.db.set("A", "base", "x", "baseline")
        vids = [sources.Video("s1", "Thunder vs Rockets highlights #shorts", datetime(2026, 10, 16), group="Shorts"),
                sources.Video("g1", "Thunder vs Rockets FULL GAME HIGHLIGHTS", datetime(2026, 10, 15))]
        done = []
        with mock.patch.object(sources, "list_recent", return_value=vids), \
             mock.patch.object(pl, "process", side_effect=lambda s, v, u=True, enforce=False: done.append(v.id) or {}):
            pl.scan_once()
        self.assertEqual(done, ["g1"])
        self.assertTrue(pl.db.seen("A", "s1"))                                 # remembered as skipped, never retried


class Naming(unittest.TestCase):
    def test_file_stem_is_alias_vs_alias_date(self):
        c = cfg()
        stem = rules.file_stem(c, ["DEN", "LAC"], datetime(2026, 10, 15))
        a, b = rules.alias_of(c, "DEN"), rules.alias_of(c, "LAC")
        self.assertEqual(stem, f"{a} vs {b} 101526")
        self.assertTrue(rules.FILE_RE.match(stem + "_1080p.mp4"))
        self.assertTrue(rules.FILE_RE.match(stem + "_720p_upscaled.mp4"))

    def test_player_choice_changes_the_alias(self):
        c = cfg()
        names = [o["name"] for o in roster.options("DEN")]
        c["player_choice"] = {"DEN": names[1]}
        self.assertEqual(rules.alias_of(c, "DEN"), rules.alias_of({"player_choice": {}}, "DEN") if len(names) < 2 else
                         [o["alias"] for o in roster.options("DEN")][1].upper().replace("*", ""))

    def test_title_pattern_and_playoffs(self):
        t = rules.make_title(["Oklahoma City Thunder", "Houston Rockets"], "FULL GAME", "October 15, 2026")
        self.assertEqual(t, "Oklahoma City Thunder vs Houston Rockets - FULL GAME HIGHLIGHTS | October 15, 2026")
        self.assertTrue(rules.TITLE_RE.match(t))
        tp = rules.make_title(["Oklahoma City Thunder", "Houston Rockets"], "FLASHY", "May 3, 2026", True)
        self.assertEqual(tp, "Oklahoma City Thunder vs Houston Rockets - FLASHY PLAYOFF HIGHLIGHTS | May 3, 2026")
        self.assertTrue(rules.TITLE_RE.match(tp))
        self.assertTrue(rules.is_playoffs("Nuggets vs Lakers Game 3 PLAYOFFS Highlights"))
        self.assertFalse(rules.is_playoffs("Nuggets vs Lakers Full Game Highlights"))


class Checks(unittest.TestCase):
    def setUp(self):
        self.c = cfg()
        self.title = "Oklahoma City Thunder vs Houston Rockets FULL GAME HIGHLIGHTS October 15, 2026"
        self.pp = post.plan_post(self.c, self.title, None, 540)
        d = tempfile.mkdtemp()
        self.f = os.path.join(d, self.pp["stem"] + "_1080p.mp4")
        with open(self.f, "wb") as fh:
            fh.write(b"x")

    def test_plain_template_passes_every_rule(self):
        checks = rules.check(self.pp["meta"], self.f, self.pp["teams"], self.title, self.c)
        self.assertEqual(rules.failed(checks), [])

    def test_a_wrong_file_name_title_or_description_is_caught(self):
        bad = dict(self.pp["meta"], title="Thunder highlights lol")
        self.assertTrue(rules.failed(rules.check(bad, self.f, self.pp["teams"], self.title, self.c)))
        nodisc = dict(self.pp["meta"], description="hello #nba")
        self.assertTrue(any("fair-use" in x for x in rules.failed(rules.check(nodisc, self.f, self.pp["teams"], self.title, self.c))))
        other = os.path.join(os.path.dirname(self.f), "my video.mp4")
        open(other, "wb").close()
        self.assertTrue(any("File name" in x for x in rules.failed(rules.check(self.pp["meta"], other, self.pp["teams"], self.title, self.c))))

    def test_playoffs_in_the_source_must_be_in_the_title(self):
        src = self.title.replace("FULL GAME HIGHLIGHTS", "PLAYOFFS Game 2 HIGHLIGHTS")
        checks = rules.check(self.pp["meta"], self.f, self.pp["teams"], src, self.c)
        self.assertTrue(any("PLAYOFF" in x for x in rules.failed(checks)))

    def test_description_begins_with_the_fair_use_text(self):
        self.assertTrue(self.pp["meta"]["description"].startswith("This video was edited to follow youtube's fair use guidelines"))


if __name__ == "__main__":
    unittest.main()
