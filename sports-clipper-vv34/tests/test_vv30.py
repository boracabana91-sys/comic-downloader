"""vv30: the channel list comes from the uploads list; missing titles are filled; every left-out video says why."""
import os
import sys
import unittest
from datetime import timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sportsclipper import sources  # noqa: E402
import test_vv29 as t29  # noqa: E402


class Listing(unittest.TestCase):
    def test_uploads_list_is_asked_first(self):
        asked = []
        entries = {"entries": [{"id": "a1", "title": "Phoenix Suns vs Utah Jazz Full Game Highlights - October 16, 2026", "duration": 586,
                                "view_count": 23000, "timestamp": 1760600000}]}
        def flat(url, **k):
            asked.append(url); return entries
        src = t29.rights.Source("A", "youtube", "UCe4ipLL5WOgOzAW4FoUNgxQ", True, "mine")
        with mock.patch.object(sources, "list_videos", return_value=[]), mock.patch.object(sources, "_flat", side_effect=flat):
            out = sources.list_recent(src, 50)
        self.assertEqual(asked[0], "https://www.youtube.com/playlist?list=UUe4ipLL5WOgOzAW4FoUNgxQ")       # UC + id -> UU + id
        self.assertEqual(out[0].id, "a1"); self.assertEqual(out[0].views, 23000)

    def test_falls_back_to_the_videos_tab(self):
        asked = []
        def flat(url, **k):
            asked.append(url)
            if "playlist?list" in url:
                raise RuntimeError("blocked")
            return {"entries": [{"id": "b1", "title": "x", "timestamp": 1760600000}]}
        src = t29.rights.Source("A", "youtube", "UCe4ipLL5WOgOzAW4FoUNgxQ", True, "mine")
        with mock.patch.object(sources, "list_videos", return_value=[]), mock.patch.object(sources, "_flat", side_effect=flat):
            out = sources.list_recent(src, 50)
        self.assertEqual(len(asked), 2); self.assertEqual(out[0].id, "b1")

    def test_title_only_an_id_is_filled_from_the_video_page(self):
        entries = {"entries": [{"id": "c1", "title": "c1", "timestamp": 1760600000}]}
        info = {"title": "Dallas Mavericks vs Atlanta Hawks Full Game Highlights - October 16, 2026", "duration": 580, "view_count": 63000}
        class Y:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, url, download=False): return info
        import types
        fake = types.SimpleNamespace(YoutubeDL=Y)
        with mock.patch.object(sources, "list_videos", return_value=[]), mock.patch.object(sources, "_flat", return_value=entries), \
             mock.patch.dict(sys.modules, {"yt_dlp": fake}):
            out = sources.list_recent(t29.SRC, 50)
        self.assertIn("Dallas Mavericks", out[0].title); self.assertEqual(out[0].duration, 580)


class WhyLeftOut(unittest.TestCase):
    def test_each_left_out_video_gets_a_reason_and_is_logged(self):
        pl = t29.make_pl(); logs = []; pl.log = logs.append
        vids = [t29.vid(0), t29.vid(1, "Funny moment #shorts"), t29.vid(2, "Random vlog")]
        new, _h, _o = pl.scan_view(t29.SRC, 5, vids=vids)
        self.assertEqual([v.id for v in new], ["id0"])
        self.assertEqual(len(pl.left_out), 2)
        self.assertTrue(all(v.state.startswith("left out: ") for v in pl.left_out))
        self.assertTrue(any("left out: 'Random vlog'" in m for m in logs))


if __name__ == "__main__":
    unittest.main()
