import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sportsclipper import results

class ResultsTests(unittest.TestCase):
    def test_groups_clips_and_sorts_sizes(self):
        d = tempfile.mkdtemp()
        folder = os.path.join(d, "Game_One")
        os.makedirs(folder)
        for n in ["Game_One_360p.mp4", "Game_One_1080p_upscaled.mp4", "Game_One_720p.mp4", "Game_One_thumb.jpg"]:
            open(os.path.join(folder, n), "w").close()
        r = results.scan_outputs(d)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["title"], "Game One")
        self.assertEqual([h for h, _ in r[0]["videos"]], [1080, 720, 360])
        self.assertTrue(r[0]["thumb"].endswith("Game_One_thumb.jpg"))

    def test_missing_folder_is_empty(self):
        self.assertEqual(results.scan_outputs("/nonexistent/dir"), [])

if __name__ == "__main__":
    unittest.main()
