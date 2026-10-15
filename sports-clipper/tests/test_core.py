"""Self-tests. Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sportsclipper import analyze, config, media, render, rights, schedule, store  # noqa: E402


def make_video(path, secs=60, w=1280, h=720):
    """A fake broadcast: the 'clock' digits flip every second while live (0-20s, 30-50s), frozen otherwise."""
    live = "between(t,0,20)+between(t,30,50)"
    x, y = int(w * 0.475), int(h * 0.828)
    a = f"drawbox=x={x+4}:y={y+4}:w=20:h=14:color=white:t=fill:enable='(lt(mod(t,2),1)*({live}))+(1-({live}))'"
    b = f"drawbox=x={x+36}:y={y+16}:w=20:h=14:color=white:t=fill:enable='gte(mod(t,2),1)*({live})'"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x101010:s={w}x{h}:r=30:d={secs}",
                    "-f", "lavfi", "-i", f"sine=f=440:d={secs}", "-vf", f"{a},{b}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", path], check=True)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.vid = os.path.join(cls.tmp, "fake.mp4")
        make_video(cls.vid)

    def cfg(self):
        c = config.load("/nonexistent")
        c.update(target_ratio=1.0, pad_s=0.5, min_clip_s=3)
        return c

    def test_dead_time_cut(self):
        p = analyze.plan(self.vid, self.cfg(), log=lambda *_: None)
        covered = lambda t: any(a <= t <= b for a, b in p["segments"])
        for t in (5, 15, 35, 45):
            self.assertTrue(covered(t), f"live second {t} was cut")
        for t in (24, 27, 55):
            self.assertFalse(covered(t), f"frozen second {t} was kept")

    def test_target_ratio_and_order(self):
        c = self.cfg(); c["target_ratio"] = 0.45; c["max_clip_s"] = 10
        p = analyze.plan(self.vid, c, log=lambda *_: None)
        self.assertLessEqual(p["kept_s"], 0.45 * 60 + 1)
        starts = [a for a, _ in p["segments"]]
        self.assertEqual(starts, sorted(starts), "clips must stay in game order")

    def test_render_ladder_and_duration(self):
        c = self.cfg()
        p = analyze.plan(self.vid, c, log=lambda *_: None)
        outs = render.render(self.vid, p["segments"], p["info"], c, os.path.join(self.tmp, "o", "x"), log=lambda *_: None)
        self.assertEqual(sorted(outs), [360, 480, 720])      # 720p source: no fake 4K / 1080p
        for h, f in outs.items():
            i = media.probe(f)
            self.assertEqual(i["height"], h)
            self.assertTrue(i["has_audio"])
            self.assertAlmostEqual(i["duration"], p["kept_s"], delta=1.5)

    def test_upscale_flag(self):
        self.assertEqual(render.ladder(720, [2160, 1080, 720], True), [2160, 1080, 720])
        self.assertEqual(render.ladder(2160, [2160, 1080, 720], False), [2160, 1080, 720])

    def test_rights_gate(self):
        with self.assertRaises(rights.NotLicensed):
            rights.check(rights.Source("x", "youtube", "UC" + "a" * 22))
        with self.assertRaises(rights.NotLicensed):
            rights.check(rights.Source("x", "youtube", "UC" + "a" * 22, licensed=True, license_note="  "))
        rights.check(rights.Source("x", "youtube", "UC" + "a" * 22, True, "written permission 2026-10-01"))

    def test_schedule(self):
        now = datetime(2026, 10, 15, 10, 0)
        self.assertEqual(schedule.next_scan(now, {"mode": "times", "times": ["09:00", "21:00"]}), datetime(2026, 10, 15, 21, 0))
        self.assertEqual(schedule.next_scan(now, {"mode": "times", "times": ["09:00"]}), datetime(2026, 10, 16, 9, 0))
        self.assertEqual(schedule.next_scan(now, {"mode": "interval", "hours": 2}, last=datetime(2026, 10, 15, 9, 0)), datetime(2026, 10, 15, 11, 0))

    def test_store(self):
        s = store.Store(os.path.join(self.tmp, "s.sqlite"))
        self.assertFalse(s.seen("a", "1")); s.set("a", "1", "t", "done"); self.assertTrue(s.seen("a", "1"))
        s.set("a", "2", "t", "error"); self.assertFalse(s.seen("a", "2"))


if __name__ == "__main__":
    unittest.main()
