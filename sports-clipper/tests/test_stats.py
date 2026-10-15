import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sportsclipper import stats

FIXTURE = {
    "header": {"id": "401", "competitions": [{"competitors": [
        {"homeAway": "home", "score": "118", "team": {"abbreviation": "DEN"}},
        {"homeAway": "away", "score": "112", "team": {"abbreviation": "LAC"}}]}]},
    "boxscore": {"players": [
        {"team": {"abbreviation": "DEN"}, "statistics": [{"labels": ["MIN", "PTS", "REB", "AST"], "athletes": [
            {"athlete": {"displayName": "Nikola Jokic"}, "stats": ["34", "34", "12", "9"]},
            {"athlete": {"displayName": "Jamal Murray"}, "stats": ["30", "21", "4", "6"]}]}]},
        {"team": {"abbreviation": "LAC"}, "statistics": [{"labels": ["MIN", "PTS", "REB", "AST"], "athletes": [
            {"athlete": {"displayName": "Kawhi Leonard"}, "stats": ["36", "28", "6", "3"]}]}]}]}}

class StatsTests(unittest.TestCase):
    def test_parse(self):
        g = stats.parse_summary(FIXTURE)
        self.assertEqual((g.home, g.home_score, g.away, g.away_score), ("DEN", 118, "LAC", 112))
        self.assertEqual(g.leaders["DEN"].last, "JOKIC")
        self.assertEqual(g.leaders["DEN"].pts, 34)
        self.assertEqual(g.leaders["LAC"].last, "LEONARD")

    def test_unavailable_returns_none(self):
        self.assertIsNone(stats.game_info("20200101", ["DEN", "LAC"]))   # no network here: must not raise

if __name__ == "__main__":
    unittest.main()
