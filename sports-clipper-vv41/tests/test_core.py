"""Self-tests. Run: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2  # noqa: E402
from sportsclipper import analyze, checks, config, media, metadata, render, rights, schedule, sources, store, thumbnail  # noqa: E402
from sportsclipper.selfcheck import make_video  # noqa: E402


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.vid = os.path.join(cls.tmp, "fake.mp4")
        make_video(cls.vid)

    def cfg(self):
        c = config.load("/nonexistent")
        c.update(min_minutes=0.5, max_minutes=2.0, pad_s=0.5, min_clip_s=3, allow_upscale=False)
        return c

    def test_dead_time_cut(self):
        p = analyze.plan(self.vid, self.cfg(), log=lambda *_: None)
        covered = lambda t: any(a <= t <= b for a, b in p["segments"])
        for t in (5, 15, 35, 45):
            self.assertTrue(covered(t), f"live second {t} was cut")
        for t in (24, 27, 55):
            self.assertFalse(covered(t), f"frozen second {t} was kept")

    def test_max_minutes_and_order(self):
        c = self.cfg(); c["min_minutes"] = 0.5; c["max_minutes"] = 0.5; c["max_clip_s"] = 10     # 40 s of live play, 30 s allowed
        p = analyze.plan(self.vid, c, log=lambda *_: None)
        self.assertLessEqual(p["kept_s"], 31)
        self.assertGreaterEqual(p["kept_s"], 26)
        starts = [a for a, _ in p["segments"]]
        self.assertEqual(starts, sorted(starts), "clips must stay in game order")

    def test_render_ladder_and_duration(self):
        c = self.cfg()
        p = analyze.plan(self.vid, c, log=lambda *_: None)
        outs = render.render(self.vid, p["segments"], p["info"], c, os.path.join(self.tmp, "o", "x"), log=lambda *_: None)
        self.assertEqual(sorted(outs), [360, 480, 720])
        for h, f in outs.items():
            i = media.probe(f)
            self.assertEqual(i["height"], h)
            self.assertTrue(i["has_audio"])
            self.assertAlmostEqual(i["duration"], p["kept_s"], delta=1.5)

    def test_ticked_1080_is_produced_as_upscaled(self):
        c = self.cfg(); c["allow_upscale"] = True; c["resolutions"] = [1080, 720]
        p = analyze.plan(self.vid, c, log=lambda *_: None)
        outs = render.render(self.vid, p["segments"], p["info"], c, os.path.join(self.tmp, "u", "x"), log=lambda *_: None)
        self.assertEqual(sorted(outs), [720, 1080])
        self.assertIn("_1080p_upscaled", outs[1080])
        self.assertEqual(media.probe(outs[1080])["height"], 1080)

    def test_upscale_flag(self):
        self.assertEqual(render.ladder(720, [2160, 1080, 720], True), [2160, 1080, 720])
        self.assertEqual(render.ladder(720, [2160, 1080, 720], False), [720])

    def test_rights_gate(self):
        with self.assertRaises(rights.NotLicensed):
            rights.check(rights.Source("x", "youtube", "UC" + "a" * 22))
        with self.assertRaises(rights.NotLicensed):
            rights.check(rights.Source("x", "youtube", "UC" + "a" * 22, licensed=True, license_note="  "))
        rights.check(rights.Source("x", "youtube", "UC" + "a" * 22, True, "owner confirmed"))

    def test_channel_html_parsing(self):
        page = ('<meta property="og:title" content="NBA &amp; Friends">'
                '<script>{"channelId":"UC' + "a" * 22 + '"}</script>')
        cid, name = sources.parse_channel_html(page)
        self.assertEqual(cid, "UC" + "a" * 22)
        self.assertEqual(name, "NBA & Friends")

    def test_channel_link_forms_without_network(self):
        cid = "UC" + "b" * 22
        self.assertEqual(sources.resolve_youtube(f"https://www.youtube.com/channel/{cid}")["location"], cid)
        with self.assertRaises(ValueError):
            sources.resolve_youtube("https://example.com/x")
        with self.assertRaises(ValueError):
            sources.resolve_youtube("")

    def test_metadata_falls_back_without_key(self):
        c = config.load("/nonexistent"); c["ai"]["enabled"] = True; c["ai"]["api_key"] = ""
        os.environ.pop("ANTHROPIC_API_KEY", None)
        m = metadata.build(c, "Game", "src", 300, log=lambda *_: None)
        self.assertIn("Game", m["title"])

    def test_teams_and_date_from_title(self):
        t = "Denver Nuggets vs Los Angeles Clippers Full Game Highlights - October 14, 2026 | NBA Preseason"
        self.assertEqual(thumbnail.parse_teams(t), ["DEN", "LAC"])
        self.assertEqual(thumbnail.parse_date(t), "OCTOBER 14 2026")
        self.assertEqual(thumbnail.parse_teams("random video"), [])

    def test_thumbnail_is_1080p_and_graded(self):
        out = os.path.join(self.tmp, "thumb.jpg")
        thumbnail.make_thumbnail(self.vid, "Denver Nuggets vs LA Clippers - October 14, 2026", 580, out, log=lambda *_: None)
        img = cv2.imread(out)
        self.assertEqual(img.shape[:2], (1080, 1920))
        self.assertLess(os.path.getsize(out), 2 * 1024 * 1024)

    def test_clip_file_makes_videos_and_thumbnail(self):
        from sportsclipper import job
        c = self.cfg(); c["resolutions"] = [720]
        r = job.clip_file(self.vid, c, "Test Game - October 14, 2026", log=lambda *_: None)
        self.assertTrue(os.path.exists(r["outputs"][720]))
        self.assertTrue(r["thumb"] and os.path.exists(r["thumb"]))

    def test_setup_check_engine(self):
        results = checks.run(config.load("/nonexistent"), log=lambda *_: None, network=False)
        engine = [r for r in results if "cutting engine" in r[1]]
        self.assertTrue(engine and engine[0][0])

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
