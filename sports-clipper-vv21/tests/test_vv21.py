"""vv21: close-up thumbnail, three AI writers, description with fair-use text and commentary lines."""
import os
import sys
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import captions, config, metadata, roster, thumbnail  # noqa: E402


def cfg():
    c = config.load("/nonexistent.json")
    c["ai"]["api_key"] = "k"
    return c


CUES = [(10.0, "Jokic from downtown, bang!"), (20.0, "and they inbound the ball"), (30.0, "What a poster dunk by Bam!"),
        (500.0, "Cold-blooded dagger at the buzzer!")]


class Thumb(unittest.TestCase):
    def test_closeup_is_the_default_and_makes_a_full_size_picture(self):
        thumbnail.set_layout("closeup")
        rgb = thumbnail.preview_rgb("DEN vs MIA FLASHY HIGHLIGHTS October 17, 2026")
        self.assertEqual(rgb.shape, (1080, 1920, 3))

    def test_old_layout_still_available(self):
        thumbnail.set_layout("stars")
        try:
            self.assertEqual(thumbnail.preview_rgb("DEN vs MIA").shape, (1080, 1920, 3))
        finally:
            thumbnail.set_layout("closeup")

    def test_headline_word_follows_the_title(self):
        self.assertEqual(thumbnail.word_of("A VS B - FLASHY HIGHLIGHTS"), "FLASHY")
        self.assertEqual(thumbnail.word_of("A VS B - GREAT HIGHLIGHTS"), "GREAT")
        self.assertEqual(thumbnail.word_of("A vs B"), "FULL GAME")

    def test_head_picture_prefers_the_matching_close_up(self):
        png = roster.find_star("ATL")[0]
        self.assertTrue(os.path.exists(thumbnail.head_picture(png)))


class Title(unittest.TestCase):
    def test_format(self):
        self.assertEqual(metadata.make_title(["Denver Nuggets", "Miami Heat"], "FLASHY", "October 17, 2026", "x"),
                         "Denver Nuggets VS Miami Heat - FLASHY HIGHLIGHTS - October 17, 2026")

    def test_date_from_a_short_month(self):
        self.assertEqual(metadata.game_date("NUGGETS at HEAT Oct 17, 2026"), "October 17, 2026")
        self.assertEqual(metadata.game_date("no date here", datetime(2026, 10, 5)), "October 5, 2026")


class Captions(unittest.TestCase):
    def test_only_exciting_lines_in_the_kept_parts(self):
        got = captions.candidates(CUES, segments=[[0, 100]])
        self.assertEqual(len(got), 2)
        self.assertNotIn("inbound", " ".join(got))
        self.assertNotIn("dagger", " ".join(got))              # at 500 s: cut out of the video

    def test_json3(self):
        d = {"events": [{"tStartMs": 1500, "segs": [{"utf8": "Oh "}, {"utf8": "my!"}]}, {"tStartMs": 3, "segs": [{"utf8": "\n"}]}]}
        self.assertEqual(captions.parse_json3(d), [(1.5, "Oh my!")])


class Writers(unittest.TestCase):
    def run_build(self, answers, caps=CUES):
        calls = []
        def fake(c, prompt, max_tokens=700):
            calls.append(prompt)
            if "SEO writer" in prompt:
                return answers["seo"]
            return answers["fans" if "die-hard" in prompt else "reach"]
        with mock.patch.object(metadata, "_ask", side_effect=fake):
            out = metadata.build(cfg(), "Denver Nuggets vs Miami Heat | October 17, 2026", "ch", 600, lambda m: None,
                                 captions=caps, published=datetime(2026, 10, 17))
        return out, calls

    def test_three_writers_and_the_description(self):
        out, calls = self.run_build({
            "seo": {"word": "FLASHY", "why": "stars", "teasers": ["Jokic from downtown, bang!", "invented line"]},
            "fans": {"tags": ["Nuggets fans", "Heat Culture"], "hashtags": ["MileHighBasketball"]},
            "reach": {"tags": ["NBA highlights", "basketball"], "hashtags": ["NBA", "Hoops"]}})
        self.assertEqual(len(calls), 3)
        self.assertEqual(out["title"], "Denver Nuggets VS Miami Heat - FLASHY HIGHLIGHTS - October 17, 2026")
        self.assertTrue(out["description"].startswith("This video was edited to follow youtube's fair use guidelines"))
        self.assertIn("Jokic from downtown, bang!", out["description"])
        self.assertNotIn("invented line", out["description"])          # only real commentary is quoted
        self.assertIn("#NBA", out["description"])
        self.assertIn("Heat Culture", out["tags"])

    def test_no_captions_means_no_quote_lines(self):
        out, _ = self.run_build({"seo": {"word": "GREAT", "teasers": ["made up"]}, "fans": {}, "reach": {}}, caps=[])
        self.assertNotIn("made up", out["description"])
        self.assertIn("GREAT HIGHLIGHTS", out["title"])

    def test_a_failed_writer_does_not_stop_the_rest(self):
        def fake(c, prompt, max_tokens=700):
            if "die-hard" in prompt:
                raise RuntimeError("boom")
            return {"word": "GREAT", "tags": ["x"], "hashtags": ["y"], "teasers": []}
        with mock.patch.object(metadata, "_ask", side_effect=fake):
            out = metadata.build(cfg(), "Denver Nuggets vs Miami Heat October 17, 2026", "ch", 600, lambda m: None)
        self.assertIn("HIGHLIGHTS", out["title"])

    def test_no_key_gives_plain_titles(self):
        c = cfg(); c["ai"]["api_key"] = ""
        with mock.patch.dict(os.environ, {}, clear=True):
            out = metadata.build(c, "Denver Nuggets vs Miami Heat October 17, 2026", "ch", 600, lambda m: None)
        self.assertTrue(out["description"].startswith("This video was edited"))

    def test_tags_stay_under_youtube_limits(self):
        tags = metadata.tag_list([f"tag number {i}" for i in range(200)])
        self.assertLessEqual(sum(len(t) + 1 for t in tags), 500)
        self.assertEqual(metadata.hashtags(["#NBA", "nba", "Bad Tag!"]), ["#NBA", "#BadTag"])


if __name__ == "__main__":
    unittest.main()
