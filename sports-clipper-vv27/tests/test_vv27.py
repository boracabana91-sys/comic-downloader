"""vv27: drag-and-drop update and the red claim button."""
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import config, selfupdate  # noqa: E402


def fake_zip(inner="SportsClipper.app", with_exe=True):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "SportsClipper-Mac.zip")
    with zipfile.ZipFile(p, "w") as z:
        if with_exe:
            z.writestr(f"{inner}/Contents/MacOS/SportsClipper", "#!/bin/sh\n")
        z.writestr(f"{inner}/Contents/Info.plist", "<plist/>")
    return p


class Update(unittest.TestCase):
    def test_drop_paths_with_spaces_and_braces(self):
        self.assertEqual(selfupdate.parse_drop("{/Users/me/My Downloads/SportsClipper-Mac.zip}"), ["/Users/me/My Downloads/SportsClipper-Mac.zip"])
        self.assertEqual(selfupdate.parse_drop("/a/b.zip /c/d.zip"), ["/a/b.zip", "/c/d.zip"])
        self.assertEqual(selfupdate.parse_drop("{/a b/c.zip} /d.zip"), ["/a b/c.zip", "/d.zip"])
        self.assertEqual(selfupdate.parse_drop(""), [])

    def test_a_real_update_zip_is_unpacked(self):
        work = tempfile.mkdtemp()
        with mock.patch.object(selfupdate.sys, "platform", "linux"):
            app = selfupdate.prepare(fake_zip(), work)
        self.assertTrue(app.endswith("SportsClipper.app") and os.path.isfile(os.path.join(app, "Contents", "MacOS", "SportsClipper")))

    def test_the_app_one_folder_down_is_found(self):
        work = tempfile.mkdtemp()
        with mock.patch.object(selfupdate.sys, "platform", "linux"):
            app = selfupdate.prepare(fake_zip(inner="SportsClipper-Mac/SportsClipper.app"), work)
        self.assertTrue(app.endswith("SportsClipper.app"))

    def test_other_files_are_refused_in_plain_words(self):
        work = tempfile.mkdtemp()
        with mock.patch.object(selfupdate.sys, "platform", "linux"):
            with self.assertRaises(ValueError) as e:
                selfupdate.prepare(fake_zip(with_exe=False), work)
            self.assertIn("not a Sports Clipper update", str(e.exception))
            bad = os.path.join(tempfile.mkdtemp(), "notes.txt"); open(bad, "w").close()
            with self.assertRaises(ValueError):
                selfupdate.prepare(bad, work)

    def test_where_the_app_cannot_be_replaced(self):
        self.assertIn("installed Mac app", selfupdate.check_target(None))
        self.assertIn("Applications", selfupdate.check_target("/private/var/AppTranslocation/ABC/d/SportsClipper.app"))
        d = tempfile.mkdtemp()
        self.assertEqual(selfupdate.check_target(os.path.join(d, "SportsClipper.app")), "")

    def test_the_swap_script_waits_swaps_keeps_a_backup_and_reopens(self):
        s = selfupdate.helper_script(123, "/Applications/SportsClipper.app", "/h/new/SportsClipper.app", "/h/prev/SportsClipper.app")
        self.assertIn("kill -0 123", s)
        self.assertIn("mv '/Applications/SportsClipper.app' '/h/prev/SportsClipper.app'", s)
        self.assertIn("mv '/h/new/SportsClipper.app' '/Applications/SportsClipper.app'", s)
        self.assertIn("open '/Applications/SportsClipper.app'", s)
        self.assertIn("&&", s)                                   # the new app moves in only if the old one moved out

    def test_quotes_in_paths_are_safe(self):
        s = selfupdate.helper_script(1, "/a/it's/SportsClipper.app", "/n/SportsClipper.app", "/b/SportsClipper.app")
        self.assertIn("'/a/it'\\''s/SportsClipper.app'", s)

    def test_the_swap_runs_for_real(self):
        d = tempfile.mkdtemp()
        old, new, back = (os.path.join(d, x, "SportsClipper.app") for x in ("apps", "new", "prev"))
        for p, mark in ((old, "old"), (new, "new")):
            os.makedirs(p); open(os.path.join(p, "v.txt"), "w").write(mark)
        os.makedirs(os.path.dirname(back))
        script = os.path.join(d, "swap.sh")
        body = selfupdate.helper_script(99999999, old, new, back).replace("/usr/bin/open", "true")
        open(script, "w").write(body)
        import subprocess
        subprocess.run(["/bin/bash", script], check=True, timeout=20)
        self.assertEqual(open(os.path.join(old, "v.txt")).read(), "new")
        self.assertEqual(open(os.path.join(back, "v.txt")).read(), "old")


if __name__ == "__main__":
    unittest.main()
