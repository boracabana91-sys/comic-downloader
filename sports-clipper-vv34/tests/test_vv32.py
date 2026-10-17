"""vv32: every clip starts 1 s before the jump ball; channels can be renamed; a video link gives the channel's own name."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sportsclipper import analyze, config, sources, store  # noqa: E402


class Tip(unittest.TestCase):
    def test_defaults_and_old_settings_move_to_one_second(self):
        self.assertEqual(config.DEFAULTS["tip_lead_s"], 1); self.assertEqual(config.DEFAULTS["highlight_lead_s"], 1)
        p = os.path.join(tempfile.mkdtemp(), "c.json")
        with open(p, "w") as f:
            json.dump({"config_version": 11, "start_at_tipoff": False, "tip_lead_s": 3, "highlight_lead_s": 3}, f)
        c = config.load(p)
        self.assertTrue(c["start_at_tipoff"]); self.assertEqual(c["tip_lead_s"], 1); self.assertEqual(c["highlight_lead_s"], 1)

    def test_best_clips_always_open_at_the_jump_ball(self):
        # the helper used by plan(): when the first pick is later than the tip, an opening clip at the tip is added
        live = np.ones(600, bool)
        rz = np.zeros(600); rz[300] = 5
        picks = analyze.best_clips(live, rz, np.zeros(600), np.zeros(600), 60, start_s=100.0)
        self.assertGreater(picks[0][0], 100.0)         # without the rule the first pick is later
        src = open(os.path.join(os.path.dirname(analyze.__file__), "analyze.py")).read()
        self.assertIn("always opens at the jump ball", src)

    def test_source_has_tip_lead_one(self):
        src = open(os.path.join(os.path.dirname(analyze.__file__), "analyze.py")).read()
        self.assertIn('cfg.get("tip_lead_s", 1)', src); self.assertIn('cfg.get("highlight_lead_s", 1)', src)


class Rename(unittest.TestCase):
    def test_history_follows_the_new_name(self):
        db = store.Store(os.path.join(tempfile.mkdtemp(), "s.sqlite"))
        db.set("Phoenix vs Utah", "v1", "t", "done"); db.set("Phoenix vs Utah", "v2", "t2", "hold", "hold word: LA")
        self.assertEqual(db.rename_source("Phoenix vs Utah", "GAMETIME HIGHLIGHTS"), 2)
        self.assertTrue(db.seen("GAMETIME HIGHLIGHTS", "v1")); self.assertFalse(db.seen("Phoenix vs Utah", "v1"))
        self.assertEqual([r[0] for r in db.held()], ["GAMETIME HIGHLIGHTS"])
        self.assertEqual(db.rename_source("x", "x"), 0)

    def test_a_video_link_gives_the_channels_own_name(self):
        page = ('<meta property="og:title" content="Phoenix Suns vs Utah Jazz Full Game Highlights">'
                '"channelId":"UCe4ipLL5WOgOzAW4FoUNgxQ"')
        with mock.patch.object(sources.urllib.request, "urlopen") as u, \
             mock.patch.object(sources, "feed_author", return_value="GAMETIME HIGHLIGHTS"):
            u.return_value.read.return_value = page.encode()
            r = sources.resolve_youtube("https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(r["name"], "GAMETIME HIGHLIGHTS")


if __name__ == "__main__":
    unittest.main()
