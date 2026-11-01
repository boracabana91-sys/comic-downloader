import sys, os, math, time, numpy as np
from scipy.interpolate import PchipInterpolator
import cat_core as C
from cat_core import FPS, DUR, S_, env_at
from PIL import Image

CUTS = [8.24, 9.24, 10.24, 11.24, 12.44, 13.44, 14.54, 15.64]
CF = [round(c*FPS) for c in CUTS]
D = dict(z=1.0, cx=360, cy=640, roll=0, bob=0, hr=0, hy=0, ear=0, blush=0.35, look=0, lookv=0, wink=0, blink=0, lid=0.42,
         brow=0.3, browl=0, smirk=0.7, grin=0, sip=0)

def K(t, pts):
    if len(pts) == 1: return pts[0][1]
    xs, ys = zip(*pts)
    return float(PchipInterpolator(xs, ys, extrapolate=False)(min(max(t, xs[0]), xs[-1])))

def S(*a): return list(a)
OPEN = dict(
    z=[(0, 3.3), (2.4, 2.7), (4.4, 1.3), (6.2, 1.18), (7.4, 1.3), (8.23, 1.5)],
    cx=[(0, 521), (2.4, 500), (4.4, 372), (6.2, 360), (8.23, 360)],
    cy=[(0, 470), (2.4, 500), (4.4, 650), (6.2, 640), (7.4, 600), (8.23, 560)],
    roll=[(0, 3), (2.4, 2), (4.4, 0), (8.23, 0)],
    look=[(0, -0.9), (4.2, -0.9), (4.7, -0.5), (6.2, -0.5), (6.6, 0.6), (7.5, 0.6), (8.0, 0.0), (8.23, 0)],
    lid=[(0, 0.45), (6.3, 0.45), (6.8, 0.8), (7.4, 0.8), (7.9, 0.42), (8.23, 0.4)],
    sip=[(0, 0), (6.3, 0), (6.8, 1), (7.4, 1), (7.9, 0), (8.23, 0)],
    hr=[(0, -5), (4.5, -5), (5.0, -3), (6.0, -7), (7.2, -8), (8.1, 0), (8.23, 0)],
    smirk=[(0, 0.3), (6.8, 0.3), (8.2, 0.9)], blush=[(0, 0.1), (6, 0.2), (8.2, 0.7)],
    brow=[(0, 0.2), (6.5, 0.2), (7.6, 0.9), (8.23, 0.9)], hy=[(0, 0), (6.8, 0), (7.1, 3), (7.9, 0)])
def wig(t0, t1, step, a, b):
    n = int((t1-t0)/step); return [(t0 + i*step, a if i % 2 == 0 else b) for i in range(n+1)]
SHOTS = [
 (0, OPEN),
 (8.24, dict(z=[(8.24, 2.05), (9.24, 2.35)], cx=[(8.24, 360), (9.24, 366)], cy=[(8.24, 520), (9.24, 515)], roll=[(8.24, -3), (9.24, -1)],
             wink=[(8.24, 0), (8.40, 0), (8.50, 1), (9.0, 1), (9.22, 0.4)], smirk=[(8.24, 0.7), (9.24, 0.9)], blush=[(8.24, 0.7)], lid=[(8.24, 0.4)],
             brow=[(8.24, 0.8), (9.24, 0.6)], hr=[(8.24, -3), (9.24, -5)])),
 (9.24, dict(z=[(9.24, 1.9), (10.24, 2.15)], cx=[(9.24, 372), (10.24, 360)], cy=[(9.24, 535), (10.24, 525)], roll=[(9.24, 4), (10.24, 2)],
             grin=[(9.24, 0.2), (9.5, 1), (10.24, 1)], blush=[(9.24, 0.9)], lid=[(9.24, 0.3)], brow=[(9.24, 0.4)], hr=[(9.24, -4), (10.24, 2)])),
 (10.24, dict(z=[(10.24, 2.2), (11.24, 2.4)], cx=[(10.24, 345), (11.24, 352)], cy=[(10.24, 520), (11.24, 510)], roll=[(10.24, -5), (11.24, -3)],
              smirk=[(10.24, 0.5), (10.5, 1.0), (11.24, 1.0)], lid=[(10.24, 0.5)], brow=[(10.24, 1.0)], look=[(10.24, -0.4), (11.24, 0.3)], hr=[(10.24, 5), (11.24, 3)], blush=[(10.24, 0.8)])),
 (11.24, dict(z=[(11.24, 2.7), (12.44, 3.0)], cx=[(11.24, 360)], cy=[(11.24, 478), (12.44, 470)], roll=[(11.24, 2), (12.44, -1)],
              lid=[(11.24, 0.6), (11.8, 0.55), (12.44, 0.35)], look=[(11.24, -1), (11.6, -1), (11.95, 1), (12.2, 1), (12.44, 0)],
              brow=[(11.24, 0.2), (11.8, 1), (12.2, 0.2), (12.44, 0.9)], browl=[(11.24, 0), (11.8, 0), (12.2, 1), (12.44, 0)],
              blink=[(11.24, 0), (11.9, 0), (11.97, 1), (12.1, 0)], smirk=[(11.24, 0.7)], hr=[(11.24, -3), (12.44, 3)], blush=[(11.24, 0.9)])),
 (12.44, dict(z=[(12.44, 1.65), (13.44, 1.95)], cx=[(12.44, 385), (13.44, 372)], cy=[(12.44, 570), (13.44, 550)], roll=[(12.44, -4), (13.44, 0)],
              wink=[(12.44, 0), (12.62, 0), (12.72, 1), (13.2, 1), (13.44, 0.3)], smirk=[(12.44, 0.9)], grin=[(12.44, 0), (12.7, 0.7), (13.44, 0.7)],
              blush=[(12.44, 0.8)], hr=[(12.44, 4), (13.44, -2)], brow=[(12.44, 0.9)])),
 (13.44, dict(z=[(13.44, 2.4), (14.54, 2.6)], cx=[(13.44, 360)], cy=[(13.44, 495), (14.54, 490)], roll=[(13.44, 3), (14.54, -2)],
              lid=[(13.44, 0.45)], brow=wig(13.44, 14.54, 0.16, 1.0, 0.1), browl=wig(13.44, 14.54, 0.16, 0.1, 1.0), grin=[(13.44, 0.5)],
              hr=[(13.44, -4), (14.54, 4)], look=[(13.44, 0.5), (14.54, -0.5)], blush=[(13.44, 0.9)])),
 (14.54, dict(z=[(14.54, 2.0), (15.64, 2.3)], cx=[(14.54, 350), (15.64, 358)], cy=[(14.54, 540), (15.64, 530)], roll=[(14.54, 5), (15.64, 2)],
              grin=[(14.54, 0.3), (14.8, 1), (15.64, 1)], blush=[(14.54, 1.0)], lid=[(14.54, 0.3)], brow=[(14.54, 0.5)], hr=[(14.54, 3), (15.64, -3)],
              ear=[(14.54, 0), (14.7, 1), (14.85, 0), (15.1, 1), (15.25, 0)])),
 (15.64, dict(z=[(15.64, 1.95), (18.0, 2.5)], cx=[(15.64, 360)], cy=[(15.64, 535), (18.0, 520)], roll=[(15.64, -3), (18.0, 0)],
              smirk=[(15.64, 0.6), (16.0, 1.0), (18, 1.0)], lid=[(15.64, 0.45), (18, 0.4)], brow=[(15.64, 0.6), (16.5, 1), (18, 1)],
              wink=[(15.64, 0), (16.85, 0), (16.95, 1), (17.3, 1), (17.4, 0)], hr=[(15.64, 2), (18.0, -2)], blush=[(15.64, 0.6), (17, 1.0)])),
]
SHOT_F = [0] + CF

def params(f, extra=None):
    t = f/FPS
    si = max(i for i, sf in enumerate(SHOT_F) if f >= sf)
    P = dict(D)
    for key, pts in SHOTS[si][1].items(): P[key] = K(t, pts)
    P["talk"] = env_at(t)
    # natural blink unless a take controls it
    if "blink" not in SHOTS[si][1]:
        P["blink"] = 1.0 if (t % 3.3) < 0.11 and P["wink"] < 0.5 else 0.0
    P["bob"] = math.sin(t*2.4)*1.4
    if f >= round(16.1*FPS): P["hu"] = (t - 16.1)*0.9 + 0.3
    # camera handheld shake: decays after each cut
    last = max([c for c in CF if f >= c] or [0])
    amp = (3.0 + 11.0*math.exp(-(f-last)/FPS*9)) if last else 1.4
    dx = amp*(math.sin(f*1.9) + 0.6*math.sin(f*4.3)); dy = amp*(math.sin(f*2.3 + 1) + 0.5*math.sin(f*5.1))
    P["cx"] += dx/P["z"]; P["cy"] += dy/P["z"]; P["roll"] += 0.5*amp/10*math.sin(f*3.1)
    # fade-in, flash and blur at cuts
    P["fade"] = min(1.0, max(0.0, t/0.9))**1.5 if t < 0.9 else 1.0
    rel = [f - c for c in CF]
    bl = {-1: 3.0, 0: 7.0, 1: 11.0, 2: 7.0, 3: 3.5, 4: 1.5}; fl = {0: 0.9, 1: 0.5, 2: 0.2}
    P["blur"] = max([bl.get(r, 0) for r in rel] + [0]); P["flash"] = max([fl.get(r, 0) for r in rel] + [0])
    if extra: P.update(extra)
    return P

def render(f):
    P = params(f); t = f/FPS
    return C.finish(C.frame_img(P, t), P, t)

def work(f):
    out = f"{S_}cat_frames/f{f:04d}.jpg"
    if os.path.exists(out): return f
    render(f).save(out, quality=94); return f

if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "test":
        os.makedirs(S_ + "cat_test", exist_ok=True)
        for tt in [float(x) for x in sys.argv[2].split(",")]:
            f = int(round(tt*FPS)); t0 = time.time(); im = render(f); im.save(f"{S_}cat_test/t{tt:05.2f}.png"); print(tt, "%.2fs" % (time.time()-t0))
    else:
        from multiprocessing import Pool
        os.makedirs(S_ + "cat_frames", exist_ok=True)
        n = int(DUR*FPS); t0 = time.time()
        with Pool(2) as p:
            for i, _ in enumerate(p.imap(work, range(n), chunksize=4)):
                if i % 30 == 0: print(i, "%.0fs" % (time.time()-t0), flush=True)
        print("done", time.time()-t0)
