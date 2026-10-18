"""vv39: the editor's synthetic play scenarios (A-L), built as per-second signals. Shared by tests/test_vv39.py."""
import numpy as np

from sportsclipper import analyze as A

MOT = {"low": 3.0, "med": 10.0, "high": 20.0}
CROWD = {"q": -0.8, "n": 0.0, "L": 1.5, "R": 2.5}
CLK = {"U": A.CLK_U, "F": A.CLK_F, "R": A.CLK_R, "J": A.CLK_J}
PAD = 60

# rows: (first s, last s, clock, motion, crowd[, bug]); cuts: CUT seconds (motion 60); caps: (s, text)
# checks: keep [a,b] inside one segment; nobnd (a,b) no boundary strictly inside; start/end [x,y]; excl [a,b] no overlap
SCEN = {
    "A": dict(rows=[(0, 3, "F", "low", "q"), (4, 11, "R", "med", "n"), (12, 14, "R", "high", "L"), (15, 15, "R", "med", "L"),
                    (16, 20, "R", "high", "L"), (21, 23, "R", "high", "R"), (24, 26, "R", "med", "n"), (27, 27, "J", "med", "n"),
                    (28, 40, "R", "med", "n")],
              cuts=[15, 27], caps=[(14, "blocked by Turner!"), (18, "kicks it out"), (21, "puts it back, good!")],
              keep=(4, 24), start=(1, 4), end=(24, 27), nobnd=[(4, 24)], never_end=(14, 16)),
    "B": dict(readable=False,
              rows=[(0, 3, "U", "low", "q"), (4, 11, "U", "med", "n"), (12, 14, "U", "high", "L"), (15, 15, "U", "med", "L"),
                    (16, 20, "U", "high", "L"), (21, 23, "U", "high", "R"), (24, 27, "U", "med", "n"), (28, 31, "U", "low", "L"),
                    (32, 45, "U", "med", "n")],
              cuts=[4, 15, 27, 32], caps=[(14, "blocked by Turner!"), (18, "kicks it out"), (21, "puts it back, good!")],
              keep=(5, 24), start=(4, 6), end=(24, 28), nobnd=[(5, 24)], excl=[(29, 31)]),
    "C": dict(rows=[(0, 2, "F", "low", "q"), (3, 9, "R", "med", "n"), (10, 11, "R", "high", "n"), (12, 12, "R", "med", "n"),
                    (13, 16, "R", "high", "L"), (17, 19, "R", "high", "R"), (20, 23, "R", "med", "n"), (24, 24, "J", "med", "n"),
                    (25, 40, "R", "med", "n")],
              cuts=[12, 24], caps=[(10, "misses the three"), (11, "long rebound"), (17, "throws it down!")],
              keep=(3, 20), start=(0, 3), end=(20, 24), nobnd=[(3, 20)]),
    "D": dict(rows=[(0, 2, "F", "low", "q"), (3, 11, "R", "med", "n"), (12, 12, "R", "high", "R"), (13, 15, "F", "high", "R"),
                    (16, 16, "U", "med", "L", "N"), (17, 22, "U", "low", "n", "N"), (23, 23, "F", "med", "n"),
                    (24, 27, "F", "low", "q"), (28, 29, "F", "low", "n"), (30, 45, "R", "med", "n")],
              cuts=[16, 23], caps=[(12, "slam! and one!"), (17, "let's take another look")],
              keep=(3, 15), start=(0, 3), end=(15, 16), excl_play=[(17, 29)]),
    "E": dict(rows=[(0, 2, "F", "low", "q"), (3, 12, "R", "med", "n"), (13, 14, "R", "high", "L"), (15, 16, "F", "med", "L"),
                    (17, 17, "F", "med", "n"), (18, 24, "F", "low", "q"), (25, 25, "F", "med", "L"), (26, 29, "F", "med", "R"),
                    (30, 30, "F", "med", "n"), (31, 33, "F", "low", "q"), (34, 50, "R", "med", "n")],
              cuts=[17, 25, 30], caps=[(13, "for three!"), (46, "good")],
              keep=(3, 16), start=(1, 3), end=(16, 17), excl=[(18, 32)], next_start=(31, 34)),
    "F": dict(post=False, end_s=20,
              rows=[(0, 3, "F", "low", "q"), (4, 15, "R", "med", "L"), (16, 17, "R", "high", "R"), (18, 20, "F", "high", "R"),
                    (21, 21, "F", "med", "R"), (22, 25, "F", "med", "L"), (26, 29, "U", "med", "n", "N"),
                    (30, 30, "U", "med", "n", "N"), (31, 90, "U", "low", "n", "N")],
              cuts=[21, 30], caps=[(17, "at the buzzer... good! wins it!"), (24, "Pacers win the ball game")],
              keep=(4, 19), start=(2, 4), end=(19, 21), excl=[(22, 90)]),
    "G": dict(rows=[(0, 2, "F", "low", "q"), (3, 13, "R", "med", "n"), (14, 14, "R", "high", "L"), (15, 17, "F", "high", "R"),
                    (18, 18, "U", "med", "L", "N"), (19, 25, "U", "low", "n", "N"), (26, 26, "U", "med", "q", "N"),
                    (27, 40, "U", "low", "q", "N"), (41, 44, "F", "low", "q"), (45, 60, "R", "med", "n")],
              cuts=[18, 26], caps=[(15, "beats the buzzer!")],
              keep=(3, 17), start=(1, 3), end=(17, 18), excl=[(19, 42)], next_start=(43, 45)),
    "H": dict(rows=[(0, 1, "F", "low", "q"), (2, 8, "R", "med", "n"), (9, 9, "R", "high", "L"), (10, 10, "R", "med", "L"),
                    (11, 14, "R", "high", "L"), (15, 17, "F", "high", "R"), (18, 18, "F", "med", "L"), (19, 21, "F", "low", "n"),
                    (22, 22, "U", "med", "n", "N"), (23, 28, "U", "low", "n", "N"), (29, 29, "F", "med", "q"),
                    (30, 37, "F", "low", "q"), (38, 50, "R", "med", "n")],
              cuts=[10, 18, 22, 29], caps=[(9, "stolen by White!"), (15, "and one!")],
              keep=(4, 17), start=(0, 4), end=(17, 18), nobnd=[(4, 17)], excl_play=[(19, 37)]),
    "I": dict(readable=False,
              rows=[(0, 5, "U", "med", "n"), (6, 6, "U", "med", "n"), (7, 9, "U", "med", "n"), (10, 11, "U", "high", "n"),
                    (12, 13, "U", "high", "R"), (14, 14, "U", "high", "n"), (15, 15, "U", "med", "L"), (16, 17, "U", "high", "n"),
                    (18, 20, "U", "high", "L"), (21, 21, "U", "high", "n"), (22, 23, "U", "med", "n"), (24, 24, "U", "med", "n"),
                    (25, 28, "U", "low", "q"), (29, 29, "U", "med", "n"), (30, 45, "U", "med", "n")],
              cuts=[6, 15, 24, 29], caps=[(12, "swatted away by Wemby!"), (18, "finishes at the rim")],
              keep=(7, 22), start=(6, 7), end=(22, 25), nobnd=[(7, 22)], excl=[(26, 28)]),
    "J": dict(rows=[(0, 1, "F", "low", "q"), (2, 19, "R", "med", "n"), (20, 24, "F", "low", "q"), (25, 29, "R", "med", "n"),
                    (30, 30, "R", "med", "n"), (31, 37, "R", "med", "n"), (38, 39, "R", "high", "L"), (40, 42, "F", "low", "q"),
                    (43, 60, "R", "med", "n")],
              cuts=[30], caps=[(19, "out of bounds"), (38, "good")],
              keep=(25, 40), nobnd=[(2, 20), (25, 40)], never_bnd=(29, 31)),
    "K": dict(pre="F",
              rows=[(0, 9, "R", "med", "n"), (10, 10, "R", "med", "n"), (11, 17, "R", "high", "L"), (18, 19, "R", "high", "R"),
                    (20, 21, "R", "med", "n"), (22, 22, "R", "med", "n"), (23, 25, "R", "med", "n"), (26, 33, "R", "low", "q"),
                    (34, 34, "R", "med", "n"), (35, 35, "R", "med", "n"), (36, 48, "R", "med", "n"), (49, 51, "R", "high", "L"),
                    (52, 53, "R", "high", "R"), (54, 69, "R", "med", "n"), (70, 73, "F", "low", "q")],
              cuts=[10, 22, 35, 48, 60], caps=[(18, "for three!"), (52, "slam!")],
              keep=(12, 21), keep2=(46, 56), nobnd=[(0, 26), (35, 72)], one_bnd=((0, 72), (26, 35)), last_end=(72, 73)),
    "L": dict(rows=[(0, 2, "F", "low", "q"), (3, 13, "R", "med", "n"), (14, 14, "R", "high", "L"), (15, 15, "R", "med", "L"),
                    (16, 18, "R", "high", "n"), (19, 24, "R", "med", "q"), (25, 30, "R", "low", "q"), (31, 31, "J", "med", "n"),
                    (32, 45, "R", "med", "n")],
              cuts=[15, 31], caps=[(14, "misses"), (16, "rebound Gobert")],
              keep=(3, 18), start=(1, 3), end=(21, 31), nobnd=[(3, 18)]),
}


def build(name):
    """Per-second arrays for a scenario, shifted by PAD seconds of neutral play before (and after, unless post=False)."""
    sc = SCEN[name]
    readable = sc.get("readable", True)
    last = max(r[1] for r in sc["rows"]) + 1
    post = PAD if sc.get("post", True) else 0
    n = PAD + last + post
    pre = sc.get("pre", "R" if readable else "U")
    clock = np.full(n, CLK[pre if readable else "U"], np.int8)
    if readable and post:
        clock[PAD + last:] = CLK["R"]
    motion = np.full(n, MOT["med"]); rz = np.zeros(n); bug = np.ones(n, bool)
    for row in sc["rows"]:
        a, b, c, m, cr = row[:5]
        sl = slice(PAD + a, PAD + b + 1)
        clock[sl] = CLK[c]; motion[sl] = MOT[m]; rz[sl] = CROWD[cr]
        if len(row) > 5:
            bug[sl] = row[5] == "Y"
    if pre == "F":                                       # a dead ball right before the scenario
        motion[:PAD] = MOT["med"]; clock[:PAD - 6] = CLK["R"]; clock[PAD - 6:PAD] = CLK["F"]
    for c in sc["cuts"]:
        motion[PAD + c] = 60.0
    cues = [(PAD + t, txt) for t, txt in sc["caps"]]
    end_s = PAD + sc["end_s"] if "end_s" in sc else None
    return dict(n=n, motion=motion, rz=rz, bug=bug, clock=clock if readable else None, cues=cues, end_s=end_s)


def run(name, **kw):
    """(units, segments) for a scenario: the play under test is the loudest unit and the share is set so only it
    (plus the always-kept opening unit, and the final unit when the game end is known) is picked."""
    d = build(name)
    res = A.play_units(d["motion"], d["rz"], d["n"], d["cues"], d["clock"], d["bug"], 0.0, d["end_s"], **kw)
    units = res["units"]
    hz = np.zeros(d["n"])
    for t, _ in d["cues"]:
        hz[int(t)] = 3.0
    k = SCEN[name]["keep"]
    hz[PAD + k[0]:PAD + k[1] + 1] += 5.0                 # the play under test is the best one
    k = SCEN[name]["keep"]
    target = next((u for u in units if u["a"] <= PAD + k[0] + 1 and u["b"] >= PAD + k[1] - 1), None)
    forced = units[0]["b"] - units[0]["a"] if units else 0
    if d["end_s"] is not None and units and units[-1] is not target:
        forced += units[-1]["b"] - units[-1]["a"]
    elig = sum(u["b"] - u["a"] for u in units) or 1.0
    want = forced + (target["b"] - target["a"] if target else 0) - 0.5
    segs, _ = A.best_play_units(units, d["motion"], d["rz"], np.zeros(d["n"]), hz, 10_000, 0.0, d["end_s"],
                                share=max(0.01, want / elig), end_known=d["end_s"] is not None, clock=d["clock"])
    shift = lambda xs: [[a - PAD, b - PAD] for a, b in xs]
    return [{"a": u["a"] - PAD, "b": u["b"] - PAD, "end": u["end"]} for u in units], shift(segs)


def problems(name, units, segs, tol=1.0):
    """The scenario's assertions; returns a list of failures (empty = pass). Inclusive second ranges, +-1 s tolerance."""
    sc = SCEN[name]
    bad = []
    bnds = sorted({x for s in segs for x in s})

    def holder(k):
        return next((s for s in segs if s[0] <= k[0] + tol and s[1] >= k[1] - tol + 1 - 1), None)
    k = sc["keep"]
    seg = holder(k)
    if seg is None:
        bad.append(f"keep {k} not inside one segment: {segs}")
    else:
        if "start" in sc and not (sc["start"][0] - tol <= seg[0] <= sc["start"][1] + tol):
            bad.append(f"start {seg[0]} not in {sc['start']}")
        if "end" in sc and not (sc["end"][0] - tol <= seg[1] <= sc["end"][1] + tol):
            bad.append(f"end {seg[1]} not in {sc['end']}")
    if "keep2" in sc and not any(u["a"] <= sc["keep2"][0] + tol and u["b"] >= sc["keep2"][1] - tol for u in units):
        bad.append(f"keep {sc['keep2']} not inside one segment")
    ub = sorted({x for u in units for x in (u["a"], u["b"])})
    for a, b in sc.get("nobnd", []):
        inside = [x for x in ub if a + tol < x < b - tol + 1]
        if inside:
            bad.append(f"unit boundary inside ({a},{b}): {inside}")
    if "never_end" in sc:
        a, b = sc["never_end"]
        if any(a <= u["b"] <= b for u in units):
            bad.append(f"a unit ends in {sc['never_end']}")
    if "never_bnd" in sc:
        a, b = sc["never_bnd"]
        if any(a <= x <= b for x in ub):
            bad.append(f"a boundary in {sc['never_bnd']}")
    for a, b in sc.get("excl", []):
        for s in segs:
            if s[0] < b + 1 - tol and s[1] > a + tol:
                bad.append(f"segment {s} overlaps excluded {a}-{b}")
    for a, b in sc.get("excl_play", []):           # only the play's own segment (the next play may start at its restart)
        if seg and seg[0] < b + 1 - tol and seg[1] > a + tol:
            bad.append(f"play segment {seg} overlaps excluded {a}-{b}")
    if "next_start" in sc:
        x, y = sc["next_start"]
        if not any(x - tol <= u["a"] <= y + tol for u in units):
            bad.append(f"no unit starts in {sc['next_start']}: {[u['a'] for u in units]}")
    if "one_bnd" in sc:
        (a, b), (x, y) = sc["one_bnd"]
        inside = [v for v in ub if a + tol < v < b - tol]
        if len(inside) != 1 or not (x - tol <= inside[0] <= y + tol):
            bad.append(f"want one boundary in {sc['one_bnd'][1]} inside {sc['one_bnd'][0]}, got {inside}")
    if "last_end" in sc:
        x, y = sc["last_end"]
        if not any(x - tol <= u["b"] <= y + tol for u in units):
            bad.append(f"no unit ends in {sc['last_end']}")
    for s in segs:
        if s[1] - s[0] < 8 - 1e-6:
            bad.append(f"segment shorter than 8 s: {s}")
    return bad
