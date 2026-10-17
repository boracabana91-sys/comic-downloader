"""vv26: free-mode hashtags (lowercase, brand first), the Gametime stats card is cut, the game ends at the final score, claim-risk sources wait for OK."""
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import analyze, config, metadata, pipeline, post, rights, rules, sources  # noqa: E402

TITLE = "Oklahoma City Thunder vs Houston Rockets FULL GAME HIGHLIGHTS | October 15, 2026"
BRAND = ["#nbahighlights", "#nba", "#gametimehighlights", "#emberhoops"]


def cfg():
    c = config.load(os.path.join(tempfile.mkdtemp(), "none.json"))
    c["ai"]["enabled"] = False
    return c


class Hashtags(unittest.TestCase):
    def test_brand_first_lowercase_max_15(self):
        c = cfg()
        m = metadata.build(c, TITLE, "A", 600, lambda m: None, captions=[], published=datetime(2026, 10, 15))
        tags = re.findall(r"#\w+", m["description"])
        self.assertEqual(tags[:4], BRAND)
        self.assertTrue(all(t == t.lower() for t in tags))
        self.assertLessEqual(len(tags), 15)
        self.assertIn("#thunder", tags); self.assertIn("#rockets", tags)

    def test_other_description_parts_are_kept(self):
        c = cfg()
        cues = [(10.0, "Oh my! From downtown, bang!"), (20.0, "What a block by the big man!")]
        m = metadata.build(c, TITLE, "A", 600, lambda m: None, captions=cues, published=datetime(2026, 10, 15))
        d = m["description"]
        self.assertTrue(d.startswith(metadata.DISCLAIMER))
        self.assertIn("Subscribe for every game's highlights.", d)
        self.assertIn("From downtown", d)
        self.assertRegex(d.strip().splitlines()[-1], r"^#\w+")

    def test_no_key_uses_free_mode_even_with_ai_on(self):
        c = cfg(); c["ai"]["enabled"] = True; c["ai"]["api_key"] = ""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(c["ai"]["api_key_env"], None)
            m = metadata.build(c, TITLE, "A", 600, lambda m: None, captions=[], published=datetime(2026, 10, 15))
        self.assertTrue(m["description"].count("#") >= 8)

    def test_preview_shows_the_hashtags_before_the_download(self):
        pp = post.preview_post(cfg(), TITLE, datetime(2026, 10, 15, tzinfo=timezone.utc), "A")
        self.assertEqual(re.findall(r"#\w+", pp["meta"]["description"])[:4], BRAND)

    def test_rules_require_the_channel_hashtags(self):
        c = cfg()
        pp = post.preview_post(c, TITLE, datetime(2026, 10, 15, tzinfo=timezone.utc), "A")
        f = pp["stem"] + "_1080p.mp4"
        self.assertEqual(rules.failed(rules.check(pp["meta"], f, pp["teams"], TITLE, c, pending=True)), [])
        bad = dict(pp["meta"], description=metadata.DISCLAIMER + "\n\n#nba")
        self.assertTrue(any("hashtags" in x for x in rules.failed(rules.check(bad, f, pp["teams"], TITLE, c, pending=True))))
        upper = dict(pp["meta"], description=pp["meta"]["description"] + " #NBAHighlights")
        self.assertTrue(rules.failed(rules.check(upper, f, pp["teams"], TITLE, c, pending=True)))


def card_frames(n_card=6, n_play=10, h=72, w=128):
    rng = np.random.default_rng(1)
    play = [(rng.integers(60, 200, (h, w))).astype(np.uint8) for _ in range(n_play)]
    card = []
    for _ in range(n_card):
        f = np.full((h, w), 14, np.uint8)
        f[10:62, 6:56] = rng.integers(8, 20, (52, 50))
        for r in range(12, 60, 4):                       # rows of text packed on the left
            f[r:r + 2, 8:54] = 190
        card.append(f)
    return np.stack(play + card + play)


class Card(unittest.TestCase):
    def test_stats_card_found_and_play_is_not(self):
        th = card_frames()
        m = analyze.gametime_card(th)
        self.assertTrue(m[10:16].all())
        self.assertFalse(m[:10].any() or m[16:].any())

    def test_cut_removes_it_from_the_clip(self):
        th = card_frames()
        live = np.ones(len(th), bool)
        cut = analyze._cut_runs(live, analyze.gametime_card(th))
        self.assertGreaterEqual(cut, 6)
        self.assertFalse(live[10:16].any())
        self.assertTrue(live[:9].all() and live[17:].all())

    def test_a_one_second_flash_is_not_cut(self):
        live = np.ones(30, bool); mask = np.zeros(30, bool); mask[10] = True
        self.assertEqual(analyze._cut_runs(live, mask), 0)


class GameEnd(unittest.TestCase):
    def test_end_pad_is_short_so_no_end_credits(self):
        self.assertLessEqual(analyze.END_PAD_S, 5)

    def test_overtime_stays_in(self):
        runs = [[0, 1500], [1560, 2900], [2960, 3300]]          # the clock runs again after regulation: that is overtime
        self.assertEqual(analyze.game_end(runs), 3300.0)


class ClaimRisk(unittest.TestCase):
    def _run(self, c):
        tmp = tempfile.mkdtemp(); c["output_dir"] = tmp; c["work_dir"] = tmp
        c["upload"]["enabled"] = True; c["thumbnail"]["enabled"] = False
        with mock.patch.object(config, "HOME", tmp):
            pl = pipeline.Pipeline(c, lambda m: None)
        src = rights.Source("A", "youtube", "UCa", True, "mine")
        v = sources.Video("g1", TITLE, datetime(2026, 10, 15, tzinfo=timezone.utc), url="https://youtu.be/xxxxxxxxxxx")
        info = {"height": 1080, "width": 1920, "duration": 3000, "has_audio": True, "codec": "h264"}

        def fake_render(path, segs, info_in, cfg_, out_base, log=print, only=None, intro=None):
            os.makedirs(os.path.dirname(out_base), exist_ok=True)
            outs = {h: out_base + f"_{h}p.mp4" for h in (only or [1080])}
            for p in outs.values():
                open(p, "wb").write(b"x")
            return outs
        up = mock.Mock(return_value="vid123")
        with mock.patch.object(pipeline.sources, "fetch", return_value="/x.mp4"), mock.patch.object(pipeline.media, "probe", return_value=info), \
             mock.patch.object(pipeline.captions, "fetch", return_value=[]), \
             mock.patch.object(pipeline.analyze, "plan", return_value={"segments": [[0, 600]], "kept_s": 600.0}), \
             mock.patch.object(pipeline.render, "render", side_effect=fake_render), mock.patch.object(pipeline.finish, "intro_picture", return_value=None), \
             mock.patch.object(pipeline.finish, "make_thumb", return_value=None), mock.patch.object(pipeline.finish, "add_cover"), \
             mock.patch.object(pipeline.uploader, "upload_youtube", up), mock.patch.object(pl, "_render_rest"):
            r = pl.process(src, v)
        return r, up

    def test_a_normal_source_uploads(self):
        r, up = self._run(cfg())
        self.assertTrue(up.called, r.get("held"))

    def test_a_source_with_a_claim_before_waits_for_ok(self):
        c = cfg(); c["claim_risk_sources"] = ["A"]
        r, up = self._run(c)
        self.assertFalse(up.called)
        self.assertTrue(r["needs_ok"] and r["source_name"] == "A")
        self.assertFalse(r.get("youtube_id"))

    def test_private_is_never_scheduled_public(self):
        c = cfg(); c["upload"]["privacy"] = "private"
        r, up = self._run(c)
        self.assertIsNone(up.call_args[0][3])                  # publish_at is None


if __name__ == "__main__":
    unittest.main()
