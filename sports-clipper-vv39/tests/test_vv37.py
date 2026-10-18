"""vv37: Best Clips takes whole plays (never cut mid-play), skips crowd/bench/interview shots, stops at the final buzzer."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import analyze, config  # noqa: E402

N = 400
SEGS = [[10.0, 40.0], [50.0, 80.0], [90.0, 120.0], [130.0, 160.0], [170.0, 200.0], [210.0, 240.0], [250.0, 280.0], [290.0, 320.0]]


def arrays(loud=None, calm=()):
    rz = np.zeros(N); mz = np.zeros(N); hz = np.zeros(N); motion = np.ones(N) * 10.0
    for t, v in (loud or {}).items():
        rz[t] = v
    for i in calm:
        a, b = SEGS[i]; motion[int(a):int(b)] = 1.0
    return rz, mz, hz, motion


class Plays(unittest.TestCase):
    def test_every_pick_is_a_whole_play(self):
        rz, mz, hz, mo = arrays({95: 6, 215: 5, 295: 4})
        out = analyze.best_plays(SEGS, rz, mz, hz, mo, 300, 10.0, 330.0, share=0.4)
        for a, b in out:
            self.assertTrue(any(abs(a - s[0]) < 1e-6 and abs(b - s[1]) < 1e-6 for s in SEGS), (a, b))   # a pick is a whole play, not a slice
        starts = {tuple(x) for x in out}
        for s in ([90.0, 120.0], [210.0, 240.0], [290.0, 320.0]):
            self.assertIn(tuple(s), starts)                 # the plays with the loudest moments, from start to end

    def test_the_jump_ball_play_always_opens(self):
        rz, mz, hz, mo = arrays({215: 9})
        out = analyze.best_plays(SEGS, rz, mz, hz, mo, 300, 10.0, 330.0, share=0.2)
        self.assertEqual(out[0], [10.0, 40.0])

    def test_calm_shots_are_left_out(self):
        rz, mz, hz, mo = arrays({95: 1, 135: 9, 215: 2}, calm=(3,))     # the loudest chunk is a crowd shot with no movement
        out = analyze.best_plays(SEGS, rz, mz, hz, mo, 300, 10.0, 330.0, share=0.9)
        self.assertNotIn([130.0, 160.0], out)

    def test_nothing_after_the_final_buzzer(self):
        rz, mz, hz, mo = arrays({295: 9})
        out = analyze.best_plays(SEGS, rz, mz, hz, mo, 300, 10.0, 300.0, share=1.0)
        self.assertLessEqual(out[-1][1], 300.0)
        self.assertNotIn([290.0, 320.0], out)

    def test_never_more_than_the_limit(self):
        rz, mz, hz, mo = arrays({95: 5, 215: 5})
        out = analyze.best_plays(SEGS, rz, mz, hz, mo, 70, 10.0, 330.0, share=1.0)
        self.assertLessEqual(sum(b - a for a, b in out), 70 * 1.02 + 1)

    def test_empty_inputs(self):
        rz, mz, hz, mo = arrays()
        self.assertEqual(analyze.best_plays([], rz, mz, hz, mo, 100), [])

    def test_buzzer_pad_is_short_and_share_is_configured(self):
        self.assertLessEqual(analyze.END_PAD_S, 2)
        self.assertEqual(config.DEFAULTS["best_clips_share"], 0.5)


if __name__ == "__main__":
    unittest.main()
