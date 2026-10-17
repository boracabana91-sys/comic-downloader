"""vv28: hold words, held list, red/green scan results, one teaser line, 5 per scan."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import captions, config, metadata, pipeline, rules, sources  # noqa: E402

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)


def make_pl(words, n=5):
    tmp = tempfile.mkdtemp()
    c = config.load(os.path.join(tmp, "none.json"))
    c["ai"]["enabled"] = False
    c["hold_words"] = words; c["videos_per_scan"] = n
    c["sources"] = [{"name": "A", "kind": "youtube", "location": "UCa", "licensed": True, "license_note": "mine", "enabled": True}]
    c["scan_only"] = ["A"]
    with mock.patch.object(config, "HOME", tmp):
        pl = pipeline.Pipeline(c, lambda m: None)
    return pl


def vid(i, title):
    return sources.Video(f"id{i}", title, NOW, url=f"https://www.youtube.com/watch?v=id{i}", group="Videos", duration=3000)


VIDS = [vid(1, "Denver Nuggets vs Los Angeles Lakers Full Game Highlights - October 16, 2026"),
        vid(2, "Oklahoma City Thunder vs Houston Rockets Full Game Highlights - October 15, 2026"),
        vid(3, "LA Clippers vs Phoenix Suns Full Game Highlights - October 14, 2026"),
        vid(4, "Atlanta Hawks vs Boston Celtics Full Game Highlights - October 13, 2026"),
        vid(5, "Miami Heat vs Orlando Magic Full Game Highlights - October 12, 2026")]


class HoldWords(unittest.TestCase):
    def test_parse_and_match_whole_words(self):
        self.assertEqual(rules.parse_hold_words("Lakers, LA\nSpurs;  "), ["Lakers", "LA", "Spurs"])
        w = ["Lakers", "LA"]
        self.assertEqual(rules.hold_match(VIDS[0].title, w), "Lakers")
        self.assertEqual(rules.hold_match(VIDS[2].title, w), "LA")
        self.assertEqual(rules.hold_match(VIDS[3].title, w), "")             # 'Atlanta' does not contain the word LA
        self.assertEqual(rules.hold_match("denver nuggets vs los angeles LAKERS", w), "Lakers")
        self.assertEqual(rules.hold_match(VIDS[0].title, []), "")

    def test_scan_preview_splits_good_and_held_and_remembers_held(self):
        pl = make_pl(["Lakers", "LA"])
        with mock.patch.object(sources, "list_videos", return_value=VIDS):
            good, held = pl.scan_preview(rights_src(), 5)
        self.assertEqual([v.id for v in good], ["id2", "id4", "id5"])
        self.assertEqual([v.id for v in held], ["id1", "id3"])
        self.assertEqual({r[1] for r in pl.db.held()}, {"id1", "id3"})

    def test_the_limit_counts_only_good_videos(self):
        pl = make_pl(["Lakers", "LA"], n=2)
        with mock.patch.object(sources, "list_videos", return_value=VIDS):
            good, held = pl.scan_preview(rights_src(), 2)
        self.assertEqual(len(good), 2); self.assertEqual(len(held), 2)

    def test_24_7_scan_never_processes_a_held_title(self):
        pl = make_pl(["Lakers", "LA"])
        pl.db.set("A", "base", "x", "baseline")
        done, scanned = [], []
        pl.on_scanned = lambda g, h: scanned.append(([v.id for v in g], [v.id for v in h]))
        with mock.patch.object(sources, "list_videos", return_value=VIDS), \
             mock.patch.object(pl, "process", side_effect=lambda s, v, u=True, enforce=False: done.append(v.id) or {}):
            pl.scan_once()
        self.assertEqual(sorted(done), ["id2", "id4", "id5"])
        self.assertEqual(scanned, [(["id2", "id4", "id5"], ["id1", "id3"])])
        self.assertEqual({r[1] for r in pl.db.held()}, {"id1", "id3"})

    def test_budget_is_five_by_default_and_videos_over_it_wait(self):
        self.assertEqual(config.DEFAULTS["videos_per_scan"], 5)

    def test_a_held_title_can_be_released_and_then_reclipped_by_link(self):
        pl = make_pl(["Lakers"])
        pl.db.set("A", "id1", "t", "hold", "hold word: Lakers")
        self.assertTrue(pl.db.is_held("A", "id1"))
        pl.db.release("A", "id1")
        self.assertEqual(pl.db.held(), [])

    def test_manual_single_link_is_never_held(self):
        pl = make_pl(["Lakers"])
        src = rights_src()
        self.assertEqual(rules.hold_match(VIDS[0].title, ["Lakers"]), "Lakers")
        # process(enforce=False) does not look at hold words: only the scans (enforce=True) do
        with mock.patch.object(pipeline.sources, "fetch", side_effect=RuntimeError("reached download")):
            with self.assertRaises(RuntimeError):
                pl.process(src, VIDS[0], upload=False)
            r = pl.process(src, VIDS[0], upload=False, enforce=True)
        self.assertEqual(r, {"held_word": "Lakers"})


def rights_src():
    from sportsclipper import rights
    return rights.Source("A", "youtube", "UCa", True, "mine")


class Teaser(unittest.TestCase):
    CUES = [(10.0, ">> and throw it down Zier Williams. Stole"),
            (20.0, ">> He had just one block credited to them."),
            (30.0, "Take away BOUNCE M TO THROW IT DOWN."),
            (40.0, "Oh my! From downtown, bang! Jokic drains the three!"),
            (50.0, "[Music]")]

    def test_clean_units(self):
        self.assertEqual(captions.clean_units(">> and throw it down Zier Williams. Stole"), ["Throw it down Zier Williams."])
        self.assertEqual(captions.clean_units("Take away BOUNCE M TO THROW IT DOWN."), [])           # broken all-caps line
        self.assertEqual(captions.clean_units("[Music]"), [])

    def test_the_single_best_line_is_chosen(self):
        c = captions.candidates(self.CUES)
        self.assertTrue(c[0].startswith("Oh my! From downtown"), c)
        self.assertNotIn(">>", " ".join(c))

    def test_description_has_exactly_one_line(self):
        cfg = config.load(os.path.join(tempfile.mkdtemp(), "none.json")); cfg["ai"]["enabled"] = False
        m = metadata.build(cfg, "Denver Nuggets vs Los Angeles Lakers Full Game Highlights", "A", 600, lambda m: None,
                           captions=self.CUES, published=NOW)
        self.assertEqual(m["description"].count("“"), 1)
        self.assertTrue(m["description"].startswith(metadata.DISCLAIMER))
        self.assertIn("Subscribe for every game's highlights.", m["description"])


class Gone(unittest.TestCase):
    def test_the_claim_marker_is_removed_from_old_settings(self):
        import json
        p = os.path.join(tempfile.mkdtemp(), "c.json")
        json.dump({"config_version": 11, "claim_risk_sources": ["GAMETIME HIGHLIGHTS"], "videos_per_scan": 3}, open(p, "w"))
        c = config.load(p)
        self.assertNotIn("claim_risk_sources", c)
        self.assertEqual(c["videos_per_scan"], 5)


if __name__ == "__main__":
    unittest.main()
