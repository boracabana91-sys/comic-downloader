"""vv24: Best Clips (off by default) and the YT Preview that shows before the video is cut."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import analyze, config, pipeline, post, rights, rules, sources  # noqa: E402


def cfg():
    c = config.load(os.path.join(tempfile.mkdtemp(), "none.json"))
    c["ai"]["enabled"] = False
    return c


class BestClips(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(config.DEFAULTS["best_clips"])

    def test_picks_the_loudest_moments_in_game_order(self):
        n = 600
        live = np.ones(n, bool)
        rz = np.zeros(n); mz = np.zeros(n); hz = np.zeros(n)
        rz[100] = 5; rz[300] = 9; rz[500] = 7
        segs = analyze.best_clips(live, rz, mz, hz, max_s=40)
        self.assertEqual(len(segs), 2)                                  # 18 s each: two fit in 40 s
        self.assertTrue(segs[0][0] < 300 < segs[0][1] and segs[1][0] < 500 < segs[1][1])   # the two loudest, in order
        self.assertLessEqual(sum(b - a for a, b in segs), 40 * 1.02)

    def test_commentary_excitement_counts(self):
        n = 400
        live = np.ones(n, bool)
        hz = analyze.hype_track([(200.0, "Oh my! From downtown, bang!")], n)
        segs = analyze.best_clips(live, np.zeros(n), np.zeros(n), hz, max_s=20)
        self.assertTrue(segs and segs[0][0] <= 200 <= segs[0][1])

    def test_never_runs_through_dead_time_or_outside_the_game(self):
        n = 300
        live = np.ones(n, bool); live[100:200] = False
        rz = np.zeros(n); rz[105] = 9; rz[150] = 9; rz[250] = 5
        segs = analyze.best_clips(live, rz, np.zeros(n), np.zeros(n), max_s=600, start_s=20, end_s=280)
        for a, b in segs:
            self.assertTrue(live[int(a):int(b)].all() and a >= 20 and b <= 280)

    def test_each_clip_is_inside_one_running_stretch(self):
        n = 120
        live = np.ones(n, bool); live[58:62] = False
        rz = np.zeros(n); rz[60 - 4] = 3; rz[56] = 3
        segs = analyze.best_clips(live, rz, np.zeros(n), np.zeros(n), max_s=100)
        for a, b in segs:
            self.assertFalse((~live[int(a):int(b)]).any())


class Preview(unittest.TestCase):
    def test_pending_file_check_passes_before_the_video_exists(self):
        c = cfg()
        pp = post.plan_post(c, "Oklahoma City Thunder vs Houston Rockets FULL GAME HIGHLIGHTS | October 15, 2026",
                            datetime(2026, 10, 15, tzinfo=timezone.utc), 600, lambda m: None, "", "A", cues=[])
        f = os.path.join(tempfile.mkdtemp(), pp["stem"] + "_1080p.mp4")
        self.assertTrue(rules.failed(rules.check(pp["meta"], f, pp["teams"], "x", c)))                  # no file yet
        self.assertEqual(rules.failed(rules.check(pp["meta"], f, pp["teams"], "Oklahoma City Thunder vs Houston Rockets FULL GAME HIGHLIGHTS", c, pending=True)), [])

    def test_the_preview_is_sent_before_anything_is_rendered(self):
        c = cfg(); c["upload"]["enabled"] = False; c["thumbnail"]["enabled"] = False
        tmp = tempfile.mkdtemp(); c["output_dir"] = tmp; c["work_dir"] = tmp
        with mock.patch.object(config, "HOME", tmp):
            pl = pipeline.Pipeline(c, lambda m: None)
        order = []
        pl.on_preview = lambda r: order.append(("preview", r))
        src = rights.Source("A", "youtube", "UCa", True, "mine")
        v = sources.Video("g1", "Oklahoma City Thunder vs Houston Rockets FULL GAME HIGHLIGHTS", datetime(2026, 10, 15, tzinfo=timezone.utc), url="https://youtu.be/xxxxxxxxxxx")
        info = {"height": 1080, "width": 1920, "duration": 3000, "has_audio": True, "codec": "h264"}

        def fake_render(path, segs, info_in, cfg_, out_base, log=print, only=None, intro=None):
            order.append(("render", None))
            return {h: out_base + f"_{h}p.mp4" for h in (only or [1080])}
        plan = {"segments": [[0, 600]], "kept_s": 600.0}
        with mock.patch.object(pipeline.sources, "fetch", return_value="/x.mp4"), mock.patch.object(pipeline.media, "probe", return_value=info), \
             mock.patch.object(pipeline.captions, "fetch", return_value=[]), mock.patch.object(pipeline.analyze, "plan", return_value=plan), \
             mock.patch.object(pipeline.render, "render", side_effect=fake_render), mock.patch.object(pipeline.finish, "intro_picture", return_value=None), \
             mock.patch.object(pipeline.finish, "make_thumb", return_value=None), mock.patch.object(pipeline.finish, "add_cover"), \
             mock.patch.object(pl, "_render_rest"):
            r = pl.process(src, v, upload=False)
        self.assertEqual(order[0][0], "preview")                              # first, even with upload off
        self.assertEqual(order[1][0], "render")
        self.assertTrue(order[0][1]["preview"] and order[0][1]["post"]["meta"]["title"])
        self.assertIn("post", r)                                              # the finished result carries it too
        self.assertTrue(r["checks"])


if __name__ == "__main__":
    unittest.main()
