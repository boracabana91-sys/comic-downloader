"""vv38: the clip ends where the game ends (never later), random upload file names, 110% zoom, daily upload limit waits."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import analyze, config, render, rules, uploader  # noqa: E402


class Ending(unittest.TestCase):
    def test_announcers_close_the_game(self):
        cues = [(10.0, "tip off"), (780.0, "they can win the game"), (828.0, "Pistons win the ball game 129 125."), (860.0, "final score again")]
        ce = analyze.final_from_cues(cues, 861.0)
        self.assertTrue(828.0 < ce < 838.0, ce)

    def test_early_talk_is_ignored(self):
        self.assertIsNone(analyze.final_from_cues([(100.0, "that's the ball game")], 1000.0))   # not in the last part of the video
        self.assertIsNone(analyze.final_from_cues([], 1000.0))
        self.assertIsNone(analyze.final_from_cues([(900.0, "a big shot to take the lead")], 1000.0))

    def test_nothing_is_kept_after_the_end(self):
        out = analyze.clamp_to_end([[0.0, 50.0], [60.0, 90.0], [95.0, 99.0]], 80.0, True)
        self.assertEqual(out, [[0.0, 50.0], [60.0, 80.0]])
        self.assertEqual(analyze.clamp_to_end([[0.0, 50.0]], 30.0, False), [[0.0, 50.0]])      # end unknown: untouched

    def test_ensure_ending_also_trims(self):
        final, _ = analyze.ensure_ending([[0.0, 50.0], [60.0, 900.0]], 828.0, True)
        self.assertEqual(final[-1][1], 828.0)

    def test_plan_uses_the_cue_and_clamps(self):
        src = open(os.path.join(os.path.dirname(analyze.__file__), "analyze.py"), encoding="utf-8").read()
        self.assertIn("final_from_cues(cues, secs", src)


class Names(unittest.TestCase):
    def test_random_names(self):
        names = {rules.random_name() for _ in range(50)}
        self.assertEqual(len(names), 50)
        for n in names:
            self.assertTrue(re.fullmatch(r"[a-z][a-z0-9]{16}", n), n)
            self.assertTrue(rules.RANDOM_RE.match(n + "_1080p.mp4"))

    def test_the_channel_rule_accepts_a_random_name(self):
        checks = rules.check({"title": "x", "description": "", "tags": []}, "/tmp/sdi9i1ndknsda9812_1080p.mp4", [], "x", None, pending=True)
        self.assertTrue(any(ok and "random" in rule for ok, rule, _ in checks))
        self.assertFalse(any((not ok) and "File name" in rule for ok, rule, _ in checks))


class Zoom(unittest.TestCase):
    def test_default_is_110(self):
        self.assertEqual(config.DEFAULTS["zoom_pct"], 110)

    def test_filter(self):
        self.assertEqual(render.zoom_filter(1.0), "")
        f = render.zoom_filter(1.1)
        self.assertIn("crop=trunc(iw/1.100/2)*2:trunc(ih/1.100/2)*2", f)

    def test_script_has_the_crop_before_the_scale(self):
        p = render._script([[0.0, 5.0]], 1080, 1080, "30", False, zoom=1.1)
        s = open(p).read(); os.unlink(p)
        self.assertLess(s.index("crop="), s.index("scale=-2:1080"))
        p = render._script([[0.0, 5.0]], 1080, 1080, "30", False)
        s = open(p).read(); os.unlink(p)
        self.assertNotIn("crop=", s)


class Limit(unittest.TestCase):
    def test_detects_the_limit(self):
        e = RuntimeError('<HttpError 400 returned "The user has exceeded the number of videos they may upload." reason: uploadLimitExceeded>')
        self.assertTrue(uploader.is_upload_limit(e))
        self.assertFalse(uploader.is_upload_limit(RuntimeError("boom")))

    def test_upload_turns_it_into_a_wait(self):
        orig = uploader._upload_youtube
        def boom(*a, **k):
            raise RuntimeError("reason: uploadLimitExceeded")
        uploader._upload_youtube = boom
        try:
            with self.assertRaises(uploader.UploadLimit):
                uploader.upload_youtube({}, "f", {}, None)
        finally:
            uploader._upload_youtube = orig


if __name__ == "__main__":
    unittest.main()
