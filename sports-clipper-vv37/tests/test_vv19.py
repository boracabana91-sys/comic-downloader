"""vv19: the end of the game comes from the score bug too (no more guessing a fixed cut at the end)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from sportsclipper import analyze, config  # noqa: E402
from test_vv18 import broadcast  # noqa: E402


class GameEnd(unittest.TestCase):
    def test_bug_goes_away_after_the_final_buzzer(self):
        t = analyze.bug_track(broadcast(bug_at=30, bug_until=150, seconds=200))
        self.assertAlmostEqual(t["onset"], 30, delta=1)
        self.assertAlmostEqual(t["end"], 150, delta=1)

    def test_bug_on_screen_until_the_very_last_second_means_no_end_cut(self):
        t = analyze.bug_track(broadcast(bug_at=30, seconds=200))
        self.assertGreaterEqual(t["end"], 199)

    def test_replay_gaps_do_not_end_the_game(self):
        th = broadcast(bug_at=30, bug_until=170, seconds=200)
        gap = broadcast(bug_at=10_000, seconds=200)             # the same shots with no bug: a 12 s replay in the middle
        th[90:102] = gap[90:102]
        self.assertAlmostEqual(analyze.bug_track(th)["end"], 170, delta=1)

    def test_a_lonely_blip_after_the_game_is_not_the_end(self):
        th = broadcast(bug_at=30, bug_until=170, seconds=250)
        blip = broadcast(bug_at=0, seconds=250)
        th[232:244] = blip[232:244]                             # a 12 s flicker of a bug-like picture long after the game (the interview)
        self.assertAlmostEqual(analyze.bug_track(th)["end"], 170, delta=1)

    def test_track_is_shared_with_the_jump_ball_search(self):
        th = broadcast(cut_at=50, bug_at=60)
        tr = analyze.bug_track(th)
        with mock.patch.object(analyze, "bug_track", side_effect=AssertionError("must reuse the track")):
            self.assertIsNotNone(analyze.tipoff_from_bug(th, track=tr))

    def test_jump_ball_tick_is_on_by_default(self):
        self.assertTrue(config.load("/nonexistent")["start_at_tipoff"])


if __name__ == "__main__":
    unittest.main()
