import datetime, unittest
from unittest import mock
from sportsclipper import sources

V = sources.Video
NOW = datetime.datetime.now()
UA, UB = "UC" + "a" * 22, "UC" + "b" * 22


def src(name, loc, kind="youtube"):
    return {"name": name, "kind": kind, "location": loc, "licensed": True, "license_note": "x", "enabled": True}


class OwnerTests(unittest.TestCase):
    def test_id_match(self):
        mine = src("Mine", f"https://www.youtube.com/channel/{UA}")
        self.assertEqual(sources.owner_source(V("a", "t", NOW, channel_id=UA), [mine]), mine)

    def test_listed_from_my_channel_without_a_matching_id(self):
        mine = src("Mine", "https://www.youtube.com/@mine")          # handle only, no UC id to compare
        v = V("a", "t", NOW, channel_id=UA, src_name="Mine")
        self.assertEqual(sources.owner_source(v, [mine]), mine)

    def test_channel_name_match(self):
        mine = src("Hoops TV", "https://www.youtube.com/@hoops")
        v = V("a", "t", NOW, channel_id=UA, channel_name="hoops  tv")
        self.assertEqual(sources.owner_source(v, [mine]), mine)

    def test_playlist_source(self):
        pl = src("Playlist: Best", "playlist:PLxxxxxxxxxxxx")
        v = V("a", "t", NOW, group="Playlist: Best", channel_id=UB, src_name="Playlist: Best")
        self.assertEqual(sources.owner_source(v, [pl]), pl)

    def test_foreign_video_still_asks(self):
        mine = src("Mine", f"https://www.youtube.com/channel/{UA}")
        v = V("a", "t", NOW, channel_id=UB, src_name="Mine", channel_name="Other")
        self.assertIsNone(sources.owner_source(v, [mine]))
        self.assertIn("Other", sources.why_not_owned(v))

    def test_one_click_add_builds_a_licensed_channel(self):
        v = V("a", "t", NOW, channel_id=UB, channel_name="Other")
        d = sources.source_for_video(v, "note")
        self.assertTrue(d["licensed"] and d["license_note"])
        self.assertEqual(sources.owner_source(v, [d]), d)
        with self.assertRaises(ValueError):
            sources.source_for_video(V("a", "t", NOW), "note")

    def test_parse_flat_keeps_channel_name(self):
        v = sources.parse_flat({"entries": [{"id": "x1", "title": "t", "channel_id": UA, "channel": "Mine"}]})[0]
        self.assertEqual(v.channel_name, "Mine")


if __name__ == "__main__":
    unittest.main()
