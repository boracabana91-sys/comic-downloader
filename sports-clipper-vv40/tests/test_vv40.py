"""vv40: the channel's closing stats card ('GAMETIME HIGHLIGHTS' box score) is always cut, and nothing after it is kept -
in the normal reclip and in Best Clips. The thin table text of the real card averages to dull grey at 128x72, so the vv26
test (bright pixels) missed it; a still, dark picture with text-like detail is now a card too."""
import os
import sys
import unittest
from copy import deepcopy
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sportsclipper import analyze, config  # noqa: E402


def card_picture(zoom=1.0, W=1920, H=1080):
    """A box-score card like the real one (dark, 'GAMETIME HIGHLIGHTS', FINAL tag, team header, ~19 thin table rows in the
    left half, right half empty), as the app sees it: grey 128x72, averaged down like ffmpeg's scaler."""
    import cv2
    img = np.full((H, W, 3), (22, 15, 15), np.uint8)
    x0, x1 = int(W * 0.03), int(W * 0.47)
    f = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, "GAMETIME HIGHLIGHTS", (x0, int(H * .06)), f, 1.1, (235, 235, 235), 2)
    cv2.rectangle(img, (int(W * .40), int(H * .02)), (int(W * .465), int(H * .07)), (40, 110, 240), -1)
    cv2.putText(img, "Toronto Raptors 125", (x0, int(H * .16)), f, 1.2, (150, 150, 150), 2)
    cv2.putText(img, "129 Detroit Pistons", (int(W * .27), int(H * .16)), f, 1.2, (255, 255, 255), 2)
    y = int(H * .25)
    for r in range(19):
        if r % 2:
            cv2.rectangle(img, (x0, y - 20), (x1, y + 10), (34, 26, 26), -1)
        cv2.putText(img, "Collins    22  12  4-7  1-3  3-4  8  0  0  1  0  2  6  3  +9", (x0, y), f, 0.6, (215, 215, 215), 1)
        y += int(H * .039)
    if zoom != 1.0:                                                   # vv38+ reclips are zoomed to 110%
        cw, ch = int(W / zoom), int(H / zoom)
        img = cv2.resize(img[(H - ch) // 2:(H + ch) // 2, (W - cw) // 2:(W + cw) // 2], (W, H))
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (128, 72), interpolation=cv2.INTER_AREA)


def live_pictures(n, seed=0, dark=False):
    """Moving 'live play' pictures: a textured scene that pans every second."""
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 90 if dark else 220, (72, 512)).astype(np.uint8)
    return np.stack([np.roll(base, -7 * t, axis=1)[:, :128] for t in range(n)])


class Detector(unittest.TestCase):
    def test_root_cause_the_old_bright_text_test_misses_the_real_card(self):
        for z in (1.0, 1.1):
            left = card_picture(z)[:, :64].astype(np.float32)
            self.assertLess((left > 110).mean(), 0.015)                 # vv26 needed > 1.5% bright pixels on the left

    def test_the_card_is_found_full_size_and_zoomed(self):
        for z in (1.0, 1.1):
            th = np.repeat(card_picture(z)[None], 5, 0)
            self.assertTrue(analyze.gametime_card(th).all(), z)
            self.assertTrue(analyze.still_text_card(th).all(), z)

    def test_with_video_noise(self):
        rng = np.random.default_rng(2)
        th = np.repeat(card_picture()[None], 6, 0).astype(int) + rng.integers(-3, 4, (6, 72, 128))
        self.assertTrue(analyze.gametime_card(np.clip(th, 0, 255).astype(np.uint8)).all())

    def test_live_play_is_not_a_card(self):
        self.assertFalse(analyze.gametime_card(live_pictures(30)).any())
        self.assertFalse(analyze.gametime_card(live_pictures(30, dark=True)).any())    # a dark arena

    def test_a_still_dark_frame_with_only_the_score_bug_is_not_a_card(self):
        sb = np.full((20, 72, 128), 12, np.uint8)
        sb[:, 60:66, 30:98] = 200; sb[:, 61:65, 35:95:6] = 20
        self.assertFalse(analyze.gametime_card(sb).any())

    def test_a_moving_timeout_graphic_is_not_a_card(self):
        for step in (2, 4, 5):
            tg = []
            for t in range(20):
                f = np.full((72, 128), 25, np.uint8); x = 5 + step * t
                for r in range(15, 60, 5):
                    f[r:r + 2, x:x + 50:3] = 200
                tg.append(f)
            self.assertFalse(analyze.gametime_card(np.stack(tg)).any(), step)

    def test_long_videos_are_checked_in_pieces_without_gaps(self):
        live = live_pictures(1400, 5)
        for at in (1196, 1199, 1200):
            th = np.concatenate([live[:at], np.repeat(card_picture()[None], 4, 0), live[:50]])
            self.assertEqual(list(np.where(analyze.gametime_card(th))[0]), list(range(at, at + 4)), at)

    def test_a_short_still_moment_is_not_a_card(self):
        th = np.concatenate([live_pictures(10), np.repeat(card_picture()[None], 2, 0), live_pictures(10, 1)])
        self.assertFalse(analyze.still_text_card(th).any())


class EndCard(unittest.TestCase):
    def test_a_card_at_the_end_ends_the_video(self):
        card = np.zeros(900, bool); card[860:890] = True
        self.assertEqual(analyze.end_card(card, 900), 860.0)

    def test_a_card_in_the_middle_does_not(self):
        card = np.zeros(900, bool); card[300:310] = True
        self.assertIsNone(analyze.end_card(card, 900))

    def test_late_card_with_the_game_still_running_after_it_does_not(self):
        n = 9000                                                        # a 2.5 h full game: a stats graphic in Q4
        card = np.zeros(n, bool); card[7000:7008] = True
        live = np.zeros(n, bool); live[7010:8500] = True
        self.assertIsNone(analyze.end_card(card, n, live))
        self.assertEqual(analyze.end_card(card, n, np.zeros(n, bool)), 7000.0)  # nothing runs after it: the end

    def test_a_one_second_flash_is_ignored(self):
        card = np.zeros(900, bool); card[880] = True
        self.assertIsNone(analyze.end_card(card, 900))


def fake_game(secs=600, card_at=None, card_len=40, outro=0, clock_ok=True, clock_on_card=False):
    """Decoder output for plan(): a running clock with whistles, moving pictures, crowd noise; optionally the stats card
    from `card_at` for `card_len` s, then `outro` s of moving video (end screen)."""
    import test_vv39 as t39
    runs = np.ones(secs, bool)
    for a in (0, 150, 300, 450):
        runs[a:a + 12] = False
    play_end = card_at if card_at is not None else secs - 10
    runs[play_end - 3:] = False                                          # the final buzzer a few seconds before the card
    if clock_on_card and card_at is not None:
        runs[card_at:card_at + card_len] = True                          # (c) the clock area of the card animates
    motion = np.full(secs, 8.0); loud = np.full(secs, 0.05)
    for c in range(20, secs, 25):
        motion[c] = 60.0
    loud[play_end - 20:play_end - 5] = 0.6                               # the last play is the loudest: Best Clips wants it
    clk, m, a, _ = t39.fake_video(secs, runs if clock_ok else np.zeros(secs, bool), motion, loud)
    if not clock_ok:
        clk[:] = 0
    th = live_pictures(secs, 3)
    if card_at is not None:
        th[card_at:card_at + card_len] = card_picture()
        m[card_at:card_at + card_len] = m[card_at]                       # the card does not move
    return (clk, m, a, th)


class Plan(unittest.TestCase):
    def run_plan(self, best, decoded, **cfgx):
        cfg = deepcopy(config.DEFAULTS)
        cfg.update(best_clips=best, min_minutes=1, max_minutes=12, **cfgx)
        secs = len(decoded[1])
        info = {"width": 1280, "height": 720, "duration": float(secs), "codec": "h264", "has_audio": True}
        with mock.patch.object(analyze, "_extract", return_value=decoded), \
                mock.patch.object(analyze.media, "probe", return_value=info):
            return analyze.plan("/x.mp4", cfg, log=lambda *_: None)

    def assert_card_out(self, res, card_at, label):
        last = max(b for a, b in res["segments"])
        self.assertLessEqual(last, card_at, (label, res["segments"]))      # nothing from the card on (and nothing after it)
        self.assertLessEqual(res["game_end_s"], card_at, label)

    def test_card_in_the_last_40_s_is_cut_in_both_modes(self):
        for best in (False, True):
            for clock_ok in (True, False):
                for outro in (0, 20):
                    secs = 600 + outro
                    res = self.run_plan(best, fake_game(secs, card_at=560, outro=outro, clock_ok=clock_ok))
                    self.assert_card_out(res, 560, (best, clock_ok, outro))

    def test_card_read_as_a_running_clock_still_ends_the_clip(self):         # (c) the clock seems to run on the card
        for best in (False, True):
            res = self.run_plan(best, fake_game(600, card_at=560, clock_on_card=True))
            self.assert_card_out(res, 560, best)

    def test_keeping_the_interview_does_not_keep_the_card(self):
        for best in (False, True):
            res = self.run_plan(best, fake_game(620, card_at=560, outro=20), include_interview=True)
            self.assert_card_out(res, 560, best)

    def test_a_loud_card_is_never_a_best_play(self):                 # music over the card, no readable clock
        clk, m, a, th = fake_game(620, card_at=560, outro=20, clock_ok=False)
        a = a.copy(); a[560 * 8000:600 * 8000] = np.sin(np.arange(40 * 8000) / 3.0) * 0.9
        for best in (False, True):
            self.assert_card_out(self.run_plan(best, (clk, m, a, th)), 560, best)

    def test_a_card_at_the_start_is_cut(self):
        clk, m, a, th = fake_game(600)
        th = th.copy(); th[2:20] = card_picture()
        for best in (False, True):
            res = self.run_plan(best, (clk, m, a, th))
            self.assertFalse(any(a0 < 19 and b0 > 3 for a0, b0 in res["segments"]), (best, res["segments"]))
            self.assertGreater(max(b for a0, b in res["segments"]), 585, best)   # an opening card does not end the clip

    def test_the_final_play_is_still_kept(self):
        for best in (False, True):
            res = self.run_plan(best, fake_game(600, card_at=560))
            self.assertTrue(any(a <= 545 and b >= 553 for a, b in res["segments"]), (best, res["segments"]))

    def test_no_card_no_change(self):
        for best in (False, True):
            res = self.run_plan(best, fake_game(600))
            self.assertGreater(max(b for a, b in res["segments"]), 585, best)


if __name__ == "__main__":
    unittest.main()
