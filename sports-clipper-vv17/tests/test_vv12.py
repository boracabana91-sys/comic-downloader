"""vv12: the finished length is between your minimum and maximum minutes, whatever the clock reading does."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sportsclipper import analyze, config  # noqa: E402
from sportsclipper.selfcheck import make_video  # noqa: E402


class Lengths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.vid = os.path.join(cls.tmp, "g.mp4")
        make_video(cls.vid, secs=300)                   # 5 minutes; the fake clock runs 0-20 s and 30-50 s of every minute? no: first minute only

    def cfg(self, lo, hi):
        c = config.load("/nonexistent")
        c.update(min_minutes=lo, max_minutes=hi, pad_s=0.5, min_clip_s=3, allow_upscale=False)
        return c

    def test_lengths_helper(self):
        self.assertEqual(analyze.lengths({"min_minutes": 8, "max_minutes": 12}), (480, 720))
        self.assertEqual(analyze.lengths({"min_minutes": 10, "max_minutes": 5}), (600, 600))     # max never below min
        self.assertEqual(analyze.lengths({}), (480, 720))

    def test_unreadable_clock_still_gives_the_minimum(self):
        """The bug: when the scoreboard clock could not be read the clip came out ~1 minute long."""
        c = self.cfg(1.5, 2.5); c["clock_roi"] = [0.02, 0.02, 0.05, 0.05]     # nowhere near the clock
        logs = []
        p = analyze.plan(self.vid, c, log=logs.append)
        self.assertGreaterEqual(p["kept_s"], 1.5 * 60 * 0.95)
        self.assertLessEqual(p["kept_s"], 2.5 * 60 * 1.16)
        self.assertTrue(any("could not read the scoreboard" in m for m in logs))
        self.assertEqual([a for a, _ in p["segments"]], sorted(a for a, _ in p["segments"]))

    def test_highlights_with_unreadable_clock(self):
        c = self.cfg(1.5, 2.5); c["clock_roi"] = [0.02, 0.02, 0.05, 0.05]; c["highlights"] = True
        p = analyze.plan(self.vid, c, log=lambda *_: None)
        self.assertGreaterEqual(p["kept_s"], 1.5 * 60 * 0.95)
        self.assertLessEqual(p["kept_s"], 2.5 * 60 * 1.16)

    def test_short_live_play_is_topped_up_to_the_minimum(self):
        c = self.cfg(1.0, 1.5)                          # clock readable: only ~40 s of live play, but 60 s is the minimum
        p = analyze.plan(self.vid, c, log=lambda *_: None)
        self.assertGreaterEqual(p["kept_s"], 57)
        self.assertLessEqual(p["kept_s"], 1.5 * 60 * 1.05)

    def test_a_video_shorter_than_the_minimum_is_kept_whole(self):
        p = analyze.plan(self.vid, self.cfg(10, 12), log=lambda *_: None)
        self.assertAlmostEqual(p["kept_s"], 300, delta=1)


if __name__ == "__main__":
    unittest.main()
