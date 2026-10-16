"""vv18: the jump ball is found from the score bug when the scoreboard clock cannot be read."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from sportsclipper import analyze  # noqa: E402

H, W = 72, 128


def broadcast(cut_at=50, bug_at=60, seconds=200, logo=False, seed=1):
    """Fake thumbnails: two camera shots (pictures that pan about), and a bug (sharp bars) from bug_at on."""
    rng = np.random.default_rng(seed)
    base = [rng.integers(60, 180, (H, W)).astype(np.float32) for _ in range(3)]
    base = [np.kron(b[::8, ::8], np.ones((8, 8), np.float32)) for b in base]       # blocky = smooth enough
    out = np.zeros((seconds, H, W), np.uint8)
    for t in range(seconds):
        shot = base[0] if t < cut_at else base[1]
        img = np.roll(shot, (int(rng.integers(0, H)), int(rng.integers(0, W))), (0, 1)) + rng.normal(0, 3, (H, W))   # the camera pans
        if t >= bug_at:
            img[60:67, 34:94] = 20                                             # dark bug...
            img[62:65, 36:92:4] = 240                                          # ...with bright digits
        if logo:
            img[4:10, 110:124] = 250
            img[5:9, 112:122:3] = 10
        out[t] = np.clip(img, 0, 255).astype(np.uint8)
    return out


class Bug(unittest.TestCase):
    def test_bug_onset_found_anywhere(self):
        self.assertAlmostEqual(analyze.bug_onset(broadcast()), 60, delta=1)

    def test_top_corner_bug_too(self):
        th = broadcast()[:, ::-1, :].copy()                                    # upside down: the bug is now at the top
        self.assertAlmostEqual(analyze.bug_onset(th), 60, delta=1)

    def test_a_watermark_there_from_the_start_is_not_the_bug(self):
        self.assertAlmostEqual(analyze.bug_onset(broadcast(logo=True)), 60, delta=1)

    def test_no_bug_no_answer(self):
        th = broadcast(bug_at=10_000)
        self.assertIsNone(analyze.bug_onset(th))
        self.assertIsNone(analyze.tipoff_from_bug(th))

    def test_jump_ball_is_3s_into_the_last_cut_before_the_bug(self):
        # a calm picture with cuts at 38 (graphic, the biggest) and 55 (the wide shot), bug at 64: the LAST clear cut counts
        th = np.zeros((120, H, W), np.uint8)
        pics = [np.full((H, W), v, np.uint8) for v in (40, 200, 90)]
        for t in range(120):
            th[t] = pics[0] if t < 38 else pics[1] if t < 55 else pics[2]
        with mock.patch.object(analyze, "bug_onset", return_value=64.0):
            self.assertEqual(analyze.tipoff_from_bug(th), 58.0)

    def test_no_clear_cut_means_a_little_before_the_bug(self):
        th = broadcast(cut_at=10_000, bug_at=60)
        self.assertAlmostEqual(analyze.tipoff_from_bug(th), 52, delta=1)

    def test_short_video_is_ignored(self):
        self.assertIsNone(analyze.bug_onset(broadcast(seconds=30, bug_at=10)))


if __name__ == "__main__":
    unittest.main()
