"""vv15: old-jersey photos are options, never the default."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_vv14 import add  # noqa: E402
from sportsclipper import preview, roster  # noqa: E402


class OldTeam(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        add(self.d, "MIA", "Giannis Antetokounmpo", ("cutout.png",))
        add(self.d, "MIA", "Bam Adebayo", ("cutout.png", "cutout2.png", "cutout3.png"))
        for who, marks in (("Giannis Antetokounmpo", "1"), ("Bam Adebayo", "2 3")):
            with open(os.path.join(self.d, roster.folder_name("MIA", who), "old.txt"), "w") as f:
                f.write(marks)

    def test_old_first_photo_is_not_the_default(self):
        names = [o["name"] for o in roster.options("MIA", self.d)]
        self.assertEqual(names, ["Bam Adebayo", "Giannis Antetokounmpo"])

    def test_old_photos_are_flagged_but_still_offered(self):
        bam = roster.options("MIA", self.d)[0]
        self.assertEqual(bam["old"], [1, 2])
        self.assertEqual(len(bam["cutouts"]), 3)

    def test_without_marker_nothing_changes(self):
        os.remove(os.path.join(self.d, roster.folder_name("MIA", "Giannis Antetokounmpo"), "old.txt"))
        names = [o["name"] for o in roster.options("MIA", self.d)]
        self.assertEqual(names[0], "Giannis Antetokounmpo")


if __name__ == "__main__":
    unittest.main()
