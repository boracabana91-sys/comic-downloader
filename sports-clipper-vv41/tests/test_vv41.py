"""vv41: the closing stats card is cut also when its box score SCROLLS (taller than the screen: the second team's bench and
the TOTALS row come into view). vv40 only knew still cards, so the scrolling seconds before the final still part stayed in."""
import os
import sys
import unittest
from copy import deepcopy
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sportsclipper import analyze, config  # noqa: E402
import test_vv40 as t40  # noqa: E402


def scrolling_card(scroll_s=10, still_s=4, speed=40, fade=True, zoom=1.0, W=1920, H=1080):
    """The card as the app sees it (128x72 grey, averaged down): a fixed header and a tall table (two teams, ~40 rows,
    a highlighted row, TOTALS) scrolling up `speed` px per second for `scroll_s` s, then held still for `still_s` s."""
    import cv2
    f = cv2.FONT_HERSHEY_SIMPLEX
    x0, x1 = int(W * 0.03), int(W * 0.47)
    tall = np.full((2400, W, 3), (22, 15, 15), np.uint8)
    y = 30
    for r in range(56):
        if r == 23:
            cv2.rectangle(tall, (x0, y - 20), (x1, y + 10), (90, 40, 60), -1)      # the highlighted player row
        elif r % 2:
            cv2.rectangle(tall, (x0, y - 20), (x1, y + 10), (34, 26, 26), -1)
        rng = np.random.default_rng(r)
        nums = "  ".join(str(int(x)) for x in rng.integers(0, 40, 11))
        name = ["McGlothan", "DeVries", "Cenac Jr.", "Uzan", "Gray", "Garza", "Gonzalez", "Harper Jr.", "Walsh", "Mitchell"][r % 10]
        text = "TOTALS   -  125  44-108  17-54  20-26  78 31 21" if r in (27, 55) else f"{name:12s} {nums}"
        cv2.putText(tall, text, (x0, y), f, 0.6, (215, 215, 215), 1)
        y += 42
    head = np.full((300, W, 3), (22, 15, 15), np.uint8)
    cv2.putText(head, "GAMETIME HIGHLIGHTS", (x0, 60), f, 1.1, (235, 235, 235), 2)
    cv2.rectangle(head, (int(W * .40), 20), (int(W * .465), 75), (40, 110, 240), -1)
    cv2.putText(head, "Boston Celtics 125     120 Philadelphia 76ers", (x0, 175), f, 1.2, (230, 230, 230), 2)
    out, pos = [], 0
    speeds = [speed] * scroll_s + [0] * still_s
    for k, v in enumerate(speeds):
        img = np.full((H, W, 3), (22, 15, 15), np.uint8)
        img[:300] = head
        img[300:H] = tall[pos:pos + H - 300]
        if fade and k < 2:
            img = (img * (0.35, 0.7)[k]).astype(np.uint8)
        if zoom != 1.0:
            cw, ch = int(W / zoom), int(H / zoom)
            img = cv2.resize(img[(H - ch) // 2:(H + ch) // 2, (W - cw) // 2:(W + cw) // 2], (W, H))
        out.append(cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (128, 72), interpolation=cv2.INTER_AREA))
        pos = min(pos + v, tall.shape[0] - (H - 300))
    return np.stack(out)


class Detector(unittest.TestCase):
    def test_root_cause_scrolling_seconds_are_never_still(self):
        th = scrolling_card()
        self.assertFalse(analyze.still_text_card(th)[:10].any())      # the vv40 still test sees no card while it scrolls
        self.assertTrue(analyze.still_text_card(th)[10:].all())       # only the final still part (from the last scroll step)

    def test_the_whole_scrolling_card_is_found(self):
        for zoom in (1.0, 1.1):
            for speed in (20, 40, 80):
                m = analyze.gametime_card(scrolling_card(speed=speed, zoom=zoom))
                self.assertTrue(m[2:].all(), (zoom, speed, m.astype(int)))    # from the end of the fade-in on

    def test_a_card_that_scrolls_to_the_very_end(self):
        m = analyze.gametime_card(scrolling_card(scroll_s=12, still_s=0, fade=False))
        self.assertTrue(m[1:].all(), m.astype(int))

    def test_live_play_and_moving_graphics_are_still_not_cards(self):
        self.assertFalse(analyze.gametime_card(t40.live_pictures(40)).any())
        self.assertFalse(analyze.gametime_card(t40.live_pictures(40, dark=True)).any())
        for step in (2, 4, 5):                                        # a panel sliding sideways
            tg = []
            for t in range(20):
                f = np.full((72, 128), 25, np.uint8); x = 5 + step * t
                for r in range(15, 60, 5):
                    f[r:r + 2, x:x + 50:3] = 200
                tg.append(f)
            self.assertFalse(analyze.gametime_card(np.stack(tg)).any(), step)

    def test_growth_needs_a_found_card(self):                       # card-looking but moving pictures alone are not cut
        th = np.repeat(scrolling_card(still_s=1, scroll_s=0, fade=False), 12, 0)
        slide = np.stack([np.roll(x, 3 * k, axis=1) for k, x in enumerate(th)])     # the table slides sideways
        slide[:, :, 70:] = 15                                         # (right side stays empty)
        self.assertFalse(analyze.gametime_card(slide).any())


class EndCard(unittest.TestCase):
    def test_a_card_lasting_to_the_end_of_the_video_closes_it(self):
        card = np.zeros(900, bool); card[600:900] = True                 # 5 min of card to the end (> 2 min / 15%)
        self.assertEqual(analyze.end_card(card, 900, np.zeros(900, bool)), 600.0)
        self.assertEqual(analyze.end_card(card, 900, None, bug=np.ones(900, bool), play_like=np.ones(900, bool)), 600.0)

    def test_but_not_one_in_the_first_half(self):
        card = np.zeros(900, bool); card[300:900] = True
        self.assertIsNone(analyze.end_card(card, 900, np.zeros(900, bool)))

    def test_V40_1_safety_kept(self):                                # a graphic with the game still running after it
        card = np.r_[np.zeros(500, bool), np.ones(4, bool), np.zeros(96, bool)]
        live = np.r_[np.zeros(505, bool), np.ones(85, bool), np.zeros(10, bool)]
        self.assertIsNone(analyze.end_card(card, 600, live))


class Plan(unittest.TestCase):
    def run_plan(self, best, decoded):
        cfg = deepcopy(config.DEFAULTS)
        cfg.update(best_clips=best, min_minutes=1, max_minutes=12)
        secs = len(decoded[1])
        info = {"width": 1280, "height": 720, "duration": float(secs), "codec": "h264", "has_audio": True}
        with mock.patch.object(analyze, "_extract", return_value=decoded), \
                mock.patch.object(analyze.media, "probe", return_value=info):
            return analyze.plan("/x.mp4", cfg, log=lambda *_: None)

    def game_with_scrolling_card(self, clock_ok=True, clock_on_card=False, outro=0, **kw):
        sc = scrolling_card(**kw)
        card_at = 560
        secs = card_at + len(sc) + outro
        clk, m, a, th = t40.fake_game(secs, card_at=card_at, card_len=len(sc), clock_ok=clock_ok, clock_on_card=clock_on_card)
        th = th.copy(); th[card_at:card_at + len(sc)] = sc
        return (clk, m, a, th), card_at

    def assert_no_card(self, res, card_at, label):
        self.assertLessEqual(max(b for _, b in res["segments"]), card_at, (label, res["segments"]))
        self.assertLessEqual(res["game_end_s"], card_at, label)

    def test_scrolling_card_at_the_end_is_cut_in_both_modes(self):
        for clock_ok in (True, False):
            for clock_on_card in ((False, True) if clock_ok else (False,)):   # the card's frames may read as a running clock
                for outro in (0, 15):
                    for best in (False, True):
                        dec, at = self.game_with_scrolling_card(clock_ok, clock_on_card, outro)
                        self.assert_no_card(self.run_plan(best, dec), at, (clock_ok, clock_on_card, outro, best))

    def test_zoomed_and_fast_scroll(self):
        for best in (False, True):
            dec, at = self.game_with_scrolling_card(False, zoom=1.1, speed=80)
            self.assert_no_card(self.run_plan(best, dec), at, best)

    def test_the_final_play_is_still_there(self):
        for best in (False, True):
            dec, at = self.game_with_scrolling_card(False)
            res = self.run_plan(best, dec)
            self.assertTrue(any(a <= 545 and b >= 553 for a, b in res["segments"]), (best, res["segments"]))


if __name__ == "__main__":
    unittest.main()
