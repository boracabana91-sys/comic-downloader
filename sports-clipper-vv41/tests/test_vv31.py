"""vv31: a channel link resolves to the channel's OWN id (not a featured/related channel on the page)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sportsclipper import sources  # noqa: E402
import test_vv29 as t29  # noqa: E402

WRONG = "UCe4ipLL5WOgOzAW4FoUNgxQ"
RIGHT = "UCrightRIGHTrightRIGHT12"
PAGE = ('<html><head><meta property="og:title" content="GAMETIME HIGHLIGHTS">'
        f'<link rel="canonical" href="https://www.youtube.com/channel/{RIGHT}"></head><body>'
        f'{{"featured":{{"channelId":"{WRONG}"}}}} {{"externalId":"{RIGHT}"}}</body></html>')
PAGE_NO_CANON = ('<html><head><meta property="og:title" content="GAMETIME HIGHLIGHTS"></head><body>'
                 f'{{"channelId":"{WRONG}"}} {{"browseId":"{RIGHT}"}}</body></html>')


class Resolve(unittest.TestCase):
    def test_the_pages_own_id_comes_first(self):
        self.assertEqual(sources.parse_channel_html(PAGE)[0], RIGHT)
        self.assertEqual(sources.channel_candidates(PAGE)[0], RIGHT)

    def test_the_id_whose_feed_name_matches_the_page_name_wins(self):
        authors = {WRONG: "Some Football Channel", RIGHT: "GAMETIME HIGHLIGHTS"}
        with mock.patch.object(sources.urllib.request, "urlopen") as u, mock.patch.object(sources, "feed_author", side_effect=lambda c: authors[c]):
            u.return_value.read.return_value = PAGE_NO_CANON.encode()
            r = sources.resolve_youtube("https://www.youtube.com/@GametimeHighlights")
        self.assertEqual(r["location"], RIGHT); self.assertEqual(r["name"], "GAMETIME HIGHLIGHTS")


class Warning(unittest.TestCase):
    def test_wrong_channel_id_is_called_out_in_the_log(self):
        pl = t29.make_pl(); logs = []; pl.log = logs.append
        v = t29.vid(0); v.channel_name = "Some Football Channel"
        src = t29.rights.Source("GAMETIME HIGHLIGHTS", "youtube", WRONG, True, "mine")
        pl.scan_view(src, 5, vids=[v])
        self.assertTrue(any("WARNING" in m and "Some Football Channel" in m for m in logs))

    def test_same_name_gives_no_warning(self):
        pl = t29.make_pl(); logs = []; pl.log = logs.append
        v = t29.vid(0); v.channel_name = "A"
        pl.scan_view(t29.SRC, 5, vids=[v])
        self.assertFalse(any("WARNING" in m for m in logs))


if __name__ == "__main__":
    unittest.main()
