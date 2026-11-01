
import math, sys, os, numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from scipy.interpolate import PchipInterpolator
from scipy.io import wavfile
S_ = "/tmp/claude-0/-home-claude/c62db8fc-3175-5bf7-b686-f4148b0c2d08/scratchpad/"
W, H, FPS, SS, SB = 720, 1280, 30, 2, 3
DUR, PUNCH = 18.0, 8.24
RED, DRED, LRED = (214, 36, 30), (150, 18, 20), (240, 90, 70)
BLK, GRN, WHT, OL = (22, 22, 28), (70, 170, 60), (255, 255, 255), (20, 10, 10)
GOLD, GOLDD = (240, 190, 70), (180, 130, 34)
PINK, VIOLET = (255, 60, 140), (150, 70, 255)
ORG, ORGD, CREAM, PNK = (238, 140, 52), (190, 92, 28), (255, 232, 196), (244, 140, 160)
SC, OX, OY = 1.2, 360, 1092
FO = -60

def catmull(pts, n=10):
    out = []; p = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(p)-2):
        for k in range(n):
            u = k/n
            out.append(tuple(0.5*((2*p[i][j]) + (-p[i-1][j]+p[i+1][j])*u + (2*p[i-1][j]-5*p[i][j]+4*p[i+1][j]-p[i+2][j])*u*u + (-p[i-1][j]+3*p[i][j]-3*p[i+1][j]+p[i+2][j])*u**3) for j in (0, 1)))
    out.append(pts[-1]); return out

def glow(base, layer, rad, strength=1.0):
    g = layer.filter(ImageFilter.GaussianBlur(rad))
    if strength != 1.0:
        a = g.getchannel("A").point(lambda v: min(255, int(v*strength))); g.putalpha(a)
    base.alpha_composite(g)

# ---------------- voice envelope for lip-sync
sr_, a_ = wavfile.read(S_ + "vo_cat.wav"); a_ = a_.astype(float)
if a_.ndim > 1: a_ = a_.mean(1)
NF = int(DUR*FPS); hop = sr_ // FPS
env = np.array([np.sqrt(np.mean(a_[i*hop:(i+1)*hop]**2)) if i*hop < len(a_) else 0 for i in range(NF)])
env = np.clip(env/(np.percentile(env, 95)+1e-9), 0, 1); env[env < 0.12] = 0
_sm = np.zeros_like(env); _v = 0
for j, e_ in enumerate(env):
    _v = _v + (e_-_v)*(0.7 if e_ > _v else 0.35); _sm[j] = _v
env = _sm
def _cent(seg):
    if len(seg) < 64: return 1500
    sp = np.abs(np.fft.rfft(seg*np.hanning(len(seg)))); fr = np.fft.rfftfreq(len(seg), 1/sr_)
    return np.sum(sp*fr)/(np.sum(sp)+1e-9)
cen = np.clip((np.array([_cent(a_[j*hop:(j+1)*hop]) for j in range(NF)]) - 800)/2500, 0, 1)
cen = np.convolve(cen, np.ones(5)/5, "same")
def env_at(t): return float(np.interp(t*FPS, np.arange(NF), env))
def cen_at(t): return float(np.interp(t*FPS, np.arange(NF), cen))

# ---------------- background (built once per process, at SB x)
def build_bg():
    SS = SB

    big = Image.new("RGBA", (W*SS, H*SS), (18, 8, 24, 255))
    d = ImageDraw.Draw(big)
    def s(x, y): return (x*SS, y*SS)
    def rect(x0, y0, x1, y1, fill, outline=None, w=0, r=0):
        if r: d.rounded_rectangle([x0*SS, y0*SS, x1*SS, y1*SS], r*SS, fill=fill, outline=outline, width=int(w*SS))
        else: d.rectangle([x0*SS, y0*SS, x1*SS, y1*SS], fill=fill, outline=outline, width=int(w*SS))
    def pl(pts, fill=None, outline=None, w=2):
        q = [s(*p) for p in pts]
        if fill: d.polygon(q, fill=fill)
        if outline: d.line(q + [q[0]], fill=outline, width=int(w*SS), joint="curve")
    def ln(pts, col, w):
        q = [s(*p) for p in pts]; d.line(q, fill=col, width=max(1, int(w*SS)), joint="curve")

    # ---------- headliner (roof)
    yy = np.linspace(0, 1, 170*SS)[:, None, None]
    roof = (np.array([10, 4, 16])*(1-yy) + np.array([34, 14, 44])*yy)*np.ones((1, W*SS, 1))
    big.paste(Image.fromarray(roof.astype(np.uint8)), (0, 0))
    d = ImageDraw.Draw(big)
    rng = np.random.default_rng(11)
    for _ in range(70):   # fibre-optic stars
        x, y = rng.uniform(10, 710), rng.uniform(8, 150); r_ = rng.uniform(1.2, 2.6)
        d.ellipse([(x-r_)*SS, (y-r_)*SS, (x+r_)*SS, (y+r_)*SS], fill=(255, 235, 210, 255))


    # ---------- rear window: two scrolling layers (far skyline, near bokeh + light streaks), seamless loop
    WX0, WY0, WX1, WY1 = 74, 170, 646, 690
    PW = (WX1-WX0)*SS; WHt = (WY1-WY0)*SS
    r2 = np.random.default_rng(23)
    sky = np.zeros((WHt, 2*PW, 3), np.float32)
    t_ = np.linspace(0, 1, WHt)[:, None]
    top_, mid_, bot_ = np.array([14, 10, 52]), np.array([120, 40, 130]), np.array([255, 120, 120])
    for c in range(3):
        sky[..., c] = np.where(t_ < 0.6, top_[c]*(1-t_/0.6) + mid_[c]*(t_/0.6), mid_[c]*(1-(t_-0.6)/0.4) + bot_[c]*((t_-0.6)/0.4))
    far = Image.fromarray(sky.astype(np.uint8)).convert("RGBA"); fd = ImageDraw.Draw(far)
    for col, hmin, hmax in (((60, 28, 92), 0.18, 0.40), ((34, 14, 58), 0.10, 0.30)):
        x = 0; bl = []
        while x < PW:
            w_ = int(r2.uniform(30, 80)*SS/2*1.4); h_ = int(r2.uniform(hmin, hmax)*WHt)
            lights = [(xx_, yy_, r2.random() < 0.38, r2.random() < 0.7) for yy_ in range(WHt-h_+12, WHt-6, 22) for xx_ in range(8, w_-8, 18)]
            bl.append((x, w_, h_, lights)); x += w_ + int(r2.uniform(0, 8))
        for off in (-PW, 0, PW):
            for x, w_, h_, lights in bl:
                fd.rectangle([x+off+PW, WHt-h_, x+off+PW+w_, WHt], fill=col)
                for xx_, yy_, on, warm in lights:
                    if on: fd.rectangle([x+off+PW+xx_, yy_, x+off+PW+xx_+6, yy_+9], fill=(255, 214, 140) if warm else (255, 120, 180))
    near = Image.new("RGBA", (2*PW, WHt), (0, 0, 0, 0)); nd2 = ImageDraw.Draw(near)
    pal = [(255, 200, 120), (255, 90, 160), (110, 200, 255), (255, 150, 90), (190, 120, 255)]
    boks = [(r2.uniform(0, PW), r2.uniform(WHt*0.25, WHt*0.95), r2.uniform(14, 52)*SS/2*1.4, pal[r2.integers(len(pal))], int(r2.uniform(70, 150))) for _ in range(46)]
    for off in (-PW, 0, PW):
        for x, y, r_, c, al in boks:
            nd2.ellipse([x+off+PW-r_, y-r_, x+off+PW+r_, y+r_], fill=c + (al,))
    near = near.filter(ImageFilter.GaussianBlur(5*SS/2))
    sk = Image.new("RGBA", near.size, (0, 0, 0, 0)); sd2 = ImageDraw.Draw(sk)
    strs = [(r2.uniform(0, PW), r2.uniform(WHt*0.55, WHt*0.9), r2.uniform(80, 240)*SS/2, pal[r2.integers(len(pal))]) for _ in range(14)]
    for off in (-PW, 0, PW):
        for x, y, L_, c in strs: sd2.line([(x+off+PW, y), (x+off+PW+L_, y)], fill=c + (200,), width=int(5*SS/2))
    near.alpha_composite(sk.filter(ImageFilter.GaussianBlur(3)))
    # frame around the window (the window interior itself is pasted in per frame)
    d.rounded_rectangle([WX0*SS, WY0*SS, WX1*SS, WY1*SS], 46*SS, outline=(10, 6, 14), width=12*SS)
    d.rounded_rectangle([(WX0-5)*SS, (WY0-5)*SS, (WX1+5)*SS, (WY1+5)*SS], 50*SS, outline=(150, 150, 165), width=3*SS)

    # ---------- pillars (door panels) + neon
    for sgn in (-1, 1):
        x0, x1 = (0, 70) if sgn < 0 else (650, 720)
        rect(x0, 0, x1, 1280, (30, 12, 26))
        for k in range(10):
            ln([(x0+8 if sgn < 0 else x0+6, 190+k*90), (x1-6 if sgn < 0 else x1-8, 190+k*90)], (52, 24, 40), 3)
    neon = Image.new("RGBA", big.size, (0, 0, 0, 0)); nd = ImageDraw.Draw(neon)
    nd.line([(68*SS, 170*SS), (68*SS, 1000*SS)], fill=PINK + (255,), width=5*SS)
    nd.line([(652*SS, 170*SS), (652*SS, 1000*SS)], fill=PINK + (255,), width=5*SS)
    nd.rounded_rectangle([60*SS, 150*SS, 660*SS, 700*SS], 56*SS, outline=VIOLET + (255,), width=4*SS)
    nd.line([(0, 168*SS), (720*SS, 168*SS)], fill=PINK + (255,), width=4*SS)
    glow(big, neon, 16*SS/2, 1.6); big.alpha_composite(neon)
    d = ImageDraw.Draw(big)

    # ---------- backrest (tufted leather)
    BY0, BY1 = 690, 962
    LEA, LEAD, LEAL = (112, 20, 40), (66, 10, 26), (150, 38, 62)
    rect(30, BY0, 690, BY1, LEA, OL, 3, 40)
    rect(30, BY0, 690, BY0+30, LEAL, None, 0, 40)
    pitch = 62
    tl = Image.new('RGBA', big.size, (0, 0, 0, 0)); td = ImageDraw.Draw(tl)
    for k in range(-6, 14):
        x = 30 + k*pitch
        td.line([(x*SS, BY0*SS), ((x+(BY1-BY0))*SS, BY1*SS)], fill=LEAD+(255,), width=3*SS); td.line([(x*SS, BY1*SS), ((x+(BY1-BY0))*SS, BY0*SS)], fill=LEAD+(255,), width=3*SS)
    msk = Image.new("L", big.size, 0); ImageDraw.Draw(msk).rounded_rectangle([30*SS, BY0*SS, 690*SS, BY1*SS], 40*SS, fill=255)
    cm = Image.new('L', big.size, 0); ImageDraw.Draw(cm).rounded_rectangle([30*SS, BY0*SS, 690*SS, BY1*SS], 40*SS, fill=255)
    big.paste(tl, (0, 0), ImageChops.multiply(tl.getchannel('A'), cm)); d = ImageDraw.Draw(big)
    outside = Image.new("RGBA", big.size, (0, 0, 0, 0))
    inv = ImageChops.invert(msk)
    # (lines were drawn over the pillars/window; redraw those regions cheaply)
    rect(30, BY0, 690, BY1, None, OL, 3, 40)
    for k in range(-6, 14):
        for r_ in range(0, 6):
            bx = 30 + k*pitch + r_*0;
    for row in range(1, 5):
        for col in range(0, 12):
            bx = 30 + col*pitch + (pitch/2 if row % 2 else 0) + 4; by = BY0 + row*(BY1-BY0)/5
            if 40 < bx < 680:
                d.ellipse([(bx-5)*SS, (by-5)*SS, (bx+5)*SS, (by+5)*SS], fill=GOLD, outline=GOLDD, width=SS)
                d.ellipse([(bx-2)*SS, (by-3)*SS, (bx)*SS, (by-1)*SS], fill=(255, 240, 190))

    # ---------- seat cushion (top surface + front face) and floor
    pl([(30, 962), (690, 962), (700, 1040), (20, 1040)], (132, 28, 52), OL, 3)
    ln([(40, 1000), (680, 1000)], LEAD, 2)
    rect(20, 1040, 700, 1114, (92, 14, 34), OL, 3, 8)
    for x in range(48, 700, 52): ln([(x, 1052), (x, 1102)], (60, 8, 22), 3)
    for x in range(48, 700, 52): ln([(x+26, 1052), (x+26, 1102)], (60, 8, 22), 1)
    ln([(24, 1114), (696, 1114)], (30, 8, 20), 6)
    fl = np.linspace(0, 1, (1280-1114)*SS)[:, None, None]
    carpet = (np.array([54, 22, 52])*(1-fl) + np.array([14, 6, 22])*fl)*np.ones((1, W*SS, 1))
    big.paste(Image.fromarray(carpet.astype(np.uint8)), (0, 1114*SS)); d = ImageDraw.Draw(big)
    for x in range(-200, 900, 38): ln([(x+ (x-360)*0.12, 1114), (x + (x-360)*0.9, 1280)], (70, 32, 66), 2)

    # ---------- ice bucket + bottle (bottom right) and rose (bottom left)
    pl([(560, 1150), (680, 1150), (668, 1264), (572, 1264)], (200, 205, 215), OL, 3)
    ln([(566, 1176), (674, 1176)], (140, 146, 160), 4); ln([(570, 1228), (670, 1228)], (140, 146, 160), 4)
    pl([(594, 1150), (646, 1150), (642, 1060), (638, 1030), (622, 1030), (618, 1060), (598, 1060)], (28, 72, 38), OL, 3)
    pl([(603, 1112), (637, 1112), (637, 1144), (603, 1144)], (240, 220, 160), None)
    pl([(622, 1030), (638, 1030), (638, 1014), (622, 1014)], GOLD, OL, 2)
    for _i, (cx_, cy_) in enumerate([(580, 1156), (606, 1146), (640, 1150), (664, 1156), (620, 1158)]):
        d.polygon([s(cx_-14, cy_), s(cx_, cy_-12), s(cx_+14, cy_-2), s(cx_+10, cy_+10), s(cx_-8, cy_+10)], fill=(214, 236, 250), outline=(120, 170, 200))
    glow(big, Image.new("RGBA", big.size, (0, 0, 0, 0)), 1)

    # soft shadow behind character on seatback / seat
    sh = Image.new("RGBA", big.size, (0, 0, 0, 0)); sd = ImageDraw.Draw(sh)
    sd.ellipse([150*SS, 560*SS, 570*SS, 1030*SS], fill=(0, 0, 0, 120))
    sd.ellipse([120*SS, 1080*SS, 600*SS, 1130*SS], fill=(0, 0, 0, 150))
    big.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26*SS/2))); d = ImageDraw.Draw(big)

    inner = Image.new("L", (PW, WHt), 0); ImageDraw.Draw(inner).rounded_rectangle([12*SS, 12*SS, PW-12*SS, WHt-12*SS], 34*SS, fill=255)
    al = big.getchannel("A"); hole = Image.new("L", big.size, 0); hole.paste(inner, (WX0*SS, WY0*SS))
    big.putalpha(ImageChops.subtract(al, hole))
    return dict(B=big, far=far, near=near, inner=inner, pos=(WX0*SS, WY0*SS), PW=PW, WHt=WHt)


_BGC = {}
def get_bg():
    if "b" not in _BGC: _BGC["b"] = build_bg()
    return _BGC["b"]

def frame_img(P, t):
    bg = get_bg(); Bimg = bg["B"]; PW, WHt = bg["PW"], bg["WHt"]
    o1 = int((12*SB*t) % PW); o2 = int((70*SB*t) % PW)
    win = bg["far"].crop((o1, 0, o1+PW, WHt)); win.alpha_composite(bg["near"].crop((o2, 0, o2+PW, WHt)))
    Bimg.paste(win, bg["pos"], bg["inner"])
    z, cxs, cys, roll = P["z"], P["cx"], P["cy"], math.radians(P["roll"])
    co, si = math.cos(roll), math.sin(roll)
    a_ = SB*co/(SS*z); b_ = SB*si/(SS*z); c_ = SB*(cxs - (360*co + 640*si)/z)
    a2 = -SB*si/(SS*z); b2 = SB*co/(SS*z); c2 = SB*(cys + (360*si - 640*co)/z)
    big = Bimg.transform((W*SS, H*SS), Image.AFFINE, (a_, b_, c_, a2, b2, c2), resample=Image.BICUBIC)
    d = ImageDraw.Draw(big)
    k = SC*SS*z
    HY = [0]; HA = [0.0]; BY = [P.get("bob", 0.0)]
    def T(x, y):
        y = y + HY[0]
        if HA[0]:
            ca, sa = math.cos(HA[0]), math.sin(HA[0]); dx, dy = x, y + 340
            x, y = dx*ca - dy*sa, dx*sa + dy*ca - 340
        X = OX + x*SC; Y = OY + (y + BY[0])*SC
        u, v = (X - cxs)*z, (Y - cys)*z
        return ((u*co - v*si + 360)*SS, (u*si + v*co + 640)*SS)
    def poly(pts, fill, outline=OL, w=5):
        q = [T(*p) for p in pts]
        if fill: d.polygon(q, fill=fill)
        if outline: d.line(q + [q[0]], fill=outline, width=max(1, int(w*k/SS)), joint="curve")
    def line(pts, col, w, cap=True):
        q = [T(*p) for p in pts]; d.line(q, fill=col, width=max(1, int(w*k)), joint="curve")
        if cap:
            for (x, y) in (q[0], q[-1]):
                r = w*k/2; d.ellipse([x-r, y-r, x+r, y+r], fill=col)
    def ell(x, y, rx, ry, fill, outline=OL, w=4):
        n = 30 if max(rx, ry) > 8 else 16
        q = [T(x + rx*math.cos(a), y + ry*math.sin(a)) for a in np.linspace(0, 2*math.pi, n, endpoint=False)]
        if fill: d.polygon(q, fill=fill)
        if outline: d.line(q + [q[0]], fill=outline, width=max(1, int(w*k/SS*1.0)), joint="curve")
    def ribbon(center, widths, col, outline=OL, ow=0):
        n = len(center); L_, R_ = [], []
        if len(widths) != n: widths = list(np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(widths)), widths))
        for i, (x, y) in enumerate(center):
            a = center[max(0, i-1)]; b = center[min(n-1, i+1)]
            dx, dy = b[0]-a[0], b[1]-a[1]; m = math.hypot(dx, dy) or 1
            nx, ny = -dy/m, dx/m; w_ = widths[i]/2
            L_.append((x+nx*w_, y+ny*w_)); R_.append((x-nx*w_, y-ny*w_))
        pts = L_ + R_[::-1]
        poly(pts, col, outline, ow) if ow else poly(pts, col, None)

    # --- tail (sways)
    tl0 = catmull([(60, -130), (150, -104), (222, -120), (252, -176), (236, -226)])
    tl_ = [(x + math.sin(t*2.2 + i*0.09)*i*0.10, y + math.sin(t*2.2 + i*0.09 + 1.0)*i*0.09) for i, (x, y) in enumerate(tl0)]
    ribbon(tl_, [34]*len(tl_), ORG, OL, 5)
    for _i in range(8, len(tl_), 7): line([(tl_[_i][0]-14, tl_[_i][1]-2), (tl_[_i][0]+14, tl_[_i][1]+2)], ORGD, 5, False)
    ell(tl_[-1][0], tl_[-1][1], 17, 15, CREAM, OL, 4)

    # --- legs: relaxed front-facing sit, knees apart, thighs foreshortened toward the viewer
    TR, TRL, CRE, SOCK = (36, 36, 52), (62, 62, 86), (84, 84, 112), (255, 110, 170)
    def shoe_pts(sg, ax):   # sg=-1 left foot, +1 right foot; toe points out and toward the viewer
        base = [(-14, -30), (28, -30), (34, -14), (28, 6), (-4, 16), (-46, 14), (-64, 0), (-52, -14), (-28, -20)]
        return catmull([(ax + sg*-(x_) if False else ax + sg*(-x_), y_) for x_, y_ in base], 6) if False else catmull([(ax + sg*(-x_ - 10) * -1 * -1, y_) for x_, y_ in base], 6)
    for sg in (-1, 1):
        kx = sg*76; ax = sg*80
        ell(sg*70, 14, 50, 9, (0, 0, 0), None)                                                      # floor shadow
        # thigh: from under the jacket hem out to the knee
        ribbon(catmull([(sg*40, -150), (sg*58, -112), (kx, -76)]), [88, 80, 66], TR, OL, 5)
        line([(sg*(kx*0.55), -122), (sg*(kx*0.86), -92)], CRE, 3, False)    # thigh crease
        # shin
        ribbon(catmull([(kx, -70), (sg*78, -46), (ax, -26)]), [60, 50, 44], TR, OL, 5)
        line([(kx-sg*4, -62), (ax-sg*2, -34)], CRE, 3, False)
        # knee cap + fold
        ell(kx, -69, 27, 20, TR, None)
        line(catmull([(kx-20, -82), (kx, -88), (kx+20, -82)], 6), TRL, 3, False)
        line(catmull([(kx-18, -52), (kx, -46), (kx+18, -52)], 6), (18, 18, 28), 3, False)           # trouser fold
        # sock + shoe (toe out)
        poly([(ax-24, -34), (ax+24, -34), (ax+22, -22), (ax-22, -22)], SOCK, OL, 3)
        shp = catmull([(ax - sg*(-26), -28), (ax + sg*(-26)*-1, -28)], 2) if False else None
        out_ = sg
        pts = [(ax - 26, -26), (ax + 26, -26), (ax + 30, -10), (ax + 24, 8), (ax + 4, 16),
               (ax + out_*42, 16), (ax + out_*62, 8), (ax + out_*60, -6), (ax + out_*44, -16), (ax + out_*20, -22)]
        # build a clean outline: heel at inner side, toe outward
        heel_x = ax - out_*26; ankle_x = ax + out_*26
        pts = [(heel_x, -26), (ankle_x, -26), (ankle_x + out_*8, -8), (ax + out_*56, -4), (ax + out_*68, 8),
               (ax + out_*58, 17), (ax + out_*20, 18), (heel_x - out_*6, 14), (heel_x - out_*8, -8)]
        poly(catmull(pts, 6), (14, 14, 20), OL, 5)
        line(catmull([(ax + out_*44, -2), (ax + out_*52, 7), (ax + out_*44, 15)], 6), (74, 74, 100), 3, False)   # toe-cap seam
        line([(ax + out_*4, -16), (ax + out_*26, -10)], (200, 200, 225), 4, False)                          # shine
        ell(ax + out_*56, 4, 6, 3.4, (210, 210, 235), None)
        line(catmull([(heel_x - out_*7, 15), (ax + out_*20, 19), (ax + out_*62, 16)], 6), (6, 6, 8), 5, False)  # sole

    # --- left arm draped along the seat-back (viewer left), fingers tap
    tap = math.sin(t*5.0)*3
    line([(-88, -326), (-150, -352), (-212, -340)], BLK, 44)
    line([(-98, -330), (-140, -345)], (50, 50, 64), 6, False)
    poly([(-216, -362), (-202, -362), (-202, -318), (-216, -318)], GOLD, OL, 3)
    ell(-238, -336, 28, 24, ORG)
    ell(-238, -326, 20, 16, CREAM, None)
    for fi_, fx_ in enumerate((-252, -236, -220)):
        dy_ = max(0.0, math.sin(t*5.0 - fi_*0.9))*5
        line([(fx_, -318), (fx_ - 2, -296 + dy_)], OL, 18); line([(fx_, -318), (fx_ - 2, -296 + dy_)], CREAM, 12)

    # --- torso (fur) hidden under the jacket, neck
    poly(catmull([(-90, -340), (-70, -250), (-60, -150), (60, -150), (70, -250), (90, -340)]), ORG, OL, 5)
    poly(catmull([(-38, -430), (-42, -380), (-46, -336), (46, -336), (42, -380), (38, -430)]), ORG, OL, 5)
    poly(catmull([(-22, -410), (-26, -370), (-28, -338), (28, -338), (26, -370), (22, -410)]), CREAM, None)

    # --- tuxedo jacket
    jy = [-338, -292, -230, -176, -124]; jw = [112, 102, 80, 84, 96]
    JL = catmull([(-h, y) for h, y in zip(jw, jy)]); JR = catmull([(h, y) for h, y in zip(jw, jy)])
    poly(JL + JR[::-1], (24, 22, 34), OL, 5)
    ell(-102, -326, 30, 24, (24, 22, 34), OL, 4); ell(102, -326, 30, 24, (24, 22, 34), OL, 4)   # shoulder pads
    # white shirt V (open collar: one button too many)
    poly([(-46, -338), (46, -338), (14, -196), (-14, -196)], WHT, OL, 4)
    # chest skin inside the V
    poly([(-22, -338), (22, -338), (4, -232), (-4, -232)], CREAM, None)
    ln_ = [(-24, -338), (-4, -232)]; line(ln_, OL, 3, False); line([(24, -338), (4, -232)], OL, 3, False)
    # collar points (flipped out)
    poly([(-50, -352), (-20, -336), (-34, -300), (-66, -318)], WHT, OL, 4)
    poly([(50, -352), (20, -336), (34, -300), (66, -318)], WHT, OL, 4)
    # gold chain + coin
    ch = catmull([(-30, -340), (-18, -296), (0, -272), (18, -296), (30, -340)])
    line(ch, GOLDD, 7, False); line(ch, GOLD, 4, False)
    ell(0, -264, 12, 12, GOLD, GOLDD, 3); ell(-3, -267, 4, 4, (255, 245, 200), None)
    # satin peak lapels
    poly([(-52, -350), (-112, -332), (-96, -230), (-42, -214), (-18, -240), (-40, -300)], (52, 48, 70), OL, 4)
    poly([(52, -350), (112, -332), (96, -230), (42, -214), (18, -240), (40, -300)], (52, 48, 70), OL, 4)
    line([(-100, -322), (-70, -240)], (120, 116, 150), 5, False); line([(100, -322), (70, -240)], (120, 116, 150), 5, False)
    # untied bow tie draped on the collar
    poly([(-30, -330), (-6, -322), (-10, -306), (-34, -312)], (16, 14, 20), OL, 3)
    poly([(30, -330), (6, -322), (10, -306), (34, -312)], (16, 14, 20), OL, 3)
    poly([(-8, -326), (8, -326), (6, -300), (-6, -300)], (16, 14, 20), OL, 3)
    poly([(-8, -300), (-24, -258), (-14, -254), (0, -290)], (16, 14, 20), OL, 3)
    poly([(8, -300), (28, -262), (18, -256), (2, -290)], (16, 14, 20), OL, 3)
    # pocket square + boutonniere
    poly([(54, -258), (82, -262), (86, -240), (60, -236)], (26, 24, 38), OL, 3)
    poly([(58, -258), (66, -276), (74, -258)], (255, 150, 190), OL, 2); poly([(68, -258), (78, -274), (84, -258)], WHT, OL, 2)
    # buttons
    ell(-12, -176, 6, 6, GOLD, GOLDD, 2); ell(12, -176, 6, 6, GOLD, GOLDD, 2)
    line([(-96, -124), (-4, -136)], (60, 56, 80), 3, False); line([(96, -124), (4, -136)], (60, 56, 80), 3, False)
    line([(-70, -176), (-54, -130)], (60, 56, 80), 3, False); line([(70, -176), (54, -130)], (60, 56, 80), 3, False)

    # ================= cat head =================
    HY[0] = -34 + P.get("hy", 0.0); HA[0] = math.radians(P["hr"])
    head = catmull([(-70, -566), (-112, -540), (-128, -490), (-118, -430), (-80, -388), (0, -372), (80, -388), (118, -430), (128, -490), (112, -540), (70, -566), (0, -574), (-70, -566)], 6)
    ear = P.get("ear", 0.0)
    for sg in (-1, 1):
        fl = ear*(1 if sg > 0 else 0)*8
        poly([(sg*124, -516), (sg*(122 + fl), -616 + fl*0.6), (sg*52, -562)], ORG, OL, 6)
        poly([(sg*106, -534), (sg*(108 + fl*0.7), -590 + fl*0.5), (sg*72, -558)], PNK, None)
    poly(head, ORG, OL, 6)
    for sg in (-1, 1):
        poly([(sg*124, -470), (sg*146, -462), (sg*128, -448)], ORG, OL, 4); poly([(sg*118, -440), (sg*140, -428), (sg*120, -420)], ORG, OL, 4)
    for x_, h_ in ((0, 38), (-24, 28), (24, 28)): line([(x_, -566), (x_*1.1, -566+h_)], ORGD, 7)
    ell(-30, -418, 42, 30, CREAM, None); ell(30, -418, 42, 30, CREAM, None); ell(0, -396, 34, 18, CREAM, None)
    # blush (clipped to the head)
    bw = P["blush"]
    if bw > 0.02:
        bl = Image.new("L", big.size, 0); bd_ = ImageDraw.Draw(bl)
        for sgn in (-1, 1):
            q = [T(sgn*88 + 20*bw*math.cos(a), -452 + 12*bw*math.sin(a)) for a in np.linspace(0, 2*math.pi, 24, endpoint=False)]
            bd_.polygon(q, fill=int(170*min(1, bw)))
        bm = Image.new("L", big.size, 0); ImageDraw.Draw(bm).polygon([T(*pt_) for pt_ in head], fill=255)
        big.paste((246, 120, 135), mask=ImageChops.multiply(bl, bm).filter(ImageFilter.GaussianBlur(3))); d = ImageDraw.Draw(big)
    # slicked quiff (sways)
    qs = math.sin(t*3.1)*3 + P.get("talk", 0)*2
    qc = catmull([(-30, -566), (-8, -606), (26, -634), (70 + qs, -638), (102 + qs*1.6, -618)])
    ribbon(qc, list(np.interp(np.linspace(0, 1, len(qc)), [0, .3, .65, 1], [34, 46, 36, 8])), ORG, OL, 5)
    line([(p[0]-4, p[1]+6) for p in qc[6:-8]], (255, 190, 110), 5, False)
    # eyes
    ex, ey = 52, -490
    lk, lv = P["look"], P["lookv"]
    for sg in (-1, 1):
        cl = max(P["blink"], P["wink"] if sg == 1 else 0.0)
        if cl > 0.88:
            line(catmull([(sg*ex-26, ey+5), (sg*ex, ey-9 + 3*(1-cl)), (sg*ex+26, ey+5)], 6), OL, 6, True); continue
        ell(sg*ex, ey, 30, 27, (255, 252, 226), OL, 4)
        ix = sg*ex + 6*(1-abs(lk)*0.3) + lk*10; iy = ey + 3 + lv*4
        ell(ix, iy, 19, 22, (110, 200, 90), None)
        ell(ix, iy, 6 + 2*max(0, P["lid"]-0.4), 19, BLK, None); ell(ix+6, iy-9, 5, 5, WHT, None)
        lid = P["lid"] + (1 - P["lid"])*cl
        poly([(sg*ex-33, ey-32), (sg*ex+33, ey-32), (sg*ex+33, ey-32+lid*58), (sg*ex-33, ey-32+lid*58)], ORG, None)
        line([(sg*ex-30, ey-32+lid*58), (sg*ex+30, ey-32+lid*58)], OL, 6, False)
    br, bl_ = P["brow"], P["browl"]
    line([(-ex-30, ey-44 - bl_*8), (-ex+28, ey-50 - bl_*16)], ORGD, 9)
    line([(ex-28, ey-58 + 8*(1-br)), (ex+4, ey-72 - 10*br), (ex+30, ey-58 - 6*br)], ORGD, 9)
    # nose
    poly([(-13, -440), (13, -440), (0, -424)], PNK, OL, 4)
    line([(0, -424), (0, -414)], OL, 5, False)
    # mouth: closed "w", smirk, grin, talk
    sm, gr, o = P["smirk"], P["grin"], P["talk"]
    mwv = (1 + 0.16*gr) * (1 + 0.10*cen_at(t)*(1 if o > 0.08 else 0))
    cl_y = -414 - gr*9
    Lc = (-46*mwv, cl_y + sm*3*0 + 2*sm); Rc = (50*mwv, -418 - 12*sm - gr*9)
    upL = catmull([Lc, (-26*mwv, -402 - gr*2), (0, -414)], 6)
    upR = catmull([(0, -414), (28*mwv, -400 - gr*2), Rc], 6)
    if o > 0.08 or gr > 0.5:
        oo = max(o, gr*0.35)
        lo = catmull([Rc, (34*mwv, -400 + oo*20), (0, -398 + oo*28), (-34*mwv, -400 + oo*20), Lc], 6)
        poly(upL + upR + lo, (96, 12, 22), None)
        if oo > 0.25: ell(0, -392 + oo*20, 18, 5 + oo*6, (232, 96, 112), None)
        line(upL + upR, OL, 6)
        line(lo, OL, 5, False)
        poly([(-30*mwv, -404), (-20*mwv, -405), (-25*mwv, -391 + oo*6)], WHT, OL, 2)
    else:
        line(upL, OL, 6); line(upR, OL, 6)
    poly([(20*mwv, -402), (32*mwv, -404), (27*mwv, -388 + o*6)], WHT, OL, 2)
    ell(8, -396 + o*8, 3, 3, GOLD, None)
    if P["grin"] > 0.6:        # twinkle on the fang
        tw = 0.5 + 0.5*math.sin(t*14)
        line([(27*mwv-9*tw, -391), (27*mwv+9*tw, -391)], WHT, 2.5, False); line([(27*mwv, -391-9*tw), (27*mwv, -391+9*tw)], WHT, 2.5, False)
    # whiskers (twitch)
    for sg in (-1, 1):
        for wi, (x1, y1) in enumerate(((150, -450), (158, -428), (148, -406))):
            tw_ = math.sin(t*6 + wi + sg)*2*(0.4 + o)
            ln_ = [(sg*54, -424), (sg*x1, y1 + tw_)]
            line(ln_, OL, 5, False); line(ln_, (250, 238, 214), 2.5, False)
    ell(-120, -519, 10, 13, None, GOLD, 3.5)    # gold hoop
    HY[0] = 0; HA[0] = 0.0

    # ================= right arm + champagne flute (sip) =================
    sp = P["sip"]
    hx, hy_ = 138 + 38*sp, -388 + 36*sp
    ex_, ey_ = 170 + 8*sp, -262 - 14*sp
    line([(92, -326), (ex_, ey_), (hx, hy_)], (24, 22, 34), 44)
    th = math.radians(58*sp)
    def GPt(x, y):
        x0, y0 = x - 138, y + 388
        return (hx + x0*math.cos(th) + y0*math.sin(th), hy_ - x0*math.sin(th) + y0*math.cos(th))
    def gpoly(pts, fill=None, outline=None, w=3):
        poly([GPt(*p) for p in pts], fill, outline, w)
    def gline(pts, col, w): line([GPt(*p) for p in pts], col, w, False)
    GX = 134
    gpoly([(GX-16, -470), (GX+16, -470), (GX+12, -520), (GX-12, -520)], (250, 225, 140))
    gpoly([(GX-16, -470), (GX+16, -470), (GX+13, -504), (GX-13, -504)], (244, 196, 80))
    gline([(GX-17, -470), (GX-13, -560), (GX+13, -560), (GX+17, -470), (GX+8, -420), (GX-8, -420), (GX-17, -470)], (255, 255, 255), 3)
    gline([(GX-6, -420), (GX-6, -396)], (235, 240, 250), 4); gline([(GX, -396), (GX, -380)], (235, 240, 250), 4)
    gline([(GX-20, -380), (GX+20, -380)], (235, 240, 250), 6)
    gline([(GX-10, -548), (GX-10, -498)], (255, 255, 255), 3)
    for bi in range(4):
        by_ = -474 - ((t*20 + bi*11) % 44); bx_ = GX + (-6 if bi % 2 else 5)
        if by_ > -516: ell(*GPt(bx_, by_), 2.4, 2.4, (255, 250, 230), None) if False else poly([GPt(bx_-2, by_-2), GPt(bx_+2, by_-2), GPt(bx_+2, by_+2), GPt(bx_-2, by_+2)], (255, 250, 230), None)
    poly([GPt(158, -386), GPt(178, -386), GPt(178, -352), GPt(158, -352)], GOLD, OL, 3)
    ell(hx, hy_, 28, 26, ORG)
    ell(hx, hy_ + 8, 20, 16, CREAM, None)
    line([(hx-12, hy_-8), (hx-6, hy_+10)], OL, 3, False); line([(hx+2, hy_-10), (hx+6, hy_+10)], OL, 3, False)
    ell(hx + 20, hy_ - 14, 10, 12, ORG, OL, 3)

    # hearts
    if P.get("hu") is not None:
        def heart(x, y, s_, col):
            pts = []
            for u in np.linspace(0, 2*math.pi, 40):
                pts.append((x + 16*math.sin(u)**3*s_, y - (13*math.cos(u) - 5*math.cos(2*u) - 2*math.cos(3*u) - math.cos(4*u))*s_))
            d.polygon([T(*p) for p in pts], fill=col)
        for n_, (hx0, hy0, s0) in enumerate([(130, -520, 3.0), (-150, -470, 2.4), (170, -400, 2.0), (-110, -600, 1.8), (20, -640, 2.2)]):
            u = P["hu"] - n_*0.12
            if u > 0: heart(hx0 + math.sin(u*5+n_)*10, hy0 - u*70, s0*min(1, u*4), (255, 70, 110))
    return big

_VIG = {}
def finish(img, P, t):
    if "v" not in _VIG:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        _VIG["v"] = (1 - 0.34*np.clip(((xx-W/2)/(W*0.62))**2 + ((yy-H*0.5)/(H*0.62))**2, 0, 1))[..., None]
    a = np.asarray(img.resize((W, H), Image.LANCZOS).convert("RGB")).astype(np.float32)*_VIG["v"]
    fl_ = P.get("flash", 0.0); a = a*P.get("fade", 1.0)*(1-fl_) + 255*fl_
    a = np.clip(a, 0, 255).astype(np.uint8)
    im = Image.fromarray(a)
    if P.get("blur", 0) > 0.2: im = im.filter(ImageFilter.GaussianBlur(P["blur"]))
    return im
