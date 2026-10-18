"""0.9: exact frame rate, upload size first, and Highlights chunk dropping."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sportsclipper import analyze, render  # noqa: E402


class V09(unittest.TestCase):
    def test_rate_kept_exact(self):
        self.assertEqual(render.rate_str(29.97), "30000/1001")
        self.assertEqual(render.rate_str(59.94), "60000/1001")
        self.assertEqual(render.rate_str(25.0), "25")

    def test_upload_size_first(self):
        self.assertEqual(render.first_size([2160, 1080, 720, 480], 1080), 1080)
        self.assertEqual(render.first_size([720, 480], 1080), 720)

    def test_even_drop_hits_target_and_keeps_order(self):
        segs = [[i * 30.0, i * 30.0 + 30] for i in range(30)]          # 900 s of play in 30 s chunks
        loud = np.zeros(900); loud[455] = 10                              # one big moment in chunk 15
        kept = analyze._even_drop(segs, loud, 0.75 * 900)
        total = sum(segs[i][1] - segs[i][0] for i in kept)
        self.assertLessEqual(total, 0.75 * 900 * 1.02)
        self.assertGreaterEqual(total, 0.75 * 900 * 0.94)
        self.assertEqual(kept, sorted(kept))
        self.assertIn(0, kept)                                            # tip-off chunk
        self.assertIn(15, kept)                                           # loudest moment
        self.assertTrue(all(i in kept for i in range(26, 30)))            # last 2 minutes
        dropped = [i for i in range(30) if i not in kept]
        self.assertFalse(any(b - a == 1 for a, b in zip(dropped, dropped[1:])), "no back-to-back drops")
        gaps = [b - a for a, b in zip(dropped, dropped[1:])]
        self.assertLessEqual(max(gaps), 5, "drops are spread through the game")


if __name__ == "__main__":
    unittest.main()
