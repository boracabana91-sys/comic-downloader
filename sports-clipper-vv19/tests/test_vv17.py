"""vv17: a link to one video in the search bar."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import sources  # noqa: E402

ID = "dQw4w9WgXcQ"


class VideoLink(unittest.TestCase):
    def test_link_forms(self):
        for u in (f"https://www.youtube.com/watch?v={ID}", f"https://youtu.be/{ID}", f"https://youtu.be/{ID}?si=abc",
                  f"https://www.youtube.com/shorts/{ID}", f"https://www.youtube.com/live/{ID}?feature=share",
                  f"https://m.youtube.com/watch?feature=share&v={ID}", f"https://www.youtube.com/embed/{ID}",
                  f"  https://www.youtube.com/watch?v={ID}&t=30s  "):
            self.assertEqual(sources.video_id(u), ID, u)

    def test_a_video_inside_a_playlist_link_is_that_video(self):
        self.assertEqual(sources.video_id(f"https://www.youtube.com/watch?v={ID}&list=PLabcdefghijklmn&index=2"), ID)

    def test_not_a_video_link(self):
        for t in ("", "DEN vs LAC", "highlights", "https://www.youtube.com/playlist?list=PLabcdefghijklmn",
                  "https://www.youtube.com/@Channel", ID, "https://example.com/watch?v=" + ID):
            self.assertEqual(sources.video_id(t), "", t)

    def test_fetch_video_makes_one_row(self):
        info = {"id": ID, "title": "DEN vs LAC full game", "timestamp": 1760000000, "channel_id": "UC" + "a" * 22}
        with mock.patch.object(sources, "_flat", return_value=info) as fl:
            vids = sources.fetch_video(f"https://youtu.be/{ID}")
        self.assertEqual(len(vids), 1)
        v = vids[0]
        self.assertEqual((v.id, v.title, v.group, v.dated, v.channel_id), (ID, "DEN vs LAC full game", "Single video", True, "UC" + "a" * 22))
        self.assertEqual(v.url, f"https://www.youtube.com/watch?v={ID}")
        self.assertTrue(fl.call_args.kwargs.get("noplaylist"))      # never the whole playlist

    def test_unreadable_video_is_a_clear_error(self):
        with mock.patch.object(sources, "_flat", return_value=None):
            with self.assertRaises(ValueError):
                sources.fetch_video(f"https://youtu.be/{ID}")
        with self.assertRaises(ValueError):
            sources.fetch_video("not a link")

    def test_rights_gate_still_applies(self):
        info = {"id": ID, "title": "x", "timestamp": 1760000000, "channel_id": "UC" + "b" * 22}
        with mock.patch.object(sources, "_flat", return_value=info):
            v = sources.fetch_video(f"https://youtu.be/{ID}")[0]
        mine = {"kind": "youtube", "location": "https://www.youtube.com/channel/UC" + "a" * 22, "name": "A"}
        self.assertIsNone(sources.owner_source(v, [mine]))          # a video of an unlisted channel is refused
        theirs = {"kind": "youtube", "location": "https://www.youtube.com/channel/UC" + "b" * 22, "name": "B"}
        self.assertEqual(sources.owner_source(v, [mine, theirs]), theirs)


if __name__ == "__main__":
    unittest.main()
