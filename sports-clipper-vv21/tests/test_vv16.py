"""vv16: head-and-neck close-ups as extra photo options."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_vv14 import add  # noqa: E402
from PIL import Image  # noqa: E402
from sportsclipper import preview, roster  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import get_players  # noqa: E402


class CloseUps(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        add(self.d, "MIA", "Bam Adebayo", ("cutout.png", "cutout2.png", "head1.png", "head2.png"))
        fol = os.path.join(self.d, roster.folder_name("MIA", "Bam Adebayo"))
        with open(os.path.join(fol, "old.txt"), "w") as f:
            f.write("2")

    def test_close_ups_come_after_the_photos_and_are_flagged(self):
        o = roster.options("MIA", self.d)[0]
        self.assertEqual([os.path.basename(p) for p in o["cutouts"]], ["cutout.png", "cutout2.png", "head1.png", "head2.png"])
        self.assertEqual(o["close"], [2, 3])

    def test_close_up_inherits_old_team_from_its_photo(self):
        o = roster.options("MIA", self.d)[0]
        self.assertEqual(o["old"], [1, 3])          # cutout2 and head2 show the old jersey

    def test_default_photo_is_still_the_first_full_one(self):
        png, _ = roster.find_star("MIA", self.d)
        self.assertEqual(os.path.basename(png), "cutout.png")

    def test_head_crop_needs_a_face(self):
        blank = Image.new("RGBA", (800, 1100), (0, 0, 0, 0))
        self.assertIsNone(get_players.head_crop(blank))


if __name__ == "__main__":
    unittest.main()
