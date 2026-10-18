"""vv39: Best Clips keeps whole plays. A play only ends at the whistle, an edit, a cutaway / replay or the game end -
never at a camera cut while the clock keeps running (block -> recovery, miss -> rebound stay together)."""
import os
import sys
import unittest
from copy import deepcopy
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sportsclipper import analyze, config  # noqa: E402
import scen_vv39 as S  # noqa: E402


def block_game(n=400):
    """A running stretch of plays split by camera cuts; the play 101-131 has a BLOCK at 115, a camera cut at 118 (the
    player recovers) and the putback at 127. Every other play has its own crowd moment."""
    rng = np.random.default_rng(1)
    motion = 6 + rng.random(n)
    cuts = [20, 47, 75, 101, 130, 160, 188, 214, 240, 266, 293, 320, 350]
    for c in cuts:
        motion[c] = 45
    motion[118] = 50
    rms = np.ones(n) * 0.1
    for c in cuts[:-1]:
        rms[c + 12:c + 15] = 0.3 + 0.2 * rng.random()
    rms[101:131] = 0.1; rms[115:118] = 0.7; rms[127:129] = 0.2
    z = lambda x: (x - x.mean()) / (x.std() + 1e-6)
    hz = np.zeros(n); hz[114:118] = 2.0
    return motion, z(rms), z(motion), hz


class RootCause(unittest.TestCase):
    def test_old_chunks_cut_the_block_play_in_half(self):
        motion, rz, mz, hz = block_game()
        segs = analyze._chunk([[0.0, 380.0]], motion, 6, 30)           # Best Clips without "highlights": 6-30 s chunks
        self.assertIn([101.0, 118.0], segs)                              # the chunk boundary is the camera cut AT the block
        out = analyze.best_plays(segs, rz, mz, hz, motion, 600, 0.0, 380.0, 0.5)
        self.assertTrue(any(b == 118.0 for a, b in out), out)           # the picked piece ends at the block ...
        self.assertFalse(any(a <= 118 and b >= 130 for a, b in out), out)   # ... and the recovery + putback is dropped

    def test_new_units_keep_it_whole_with_no_clock(self):
        motion, rz, mz, hz = block_game()
        cues = [(115.0, "blocked by Turner!"), (121.0, "he gets it back"), (127.0, "puts it back, good!")]
        pu = analyze.play_units(motion, rz, 400, cues, None, None, 0.0, 380.0)
        for u in pu["units"]:
            self.assertFalse(110 < u["b"] < 129, u)                      # no unit ends between the drive and the putback
        out, _ = analyze.best_play_units(pu["units"], motion, rz, mz, hz, 600, 0.0, 380.0, 0.5, True)
        self.assertTrue(any(a <= 105 and b >= 129 for a, b in out), out)

    def test_new_units_keep_it_whole_with_a_running_clock(self):
        motion, rz, mz, hz = block_game()
        clock = np.full(400, analyze.CLK_R, np.int8)                     # the clock runs through every camera cut
        pu = analyze.play_units(motion, rz, 400, [(115.0, "blocked!")], clock, None, 0.0, 380.0)
        for u in pu["units"]:
            self.assertFalse(110 < u["b"] < 129, u)
        self.assertTrue(all(u["b"] - u["a"] <= 60 for u in pu["units"]))


class Scenarios(unittest.TestCase):
    """The editor's scenarios A-L (team/editor_spec.md section 6)."""

    def check(self, name):
        units, segs = S.run(name)
        self.assertEqual(S.problems(name, units, segs), [], (name, units, segs))

    def test_A_block_recover_putback(self): self.check("A")
    def test_B_same_with_no_clock(self): self.check("B")
    def test_C_miss_long_rebound_break(self): self.check("C")
    def test_D_and_one_then_replay(self): self.check("D")
    def test_E_timeout_cutaways(self): self.check("E")
    def test_F_final_buzzer(self): self.check("F")
    def test_G_quarter_buzzer_beater(self): self.check("G")
    def test_H_steal_and_one_replay_free_throw(self): self.check("H")
    def test_I_block_other_team_no_clock(self): self.check("I")
    def test_J_out_of_bounds_angle_switch(self): self.check("J")
    def test_K_long_running_stretch(self): self.check("K")
    def test_L_miss_defensive_rebound(self): self.check("L")


class Rules(unittest.TestCase):
    def test_units_cover_whole_and_never_overlap(self):
        for name in S.SCEN:
            units, segs = S.run(name)
            for u in units:                                               # a pick is a whole unit or nothing
                for a, b in segs:
                    inside = a - 1e-6 <= u["a"] and u["b"] <= b + 1e-6
                    apart = u["b"] <= a + 1e-6 or u["a"] >= b - 1e-6
                    self.assertTrue(inside or apart, (name, u, segs))
            for x, y in zip(units, units[1:]):
                self.assertLessEqual(x["b"], y["a"] + 1e-6, name)

    def test_no_end_right_after_a_block_word(self):
        d = S.build("B")
        res = analyze.play_units(d["motion"], d["rz"], d["n"], d["cues"], None, d["bug"])
        c = S.PAD + 14
        self.assertFalse(any(c <= u["b"] <= c + 6 for u in res["units"]))

    def test_replays_are_left_out_unless_asked(self):
        d = S.build("D")
        res = analyze.play_units(d["motion"], d["rz"], d["n"], d["cues"], d["clock"], d["bug"])
        self.assertTrue(any(abs(a - (S.PAD + 16)) <= 1 for a, b in res["replays"]), res["replays"])
        play = next(u for u in res["units"] if u["a"] <= S.PAD + 3 <= u["b"])
        seg, _ = analyze.best_play_units([play], d["motion"], d["rz"], d["rz"], np.zeros(d["n"]), 600, replays=res["replays"])
        self.assertLessEqual(seg[-1][1], S.PAD + 16)
        seg, _ = analyze.best_play_units([play], d["motion"], d["rz"], d["rz"], np.zeros(d["n"]), 600, replays=res["replays"],
                                         keep_replays=True)
        self.assertGreater(seg[-1][1], S.PAD + 20)                        # option on: the replay follows its play

    def test_nothing_after_the_game_end(self):
        units, segs = S.run("F")
        self.assertLessEqual(max(b for a, b in segs), 20.0 + 1e-6)
        self.assertLessEqual(max(u["b"] for u in units), 20.0 + 1e-6)

    def test_a_forced_split_keeps_the_next_unit(self):
        n = 200
        motion = np.full(n, 20.0); rz = np.full(n, 1.5)                 # 150 s of non-stop action, no lull, no clock
        pu = analyze.play_units(motion, rz, n, None, None, None, 0.0, 150.0)
        self.assertTrue(all(u["b"] - u["a"] <= 60 for u in pu["units"]))
        self.assertTrue(any(u["end"] == "forced" for u in pu["units"]))
        hz = np.zeros(n); hz[70] = 9
        out, info = analyze.best_play_units(pu["units"], motion, rz, np.zeros(n), hz, 600, 0.0, 150.0, 0.01)
        self.assertGreaterEqual(info["appended"] + info["picked"], 2)

    def test_clock_jumps_are_edits_but_tenths_are_not(self):
        secs, cw = 60, 64
        clk = np.zeros((secs * 2, cw), np.uint8)
        clk[:, :24] = 30                                                  # dark background
        for s in range(secs):
            on = np.zeros(cw, bool)
            on[24 + s % 3: 26 + s % 3] = True                            # a normal tick: two pixels move
            if s >= 30:
                on[24:40] = ~on[24:40]                                    # the edit at 30: many digits change at once
            clk[2 * s:2 * s + 2, on] = 255
        st = analyze.clock_states(clk, secs)
        self.assertEqual(list(np.where(st == analyze.CLK_J)[0]), [29])   # the change 29 -> 30 (a cut at 30 is within 1 s)
        self.assertTrue((st[5:29] == analyze.CLK_R).all())

    def test_a_short_scoreboard_misread_does_not_end_the_play(self):
        n = 200
        clock = np.full(n, analyze.CLK_R, np.int8); clock[:5] = analyze.CLK_F; clock[150:] = analyze.CLK_F
        clock[60:63] = analyze.CLK_U                                      # 3 s with no scoreboard read mid-play
        pu = analyze.play_units(np.full(n, 10.0), np.zeros(n), n, None, clock)
        self.assertFalse(any(55 < x < 68 for u in pu["units"] for x in (u["a"], u["b"])), pu["units"])
        clock[60:66] = analyze.CLK_U                                      # 6 s: a replay / graphic - the play ends there
        pu = analyze.play_units(np.full(n, 10.0), np.zeros(n), n, None, clock)
        self.assertTrue(any(60 <= u["b"] <= 63 for u in pu["units"]), pu["units"])

    def test_caption_words(self):
        ev = analyze.cue_events([(3, "Blocked by Turner!"), (5, "and one!"), (7, "let's take another look")], 10)
        self.assertTrue(ev["cont"][3] and ev["res"][5] and ev["rep"][7])
        self.assertFalse(ev["res"][3] or ev["cont"][5])

    def test_empty(self):
        self.assertEqual(analyze.play_units(np.zeros(0), np.zeros(0))["units"], [])
        self.assertEqual(analyze.best_play_units([], np.zeros(5), np.zeros(5), np.zeros(5), np.zeros(5), 100)[0], [])


def fake_video(secs, clock_runs, motion, loud, cw=64):
    """Decoder output for plan(): 2 fps clock crop (running where clock_runs), 64x36 motion frames, 8 kHz audio."""
    clk = np.zeros((secs * 2, cw), np.uint8)
    clk[:, :24] = 30
    for s in range(secs):
        k = s if clock_runs[s] else -1
        on = np.zeros(cw, bool); on[24 + (k % 5) * 2: 27 + (k % 5) * 2] = True
        clk[2 * s:2 * s + 2, on] = 255
    x, frames = 0.0, []
    for s in range(secs):
        d = -1.0 if x > 0 else 1.0
        x += d * motion[s]
        frames.append(np.full(36 * 64, 100.0 + x, np.float32))
    a = np.concatenate([np.sin(np.arange(8000) / 3.0) * loud[s] for s in range(secs)]).astype(np.float32)
    return clk, np.array(frames), a, np.zeros((0, 72, 128), np.uint8)


def mod(name, **changes):
    """A copy of scenario `name` with some rows / checks changed (editor review probes)."""
    sc = deepcopy(S.SCEN[name]); sc.update(changes)
    return sc


class Review(unittest.TestCase):
    """vv39 review: the editor's probe inputs, kept as regressions."""

    def units(self, d, **kw):
        r = analyze.play_units(d["motion"], d["rz"], d["n"], d["cues"], d["clock"], d["bug"], 0.0, d.get("end_s"),
                               wide=d.get("wide"), **kw)
        return [{"a": u["a"] - S.PAD, "b": u["b"] - S.PAD, "end": u["end"]} for u in r["units"]]

    def one_unit(self, us, a, b):
        self.assertTrue(any(u["a"] <= a and u["b"] >= b for u in us), us)

    def test_J_seen_as_running_still_keeps_the_play(self):            # no clock-jump detection: A, C, L still whole
        for name in "ACL":
            sc = S.SCEN[name]
            d = S.build(name); d["clock"] = d["clock"].copy(); d["clock"][d["clock"] == analyze.CLK_J] = analyze.CLK_R
            units, segs = S.run(name, d=d)
            self.one_unit(units, *sc["keep"])
            for a, b in sc["nobnd"]:
                self.assertFalse(any(a + 1 < x < b for u in units for x in (u["a"], u["b"])), (name, units))
            self.assertEqual(S.unsafe_bounds(d, units), [], name)

    def test_frozen_misread_mid_play_does_not_split(self):           # review #3
        for k in (1, 2, 3):
            d = S.build("A"); d["clock"] = d["clock"].copy(); d["clock"][S.PAD + 16:S.PAD + 16 + k] = analyze.CLK_F
            self.one_unit(self.units(d), 2, 24)

    def test_slow_reset_after_the_block_no_clock(self):              # review #1 (+ 3 s caption lag)
        d = S.build("B"); d["motion"] = d["motion"].copy(); d["motion"][S.PAD + 16:S.PAD + 18] = S.MOT["low"]
        self.one_unit(self.units(d), 4, 24)
        d["cues"] = [(S.PAD + 17, "blocked by Turner!"), (S.PAD + 20, "kicks it out"), (S.PAD + 22, "puts it back, good!")]
        self.one_unit(self.units(d), 4, 24)

    def test_a_live_shot_with_a_walk_up_is_not_deleted(self):        # review #2
        d = S.build("I"); d["motion"] = d["motion"].copy()
        d["motion"][S.PAD + 16:S.PAD + 20] = S.MOT["low"]; d["motion"][S.PAD + 20:S.PAD + 24] = S.MOT["high"]
        self.one_unit(self.units(d), 7, 22)

    def test_caption_lag_protects_before_the_cue(self):              # review #4
        n = 200
        rng = np.random.default_rng(3)
        motion = 20 + 2 * rng.random(n); rz = np.full(n, 1.5)
        cues = [(79.0, "blocked by Turner!"), (85.0, "puts it back, good!")]
        pu = analyze.play_units(motion, rz, n, cues, None, None, 0.0, 150.0)
        self.assertFalse(any(76 <= u["b"] <= 85 for u in pu["units"]), pu["units"])

    def test_a_forced_split_keeps_both_sides(self):                  # review #5
        n = 200
        rng = np.random.default_rng(3)
        motion = 20 + 2 * rng.random(n); rz = np.full(n, 1.5)
        for t in (77, 30):
            cues = [(t + 2.0, "blocked by Turner!"), (t + 8.0, "puts it back, good!")]
            pu = analyze.play_units(motion, rz, n, cues, None, None, 0.0, 150.0)
            hz = np.zeros(n); hz[t + 6:t + 10] = 9                     # the putback is the loudest moment
            segs, _ = analyze.best_play_units(pu["units"], motion, rz, np.zeros(n), hz, 600, 0.0, 150.0, 0.7)
            self.assertTrue(any(a <= t - 3 and b >= t + 9 for a, b in segs), (t, pu["units"], segs))
            u = next(u for u in pu["units"] if u["a"] <= t + 7 < u["b"])          # the unit holding the putback ...
            g, _ = analyze.best_play_units([dict(x) for x in pu["units"]], motion, rz, np.zeros(n), hz, 600, 0.0, None, 0.01)
            self.assertTrue(any(a <= t - 3 and b >= u["b"] for a, b in g) or u["a"] <= t - 3, (t, g))

    def test_crowd_shot_with_medium_motion_no_clock(self):           # review #6 (needs the wide-camera check)
        d = S.build("B"); d["motion"] = d["motion"].copy(); d["rz"] = d["rz"].copy()
        d["motion"][S.PAD + 28:S.PAD + 32] = S.MOT["med"]; d["rz"][S.PAD + 28:S.PAD + 32] = S.CROWD["R"]
        us = self.units(d)
        self.one_unit(us, 4, 24)
        self.assertFalse(any(u["a"] < 31 and u["b"] > 29 for u in us), us)

    def test_short_replay_between_cuts_with_no_bug_track(self):      # review #7
        d = S.build("A"); d["clock"] = d["clock"].copy(); d["motion"] = d["motion"].copy()
        d["clock"][S.PAD + 24:S.PAD + 27] = analyze.CLK_U; d["motion"][S.PAD + 24] = 60; d["motion"][S.PAD + 27] = 60
        d["bug"] = None
        us = self.units(d)
        self.one_unit(us, 2, 23)
        self.assertFalse(any(u["a"] < 26 and u["b"] > 25 for u in us), us)

    def test_post_buzzer_celebration_when_the_end_is_unknown(self):  # review #9
        n = 300
        motion = np.full(n, 10.0); rz = np.zeros(n)
        for c in (20, 45, 70, 95, 120, 150, 175, 200, 230):
            motion[c] = 60
        rz[150:175] = 2.5; motion[151:175] = 12; motion[176:230] = 3.0; rz[60:63] = 1.5
        pu = analyze.play_units(motion, rz, n, [(148.0, "at the buzzer, good!")], None, None, 0.0, None)
        segs, _ = analyze.best_play_units(pu["units"], motion, rz, np.zeros(n), np.zeros(n), 600, 0.0, None, 0.3)
        self.assertFalse(any(a < 170 and b > 155 for a, b in segs), segs)
        self.assertTrue(any(u["a"] <= 125 and u["b"] >= 148 for u in pu["units"]))   # the buzzer play itself stays

    def test_F_without_a_known_end(self):
        sc = mod("F"); sc.pop("end_s")
        units, segs = S.run("F", sc=sc)
        self.assertEqual(S.problems("F", units, segs, sc=sc), [])

    def test_short_jump_ball_play_needs_a_real_dead_ball(self):
        n = 200
        clock = np.full(n, analyze.CLK_R, np.int8); clock[:20] = analyze.CLK_F
        clock[26:28] = analyze.CLK_U                                     # 6 s after the tip: a 2 s drop-out, not a whistle
        clock[26] = analyze.CLK_F; clock[27] = analyze.CLK_F; clock[28:33] = analyze.CLK_R; clock[33:40] = analyze.CLK_F
        motion = np.full(n, 10.0); motion[30] = 60; motion[26] = 60
        us = analyze.play_units(motion, np.zeros(n), n, None, clock, None, 19.0)["units"]
        self.assertFalse(any(u["b"] - u["a"] < 8 and u["b"] <= 30 for u in us), us)
        clock = np.full(n, analyze.CLK_R, np.int8); clock[:20] = analyze.CLK_F; clock[26:34] = analyze.CLK_F   # tip, foul
        us = analyze.play_units(np.full(n, 10.0), np.zeros(n), n, None, clock, None, 19.0)["units"]
        self.assertTrue(us and us[0]["a"] <= 20 and us[0]["b"] <= 30, us)


class Round2(unittest.TestCase):
    """vv39 review round 2: the editor's probe_r2 inputs."""

    def units(self, sc):
        d = S.build("B", sc)
        return d, Review.units(self, d)

    def test_R1_bench_shot_after_a_roar_is_cut(self):                 # a dunk, its roar, then a bench shot (no clock)
        sc = dict(readable=False,
                  rows=[(0, 3, "U", "low", "q"), (4, 20, "U", "med", "n"), (21, 25, "U", "high", "R"), (26, 33, "U", "low", "L"),
                        (34, 50, "U", "med", "n")],
                  cuts=[4, 26, 34], caps=[(21, "throws it down!")], keep=(5, 24), wideN=[(0, 3), (27, 33)])
        for crowd in ("L", "n", None):
            d = S.build("B", sc)
            if crowd:
                d["rz"][S.PAD + 26:S.PAD + 34] = S.CROWD[crowd]
            if crowd is None:
                d["rz"][S.PAD + 21:S.PAD + 26] = S.CROWD["L"]                    # no roar at all
            us = Review.units(self, d)
            self.assertTrue(any(u["a"] <= 5 and 25 <= u["b"] <= 27 for u in us), (crowd, us))
            self.assertFalse(any(u["a"] < 33 and u["b"] > 28 for u in us), (crowd, us))

    def test_R2_tight_live_angle_with_the_basket_is_kept(self):       # not the wide camera, but the basket is in it
        sc = dict(readable=False,
                  rows=[(0, 3, "U", "low", "q"), (4, 14, "U", "med", "n"), (15, 19, "U", "med", "n"), (20, 22, "U", "med", "R"),
                        (23, 23, "U", "med", "n"), (24, 40, "U", "med", "n")],
                  cuts=[4, 15, 24], caps=[(20, "and he scores, good!")], keep=(5, 22), wideN=[(0, 3), (16, 23)])
        for variant in ("caption", "no caption", "away crowd"):
            d = S.build("B", sc)
            if variant != "caption":
                d["cues"] = []
            if variant == "away crowd":
                d["rz"][S.PAD + 20:S.PAD + 23] = S.CROWD["L"]
            us = Review.units(self, d)
            self.assertTrue(any(u["a"] <= 4 and u["b"] >= 23 for u in us), (variant, us))

    def test_R3_short_reset_shot_after_a_block_word(self):           # with the caption the play goes on (K1: not without)
        sc = dict(readable=False,
                  rows=[(0, 3, "U", "low", "q"), (4, 11, "U", "med", "n"), (12, 13, "U", "high", "R"), (14, 14, "U", "high", "L"),
                        (15, 17, "U", "low", "n"), (18, 20, "U", "high", "L"), (21, 23, "U", "high", "R"), (24, 40, "U", "med", "n")],
                  cuts=[4, 15, 18, 27], caps=[(13, "blocked!")], keep=(5, 24), wideN=[(0, 3)])
        us = Review.units(self, S.build("B", sc))
        self.assertTrue(any(u["a"] <= 5 and u["b"] >= 24 for u in us), us)

    def chain(self, every, words):
        n = 640
        motion = np.full(n, 10.0); rz = np.zeros(n); cues = []
        for k, t in enumerate(range(4, 600, every)):
            motion[t] = 60; cues.append((t + 3.0, words[k % len(words)]))
        rz[300:303] = 2.5
        us = analyze.play_units(motion, rz, n, cues, None, None, 0.0, 600.0)["units"]
        hz = np.zeros(n); hz[300] = 9
        segs, _ = analyze.best_play_units(us, motion, rz, np.zeros(n), hz, 120, 0.0, 600.0, 0.3, True)
        return us, segs

    def test_R5_dense_commentary_never_keeps_the_whole_video(self):
        for every, words in ((8, ("good",)), (8, ("rebound", "good")), (12, ("good", "rebound")), (12, ("good",))):
            us, segs = self.chain(every, words)
            self.assertLessEqual(sum(b - a for a, b in segs), 120 * 1.02 + 1e-6, (every, words, segs))
            self.assertTrue(all(b - a <= 90 * 1.5 + 1e-6 for a, b in segs), (every, words, segs))
            self.assertTrue(segs and segs[0][0] == 0.0 and segs[-1][1] == 600.0, (every, words, segs))   # tip and finish kept
            self.assertEqual(S.unsafe_bounds(dict(n=640, cues=[(4 + k * every + 3.0, words[k % len(words)])
                                                               for k in range(len(range(4, 600, every)))],
                                                  rz=np.zeros(640), clock=None, end_s=600.0),
                                             [dict(u, a=u["a"] - S.PAD, b=u["b"] - S.PAD) for u in us]), [])

    def test_R5_made_it_words_still_allow_a_walk_up_split(self):     # "good" every 12 s: split in the walk-ups, not forced
        us, _ = self.chain(12, ("good",))
        self.assertFalse(any(u["end"] == "forced" for u in us), us)

    def test_forced_picks_respect_the_maximum(self):
        n = 640
        motion = np.full(n, 20.0); rz = np.full(n, 1.5)                 # nothing but forced splits
        us = analyze.play_units(motion, rz, n, None, None, None, 0.0, 600.0)["units"]
        self.assertTrue(all(u["end"] in ("forced", "dead") for u in us))
        for mx in (60, 120, 300):
            segs, _ = analyze.best_play_units(us, motion, rz, np.zeros(n), np.zeros(n), mx, 0.0, 600.0, 0.5, True)
            self.assertLessEqual(sum(b - a for a, b in segs), mx * 1.02 + 1e-6, (mx, segs))
            self.assertEqual(segs[-1][1], 600.0)


def digits(txt, shot=None):
    import cv2
    img = np.full((24, 96), 30, np.uint8)
    cv2.putText(img, txt, (2, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 255, 2)
    if shot is not None:
        cv2.putText(img, f"{shot:2d}", (70, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 255, 2)
    return img.reshape(-1)


def clock_video(start, secs, with_shot=False, resets=(), jump_at=None):
    fmt = lambda t: f"{int(t) // 60}:{int(t) % 60:02d}" if t >= 60 else f"{t:4.1f}"
    frames, shot = [], 24.0
    for k in range(secs * 2):
        t = start - k / 2 - (207 if jump_at is not None and k / 2 >= jump_at else 0)
        sh = None
        if with_shot:
            if any(abs(k / 2 - r) < 1e-9 for r in resets):
                shot = 24.0
            sh = max(0, int(np.ceil(shot))); shot -= 0.5
        frames.append(digits(fmt(t), sh))
    return analyze.clock_states(np.array(frames), secs)


class RealDigits(unittest.TestCase):
    """Rendered clock digits (review #8): rollovers, the switch to tenths and shot-clock resets are not edits."""

    def test_minute_rollovers(self):
        self.assertFalse((clock_video(205, 90) == analyze.CLK_J).any())

    def test_switch_to_tenths(self):
        self.assertFalse((clock_video(80, 40) == analyze.CLK_J).any())

    def test_shot_clock_reset(self):
        self.assertFalse((clock_video(400, 50, True, (14, 33)) == analyze.CLK_J).any())

    def test_a_real_edit_is_a_jump(self):
        st = clock_video(500, 60, jump_at=30)       # 7:51 -> 4:23: spliced 3:27 on (a 1-2 digit jump is missed: the play goes on)
        self.assertTrue((st[28:31] == analyze.CLK_J).any(), list(np.where(st == analyze.CLK_J)[0]))


class WideCamera(unittest.TestCase):
    def test_crowd_pictures_are_not_wide(self):
        rng = np.random.default_rng(0)
        th = rng.integers(150, 190, (100, 72, 128)).astype(np.uint8)    # the court
        th[40:45] = rng.integers(0, 255, (5, 72, 128))                  # a crowd shot
        self.assertEqual(list(np.where(~analyze.wide_shots(th, 100))[0]), [40, 41, 42, 43, 44])
        self.assertIsNone(analyze.wide_shots(th[:10], 10))


class Plan(unittest.TestCase):
    def run_plan(self, clock_ok=True):
        secs = 600
        runs = np.ones(secs, bool)
        for a in (0, 150, 300, 450):                                      # dead balls (whistles)
            runs[a:a + 12] = False
        runs[590:] = False
        motion = np.full(secs, 8.0); loud = np.full(secs, 0.05)
        for c in range(20, 590, 25):
            motion[c] = 60.0                                              # camera cuts every 25 s
        for c in (195, 345):
            motion[c] = 60.0
        loud[190:195] = 0.6                                               # the block (crowd roar) right before the cut at 195
        loud[203:206] = 0.4                                               # ... the putback after it
        clk, m, a, th = fake_video(secs, runs if clock_ok else np.zeros(secs, bool), motion, loud)
        if not clock_ok:
            clk[:] = 0                                                    # no scoreboard found at all
        cfg = deepcopy(config.DEFAULTS)
        cfg.update(best_clips=True, min_minutes=1, max_minutes=12, include_interview=False)
        info = {"width": 1280, "height": 720, "duration": float(secs), "codec": "h264", "has_audio": True}
        cues = [(190.0, "blocked by Turner!"), (198.0, "he gets it back"), (204.0, "puts it back, good!")]
        with mock.patch.object(analyze, "_extract", return_value=(clk, m, a, th)), \
                mock.patch.object(analyze.media, "probe", return_value=info):
            return analyze.plan("/x.mp4", cfg, log=lambda *_: None, cues=cues)

    def test_plan_keeps_the_block_play_whole(self):
        for ok in (True, False):
            res = self.run_plan(ok)
            segs = res["segments"]
            self.assertTrue(any(a <= 185 and b >= 207 for a, b in segs), (ok, segs))
            for a, b in segs:
                self.assertFalse(185 < b < 207, (ok, segs))
            for k, (a, b) in enumerate(segs):                             # only the jump-ball play may be shorter than 8 s
                self.assertGreaterEqual(b - a, 4.0 if k == 0 else 8.0, (ok, segs))

    def test_plan_ends_at_the_game_end(self):
        res = self.run_plan(True)
        self.assertLessEqual(res["segments"][-1][1], 590 + analyze.END_PAD_S + 1e-6)
        self.assertGreater(res["segments"][-1][1], 580)


if __name__ == "__main__":
    unittest.main()
