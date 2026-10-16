"""Automatic thumbnail.

vv10: when both teams have a player cutout in the players folder, the thumbnail is the two star players
on opposite sides (team acronym over the player's alias). Otherwise it falls back to the photo style below.

Photo style (fallback) - reference style:

Reference look: full-colour action photo of a player, big yellow stacked team names with a black
outline on the left, a dark date band, and a duration badge bottom-right. Only the font is changed
(bold condensed). No colour grading or glow.

Player choice: among solo close-ups (one prominent face), pick the frame with the most movement
around the player and a sharp image, so the player is in an action moment, not standing still.
"""
from __future__ import annotations
import os
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


OUT = (1920, 1080)
W, H = OUT
YELLOW = (250, 214, 20)       # RGB, the reference's gold-yellow
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
HERE = os.path.dirname(os.path.abspath(__file__))

NBA = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
# First font found wins. Impact is on every Mac; the bundled font is the fallback.
FONT_FILES = [
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/Library/Fonts/Impact.ttf",
    os.path.join(HERE, "fonts", "DejaVuSansCondensed-Bold.ttf"),
]


# ---------- title parsing -------------------------------------------------
def parse_teams(title: str) -> list:
    """Team acronyms in the order they appear in the title. Understands full names ("Denver Nuggets"),
    short names ("Nuggets vs Clippers") and acronyms ("DEN vs LAC")."""
    from . import roster
    spots = {}

    def note(abbr, i):
        if i >= 0 and (abbr not in spots or i < spots[abbr]):
            spots[abbr] = i

    low = title.lower()
    for name, abbr in NBA.items():
        note(abbr, low.find(name.lower()))
    for abbr, (_full, nick, _c) in roster.TEAMS.items():
        m = re.search(r"(?<![A-Za-z])" + re.escape(nick) + r"(?![A-Za-z])", title, re.I)
        note(abbr, m.start() if m else -1)
        m = re.search(r"(?<![A-Za-z])" + abbr + r"(?![A-Za-z])", title)       # acronyms must be written in capitals
        note(abbr, m.start() if m else -1)
    return [a for a, _ in sorted(spots.items(), key=lambda kv: kv[1])][:2]


def parse_date(title: str) -> str:
    m = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})", title)
    return f"{m.group(1).upper()} {int(m.group(2))} {m.group(3)}" if m else ""


# ---------- finding the play ----------------------------------------------
def _face_detector():
    """Haar face detector. Needs OpenCV 4.x (requirements pin it; OpenCV 5 dropped these data files)."""
    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def closeups(path: str, n: int = 8, step_s: float = 4.0) -> list:
    """Solo close-ups ranked by movement around the player and sharpness.
    Returns [(score, frame, face_box_in_frame_coords)], best first."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cas = _face_detector()
    later = max(1, int(fps * 0.4))                          # second look, 0.4 s on, to measure movement
    cands = []
    margin = int(fps * 5)
    for i in range(margin, max(margin, total - margin - later), max(1, int(fps * step_s))):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        if not ok:
            break
        k = 640 / f.shape[1]
        small = cv2.resize(f, (640, int(f.shape[0] * k)))
        g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cas.detectMultiScale(g, 1.1, 6, minSize=(70, 70))
        if len(faces) == 0:
            continue
        faces = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)
        main = faces[0]
        if len(faces) > 1 and main[2] * main[3] < 4 * faces[1][2] * faces[1][3]:
            continue                                         # two big faces: not a solo shot
        ratio = main[2] / 640
        if not 0.10 <= ratio <= 0.40 or g.mean() < 25:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, i + later)
        ok2, f2 = cap.read()
        if not ok2:
            continue
        x, y, fw, fh = (int(v / k) for v in main)
        h_, w_ = f.shape[:2]
        x0, x1 = max(0, int(x - 1.5 * fw)), min(w_, int(x + 2.5 * fw))
        y0, y1 = max(0, int(y - 0.5 * fh)), h_
        a = cv2.cvtColor(f[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        b = cv2.cvtColor(f2[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        motion = float(np.abs(a - b).mean())                 # 0 = still, larger = more action
        sharp = cv2.Laplacian(g, cv2.CV_64F).var()
        score = 0.35 * min(motion / 20, 1) + 0.50 * min(sharp / 500, 1) + 0.15 * (1 - min(abs(ratio - 0.24) / 0.24, 1))
        cands.append((score, f.copy(), (x, y, fw, fh), motion))
    cap.release()
    cands.sort(key=lambda c: c[0], reverse=True)
    return [(s, fr, fc) for s, fr, fc, _ in cands[:n]], cands[:1]


def _center_frame(path: str):
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) // 2)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


# ---------- framing and photo ---------------------------------------------
def crop_169(frame, face):
    """16:9 crop that cuts off the broadcast scoreboard bar; player placed on the right for the text."""
    fh, fw = frame.shape[:2]
    cw = min(fw, fh * 16 / 9)
    ch = cw * 9 / 16
    if ch > 0.72 * fh:
        ch = 0.72 * fh
        cw = ch * 16 / 9
    if face is None:
        x0, y0 = (fw - cw) / 2, (fh - ch) / 2
    else:
        fx, fy, fwid, fhei = face
        x0 = fx + fwid / 2 - 0.64 * cw
        y0 = fy + fhei / 2 - 0.40 * ch
        x0 = min(max(0, x0), fw - cw)
        y0 = min(max(0, y0), 0.72 * fh - ch)           # stay above the scoreboard bar
    x0, y0 = int(x0), int(y0)
    return frame[y0:y0 + int(ch), x0:x0 + int(cw)], x0, y0


def photo_look(bgr):
    """Keep the photo natural: a little contrast and colour, and darken the left side so the text reads."""
    f = bgr.astype(np.float32) / 255.0
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.08, 0, 255)
    f = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) / 255.0
    f = np.clip((f - 0.5) * 1.06 + 0.5, 0, 1)
    xx = np.linspace(0, 1, f.shape[1], dtype=np.float32)[None, :]
    shade = 1 - 0.45 * np.clip((0.55 - xx) / 0.55, 0, 1)
    return (np.clip(f * shade[..., None], 0, 1) * 255).astype(np.uint8)


# ---------- text (PIL, so the font can be swapped) -------------------------
def _font(size: int):
    for path in FONT_FILES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fit_font(text: str, max_w: int, start: int):
    size = start
    while size > 20:
        f = _font(size)
        if f.getlength(text) <= max_w:
            return f
        size -= 4
    return _font(20)


def score_line(title: str) -> str:
    """Final score from ESPN (stats.py), e.g. 'BOS 112 - 108 LAL'. Empty string if the game or feed is not found."""
    teams, date = parse_teams(title), parse_date(title)
    if len(teams) != 2 or not date:
        return ""
    try:
        from datetime import datetime
        from . import stats
        ymd = datetime.strptime(date.title(), "%B %d %Y").strftime("%Y%m%d")
        info = stats.game_info(ymd, teams)
    except Exception:
        return ""
    if not info:
        return ""
    return f"{info.away} {info.away_score} - {info.home_score} {info.home}"


def draw_text(rgb: np.ndarray, teams: list, date: str, duration_s: float, score: str = "") -> np.ndarray:
    img = Image.fromarray(rgb).convert("RGBA")
    d = ImageDraw.Draw(img)
    x, y = 90, 70
    if len(teams) == 2:
        big = _fit_font(max(teams, key=len), int(W * 0.46), 400)
        sw = max(6, big.size // 22)
        small = _font(int(big.size * 0.42))
        for text, f in ((teams[0], big), ("VS", small), (teams[1], big)):
            d.text((x, y), text, font=f, fill=YELLOW, stroke_width=sw, stroke_fill=BLACK)
            bbox = d.textbbox((x, y), text, font=f, stroke_width=sw)
            y = bbox[3] - sw * 2 + 8
    band = "   |   ".join(p for p in (date, score) if p)
    if band:
        f = _fit_font(band, int(W * 0.62), 64)
        x0, y0 = x - 14, y + 26
        bbox = d.textbbox((x0 + 14, y0 + 8), band, font=f)
        d.rectangle((x0, y0, bbox[2] + 16, bbox[3] + 14), fill=(0, 0, 0, 185))
        d.text((x0 + 14, y0 + 8), band, font=f, fill=YELLOW)
    m, s = divmod(int(round(duration_s)), 60)
    hh, m = divmod(m, 60)
    dur = f"{hh}:{m:02d}:{s:02d}" if hh else f"{m}:{s:02d}"
    f = _font(60)
    bbox = d.textbbox((0, 0), dur, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x1, y1 = W - 40, H - 40
    d.rectangle((x1 - tw - 40, y1 - th - 34, x1, y1), fill=(0, 0, 0, 215))
    d.text((x1 - tw - 20, y1 - th - 24), dur, font=f, fill=WHITE)
    return np.asarray(img.convert("RGB"))


# ---------- vv10: two star players, one on each side ------------------------
BAND_H = 100


def _cutout(path: str, max_h: int, max_w: int) -> Image.Image:
    """Transparent player image trimmed to the player and scaled to fit."""
    im = Image.open(path).convert("RGBA")
    box = im.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
    if box:
        im = im.crop(box)
    k = min(max_h / im.height, max_w / im.width)
    return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)


def _backdrop(colors: tuple) -> Image.Image:
    """Dark stage with a soft glow of each team's colour behind its player and a thin seam in the middle."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    img = np.empty((H, W, 3), np.float32)
    img[:] = (10, 12, 17)
    for cx, col in ((0.29 * W, colors[0]), (0.71 * W, colors[1])):
        d = np.sqrt(((xx - cx) / (0.50 * W)) ** 2 + ((yy - 0.58 * H) / (0.78 * H)) ** 2)
        g = np.clip(1 - d, 0, 1) ** 1.7 * 0.62
        for c in range(3):
            img[..., c] += g * col[c]
    vig = 1 - 0.35 * np.clip((np.abs(xx - W / 2) / (W / 2)) ** 3 + (np.abs(yy - H / 2) / (H / 2)) ** 3, 0, 1)
    img *= vig[..., None]
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    seam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(seam).line([(W * 0.545, 0), (W * 0.455, H)], fill=(255, 255, 255, 46), width=5)
    return Image.alpha_composite(out, seam)


def _place(canvas: Image.Image, cut: Image.Image, cx: float, bottom: int, color: tuple) -> None:
    """Shadow, a team-colour rim glow (hides rough cutout edges), then the player standing on the bottom band."""
    x = int(min(max(0, cx - cut.width / 2), W - cut.width))
    y = int(bottom - cut.height)
    a = cut.getchannel("A")
    pad = 60
    layer = Image.new("L", (cut.width + 2 * pad, cut.height + 2 * pad), 0)
    layer.paste(a, (pad, pad))
    glow = layer.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.8))
    shadow = layer.filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.65))
    for mask, rgb, dx, dy in ((shadow, (0, 0, 0), 14, 10), (glow, color, 0, 0)):
        canvas.paste(Image.new("RGB", mask.size, rgb), (x - pad + dx, y - pad + dy), mask)    # paste clips at the edges
    canvas.alpha_composite(cut, (x, y))


def _outlined(d, xy, text, font, fill, stroke):
    d.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=BLACK)


def versus_thumbnail(teams: list, stars: list, date: str, duration_s: float, score: str = "") -> np.ndarray:
    """teams = [ACR, ACR]; stars = [(cutout_png, name), (cutout_png, name)] in the same order. Returns RGB."""
    from . import roster
    colors = [roster.team_color(t) for t in teams]
    canvas = _backdrop(colors)
    bottom = H - BAND_H + 14
    d = ImageDraw.Draw(canvas)
    lay, text_bottom = [], 0                       # lay out acronym + alias first so the players fit below the text
    for i, (acr, (_, name)) in enumerate(zip(teams, stars)):
        cx = (0.29 if i == 0 else 0.71) * W
        big = _fit_font(acr, int(0.40 * W), 215)
        sw = max(6, big.size // 22)
        y = d.textbbox((cx, 22), acr, font=big, stroke_width=sw, anchor="ma")[3] - 6
        small = _fit_font(name, int(0.44 * W), 88)
        ssw = max(4, small.size // 18)
        text_bottom = max(text_bottom, d.textbbox((cx, y), name, font=small, stroke_width=ssw, anchor="ma")[3])
        lay.append((cx, acr, big, sw, y, name, small, ssw))
    max_h = max(300, bottom - (text_bottom + 14))
    for ((png, _), col), item in zip(zip(stars, colors), lay):
        _place(canvas, _cutout(png, min(int(0.64 * H), max_h), int(0.50 * W)), item[0], bottom, col)
    d = ImageDraw.Draw(canvas)
    for cx, acr, big, sw, y, name, small, ssw in lay:
        d.text((cx, 22), acr, font=big, fill=YELLOW, stroke_width=sw, stroke_fill=BLACK, anchor="ma")
        d.text((cx, y), name, font=small, fill=WHITE, stroke_width=ssw, stroke_fill=BLACK, anchor="ma")
    vs = _font(84)
    d.text((W / 2, 0.52 * H), "VS", font=vs, fill=WHITE, stroke_width=6, stroke_fill=BLACK, anchor="mm")
    # bottom band: date and score in the middle, duration on the right
    d.rectangle((0, H - BAND_H, W, H), fill=(0, 0, 0, 235))
    d.rectangle((0, H - BAND_H, W, H - BAND_H + 4), fill=YELLOW)
    band = "   |   ".join(p for p in (date, score) if p)
    if band:
        f = _fit_font(band, int(W * 0.62), 62)
        d.text((W / 2, H - BAND_H / 2 + 2), band, font=f, fill=YELLOW, anchor="mm")
    if duration_s and duration_s > 0:                    # no length yet in a preview made before the video exists
        m, sec = divmod(int(round(duration_s)), 60)
        hh, m = divmod(m, 60)
        dur = f"{hh}:{m:02d}:{sec:02d}" if hh else f"{m}:{sec:02d}"
        d.text((W - 40, H - BAND_H / 2 + 2), dur, font=_font(56), fill=WHITE, anchor="rm")
    return np.asarray(canvas.convert("RGB"))


def _stars_for(teams: list, log=print, picks: dict | None = None):
    """[(png, name), (png, name)] if both teams have a player cutout, else None.
    picks = {"DEN": "Jamal Murray"} - the player chosen in the window's drop-down (default player otherwise)."""
    from . import roster
    if len(teams) != 2:
        return None
    found, missing = [], []
    for t in teams:
        star = roster.find_star(t, choice=(picks or {}).get(t))
        (found if star else missing).append(star or t)
    if missing:
        log(f"thumbnail: no player picture for {', '.join(missing)} in {roster.players_dir()} - using the photo style")
        return None
    log(f"thumbnail: {teams[0]} {found[0][1]}  vs  {teams[1]} {found[1][1]}")
    return found



def make_thumbnail(path: str, title: str, duration_s: float, out: str, log=print, score: str | None = None,
                   picks: dict | None = None) -> str:
    if score is None:
        score = score_line(title)
        if score:
            log(f"thumbnail: final score {score}")
    teams = parse_teams(title)
    stars = _stars_for(teams, log, picks)
    if stars:
        rgb = versus_thumbnail(teams, stars, parse_date(title), duration_s, score)
        return _save_jpeg(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), out)
    cands, best = closeups(path)
    if cands:
        action, frame, face = cands[0]                      # (vv10 fix: this used to overwrite the final score)
        crop, _, _ = crop_169(frame, face)
        log(f"thumbnail: solo close-up from a live moment (action score {action:.2f})")
    else:
        frame = _center_frame(path)
        if frame is None:
            raise RuntimeError("could not read a frame for the thumbnail")
        crop, _, _ = crop_169(frame, None)
        log("no solo close-up found - the thumbnail uses a centre frame")
    base = cv2.resize(crop, OUT, interpolation=cv2.INTER_LANCZOS4)
    soft = cv2.GaussianBlur(base, (0, 0), 2.2)                 # sharpen the upscale: clear edges and faces
    base = cv2.addWeighted(base, 1.7, soft, -0.7, 0)
    rgb = cv2.cvtColor(photo_look(base), cv2.COLOR_BGR2RGB)
    rgb = draw_text(rgb, parse_teams(title), parse_date(title), duration_s, score)
    return _save_jpeg(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), out)


def preview_rgb(title: str, picks: dict | None = None, duration_s: float = 0, log=lambda m: None):
    """The two-star thumbnail straight from a title, with no video needed (for the window's live preview).
    Returns an RGB array, or None when the title does not name two teams that both have a picture."""
    teams = parse_teams(title)
    stars = _stars_for(teams, log, picks)
    if not stars:
        return None
    return versus_thumbnail(teams, stars, parse_date(title), duration_s, score_line(title))


def _save_jpeg(img, out: str) -> str:
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    for q in (92, 85, 75):                                   # YouTube thumbnails must stay under 2 MB
        cv2.imwrite(out, img, [cv2.IMWRITE_JPEG_QUALITY, q])
        if os.path.getsize(out) <= 2 * 1024 * 1024:
            break
    return out
