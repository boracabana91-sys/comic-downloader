"""0.9.1: full channel/playlist listing, playlist links, config migration, codec in the probe."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sportsclipper import config, media, rights, sources  # noqa: E402
from sportsclipper.selfcheck import make_video  # noqa: E402

FLAT_VIDEOS = {"entries": [
    {"id": "aaaaaaaaaaa", "title": "DEN vs LAC - October 14, 2026", "timestamp": 1792000000},
    {"id": "bbbbbbbbbbb", "title": "Older game", "upload_date": "20261001"},
    {"id": "ccccccccccc", "title": "No date given"},
    {"id": "PLxxxxxxxxxxxx", "title": "A playlist row", "ie_key": "YoutubeTab", "url": "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxx"},
    None,
]}
FLAT_PLAYLISTS = {"entries": [
    {"id": "PLabcdefghijkl", "title": "Season 2026-27", "ie_key": "YoutubeTab"},
    {"id": "notaplaylist", "title": "ignore me"},
]}


class V091(unittest.TestCase):
    def test_parse_flat_rows(self):
        v = sources.parse_flat(FLAT_VIDEOS, "Videos")
        self.assertEqual([x.id for x in v], ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"])   # playlist row and None skipped
        self.assertEqual([x.dated for x in v], [True, True, False])
        self.assertEqual(v[1].published.strftime("%Y-%m-%d"), "2026-10-01")
        self.assertTrue(all(x.group == "Videos" and x.url.endswith(x.id) for x in v))

    def test_parse_playlists(self):
        self.assertEqual(sources.parse_playlists(FLAT_PLAYLISTS), [("PLabcdefghijkl", "Season 2026-27")])

    def test_list_all_groups_like_the_channel(self):
        src = rights.Source("Chan", "youtube", "UC" + "a" * 22, True, "test")

        def fake(url, **kw):
            if url.endswith("/videos"):
                return FLAT_VIDEOS
            if url.endswith("/streams") or url.endswith("/shorts"):
                return {"entries": []}
            if url.endswith("/playlists"):
                return FLAT_PLAYLISTS
            if "playlist?list=PLabcdefghijkl" in url:
                return {"entries": [{"id": "aaaaaaaaaaa", "title": "DEN vs LAC - October 14, 2026"}]}
            raise AssertionError(url)
        with mock.patch.object(sources, "_flat", fake):
            out = sources.list_all(src, log=lambda *_: None)
        groups = [v.group for v in out]
        self.assertEqual(groups, ["Videos"] * 3 + ["Playlist: Season 2026-27"])

    def test_playlist_link_is_scanned_directly(self):
        with mock.patch.object(sources, "_flat", lambda url, **kw: {"title": "My Playlist"}):
            r = sources.resolve_youtube("https://www.youtube.com/playlist?list=PLabcdefghijklmn")
        self.assertEqual(r, {"name": "Playlist: My Playlist", "kind": "youtube", "location": "playlist:PLabcdefghijklmn"})
        src = rights.Source(r["name"], "youtube", r["location"], True, "x")
        seen = {}

        def fake(url, **kw):
            seen["url"] = url
            return FLAT_VIDEOS
        with mock.patch.object(sources, "_flat", fake):
            vids = sources.list_all(src, log=lambda *_: None)
        self.assertIn("playlist?list=PLabcdefghijklmn", seen["url"])
        self.assertEqual(len(vids), 3)

    def test_old_config_loses_4k_and_slow_encoder(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            json.dump({"config_version": 9, "resolutions": [2160, 1080, 720], "encoder": "libx264"}, open(p, "w"))
            c = config.load(p)
            self.assertEqual(c["resolutions"], [1080, 720])
            self.assertEqual(c["config_version"], 10)
            json.dump({"config_version": 10, "resolutions": [2160, 1080]}, open(p, "w"))
            self.assertEqual(config.load(p)["resolutions"], [2160, 1080])      # ticked again on purpose: kept

    def test_probe_reports_codec(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "t.mp4")
            make_video(v, secs=4)
            self.assertEqual(media.probe(v)["codec"], "h264")


if __name__ == "__main__":
    unittest.main()
