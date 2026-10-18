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
            self.assertGreaterEqual(min(b - a for a, b in segs), 4.0)

    def test_plan_ends_at_the_game_end(self):
        res = self.run_plan(True)
        self.assertLessEqual(res["segments"][-1][1], 590 + analyze.END_PAD_S + 1e-6)
        self.assertGreater(res["segments"][-1][1], 580)


if __name__ == "__main__":
    unittest.main()
