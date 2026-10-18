"""vv29: scan lists show the newest 5 (green) AND older posts with dates; views colour; nothing done is repeated."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import config, pipeline, rights, sources  # noqa: E402

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
TEAMS = [("Denver Nuggets", "Los Angeles Lakers"), ("Oklahoma City Thunder", "Houston Rockets"), ("Miami Heat", "Orlando Magic"),
         ("Atlanta Hawks", "Boston Celtics"), ("Phoenix Suns", "Utah Jazz"), ("Dallas Mavericks", "San Antonio Spurs"),
         ("Chicago Bulls", "New York Knicks"), ("Toronto Raptors", "Brooklyn Nets")]


def vid(i, title=None, views=None):
    a, b = TEAMS[i % len(TEAMS)]
    t = title or f"{a} vs {b} Full Game Highlights - October {20 - i}, 2026"
    return sources.Video(f"id{i}", t, NOW - timedelta(days=i), url=f"https://www.youtube.com/watch?v=id{i}",
                         group="Videos", duration=3000, views=views)


def make_pl(words=()):
    tmp = tempfile.mkdtemp()
    c = config.load(os.path.join(tmp, "none.json"))
    c["hold_words"] = list(words)
    c["sources"] = [{"name": "A", "kind": "youtube", "location": "UCa", "licensed": True, "license_note": "mine", "enabled": True}]
    c["scan_only"] = ["A"]
    with mock.patch.object(config, "HOME", tmp):
        return pipeline.Pipeline(c, lambda m: None)


SRC = rights.Source("A", "youtube", "UCa", True, "mine")


class ScanView(unittest.TestCase):
    def test_newest_five_green_rest_old_with_shorts_and_noise_left_out(self):
        pl = make_pl()
        vids = [vid(0), vid(1, "Funny moment #shorts"), vid(2), vid(3), vid(4), vid(5), vid(6), vid(7), vid(8, "Random vlog about my day")]
        new, held, old = pl.scan_view(SRC, 5, vids=vids)
        self.assertEqual([v.id for v in new], ["id0", "id2", "id3", "id4", "id5"])
        self.assertEqual([v.id for v in old], ["id6", "id7"])
        self.assertEqual(held, [])

    def test_done_videos_are_old_and_never_green(self):
        pl = make_pl()
        pl.db.set("A", "id0", "x", "done")
        new, _h, old = pl.scan_view(SRC, 5, vids=[vid(i) for i in range(4)])
        self.assertEqual([v.id for v in new], ["id1", "id2", "id3"])
        self.assertEqual([(v.id, v.state) for v in old], [("id0", "done")])

    def test_scan_now_treats_baseline_as_clippable_but_24_7_as_old(self):
        pl = make_pl()
        for i in range(3):
            pl.db.set("A", f"id{i}", "x", "baseline")
        vids = [vid(i) for i in range(3)]
        self.assertEqual(len(pl.scan_view(SRC, 5, baseline_is_old=False, vids=vids)[0]), 3)
        self.assertEqual(len(pl.scan_view(SRC, 5, baseline_is_old=True, vids=list(vids))[0]), 0)

    def test_hold_words_go_red_and_do_not_use_up_the_five(self):
        pl = make_pl(["Lakers"])
        new, held, old = pl.scan_view(SRC, 2, vids=[vid(i) for i in range(5)])
        self.assertEqual([v.id for v in held], ["id0"])
        self.assertEqual([v.id for v in new], ["id1", "id2"])
        self.assertEqual([v.id for v in old], ["id3", "id4"])

    def test_24_7_sends_old_posts_to_the_list_too(self):
        pl = make_pl()
        pl.db.set("A", "base", "x", "baseline")
        got = []
        pl.on_scanned = lambda n, h, o=(): got.append(([v.id for v in n], [v.id for v in o]))
        vids = [vid(i) for i in range(8)]
        for v in vids[5:]:
            pl.db.set("A", v.id, v.title, "done")
        with mock.patch.object(sources, "list_recent", return_value=vids), mock.patch.object(pl, "process", return_value={}):
            pl.scan_once()
        self.assertEqual(got[0][0], ["id0", "id1", "id2", "id3", "id4"])
        self.assertTrue({"id5", "id6", "id7"} <= set(got[0][1]))

    def test_24_7_never_uploads_a_video_already_done(self):
        pl = make_pl()
        pl.db.set("A", "id0", "x", "done")
        with mock.patch.object(pipeline.sources, "fetch", side_effect=RuntimeError("downloaded")):
            r = pl.process(SRC, vid(0), enforce=True)
        self.assertEqual(r, {"skipped": "already done"})


class ViewsAndDates(unittest.TestCase):
    def test_feed_views_are_read(self):
        feed = ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
                'xmlns:media="http://search.yahoo.com/mrss/"><entry><yt:videoId>abc</yt:videoId><title>T</title>'
                '<published>2026-10-16T00:00:00+00:00</published><media:group><media:community>'
                '<media:statistics views="123456"/></media:community></media:group></entry></feed>')
        with mock.patch.object(sources.urllib.request, "urlopen") as u, mock.patch.object(sources, "_channel_id", return_value="UC1"):
            u.return_value.read.return_value = feed.encode()
            v = sources.list_videos(SRC, 15)[0]
        self.assertEqual(v.views, 123456)

    def test_flat_listing_keeps_view_count(self):
        v = sources.parse_flat({"entries": [{"id": "x1", "title": "t", "view_count": 250000, "timestamp": 1760000000}]}, "Videos")[0]
        self.assertEqual(v.views, 250000)

    def test_list_recent_merges_feed_and_tab_newest_first(self):
        feed = [vid(1, views=500)]
        tab = [sources.Video("id1", "x", NOW, views=900), vid(2, views=150000)]
        with mock.patch.object(sources, "list_videos", return_value=feed), mock.patch.object(sources, "_channel_id", return_value="UC1"), \
             mock.patch.object(sources, "_flat", return_value={}), mock.patch.object(sources, "parse_flat", return_value=tab):
            out = sources.list_recent(SRC, 50)
        self.assertEqual([v.id for v in out], ["id1", "id2"])
        self.assertEqual(out[0].views, 500)          # the feed's number is kept


if __name__ == "__main__":
    unittest.main()
