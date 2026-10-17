"""vv21: every thumbnail face is levelled, the same size and on the same eye line."""
import glob
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from sportsclipper import facefit, roster, thumbnail  # noqa: E402

PLAYERS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "players")


_GOOD = []


def good_photo():
    """A bundled photo that passes the face check (found, not hard-coded: the library grows)."""
    if not _GOOD:
        for p in sorted(glob.glob(os.path.join(PLAYERS, "*", "head*.png"))):
            i = facefit.analyse(p)
            if i["ok"] and i["face_px"] >= 250:
                _GOOD.append(p); break
    assert _GOOD, "no bundled photo passes the face check"
    return _GOOD[0]


class FaceFit(unittest.TestCase):
    def test_front_facing_photo_passes_and_a_tilted_one_is_rejected(self):
        p = good_photo()
        self.assertTrue(facefit.analyse(p)["ok"])
        with tempfile.TemporaryDirectory() as d:
            q = os.path.join(d, "t.png")
            Image.open(p).convert("RGBA").rotate(28, expand=True, resample=Image.BICUBIC).save(q)
            self.assertFalse(facefit.analyse(q)["ok"])

    def test_fit_puts_eyes_on_the_line_with_the_face_at_the_set_share(self):
        p = good_photo()
        info = facefit.analyse(p)
        self.assertTrue(info["ok"], info["why"])
        w, h = 700, 1080
        out = facefit.fit(p, w, h, info)
        self.assertEqual(out.size, (w, h))
        with tempfile.TemporaryDirectory() as d:
            q = os.path.join(d, "o.png"); out.save(q)
            i2 = facefit.analyse(q)
        (x1, y1), (x2, y2) = i2["eyes"]
        self.assertAlmostEqual(((y1 + y2) / 2) / h, facefit.EYE_LINE, delta=0.03)
        self.assertAlmostEqual(i2["box"][2] / w, facefit.FACE_SHARE, delta=0.06)
        self.assertLess(abs(i2["roll"]), 3)

    def test_a_tilted_photo_is_levelled(self):
        p = good_photo()
        with tempfile.TemporaryDirectory() as d:
            im = Image.open(p).convert("RGBA").rotate(9, expand=True, resample=Image.BICUBIC)
            q = os.path.join(d, "t.png"); im.save(q)
            info = facefit.analyse(q)
            self.assertTrue(info["ok"], info["why"])
            self.assertGreater(abs(info["roll"]), 5)
            out = facefit.fit(q, 700, 1080, info)
            r = os.path.join(d, "l.png"); out.save(r)
            self.assertLess(abs(facefit.analyse(r)["roll"]), 3)

    def test_choose_face_replaces_a_bad_photo_with_a_good_one(self):
        with tempfile.TemporaryDirectory() as d:
            fol = os.path.join(d, "Test Team - TST - Test Player"); os.makedirs(fol)
            good = good_photo()
            Image.open(good).convert("RGBA").rotate(28, expand=True, resample=Image.BICUBIC).save(os.path.join(fol, "cutout.png"))
            Image.open(good).convert("RGBA").save(os.path.join(fol, "cutout2.png"))
            pic, info, note = thumbnail.choose_face(os.path.join(fol, "cutout.png"))
            self.assertTrue(info["ok"])
            self.assertEqual(os.path.basename(pic), "cutout2.png")
            self.assertIn("skipped", note)

    def test_both_faces_in_a_thumbnail_are_the_same_size(self):
        thumbnail.set_layout("closeup")
        for a, b in (("DEN", "MIA"), ("GSW", "LAL"), ("DET", "MIN")):
            stars = [(roster.options(t)[0]["cutout"], "x") for t in (a, b)]
            if any(not facefit.pick(roster.options(t)[0]["cutouts"])[1].get("ok") for t in (a, b)):
                continue                                   # a player with no front-facing photo yet: not a layout problem
            img = thumbnail.versus_thumbnail([a, b], stars, "", 580, None, "FLASHY")
            H, W = img.shape[:2]
            bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            det = facefit._detector()
            widths = []
            for x0, x1 in ((0, W // 2), (W // 2, W)):
                part = np.ascontiguousarray(bgr[:, x0:x1])
                det.setInputSize((part.shape[1], part.shape[0]))
                _, r = det.detect(part)
                self.assertIsNotNone(r, f"no face found on one side of {a} v {b}")
                widths.append(float(sorted(r, key=lambda z: -z[2])[0][2]))
            self.assertLess(max(widths) / min(widths), 1.35, (a, b, widths))


if __name__ == "__main__":
    unittest.main()
