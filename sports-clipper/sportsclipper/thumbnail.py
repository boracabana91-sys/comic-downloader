"""Automatic thumbnail in the reference style.

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
from PIL import Image, ImageDraw, ImageFont

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
    found = []
    for name, abbr in NBA.items():
        i = title.lower().find(name.lower())
        if i >= 0 and abbr not in [a for _, a in found]:
            found.append((i, abbr))
    return [a for _, a in sorted(found)][:2]


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


def make_thumbnail(path: str, title: str, duration_s: float, out: str, log=print, score: str | None = None) -> str:
    if score is None:
        score = score_line(title)
        if score:
            log(f"thumbnail: final score {score}")
    cands, best = closeups(path)
    if cands:
        score, frame, face = cands[0]
        crop, _, _ = crop_169(frame, face)
        log(f"thumbnail: solo close-up from a live moment (action score {score:.2f})")
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
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    for q in (92, 85, 75):                                   # YouTube thumbnails must stay under 2 MB
        cv2.imwrite(out, img, [cv2.IMWRITE_JPEG_QUALITY, q])
        if os.path.getsize(out) <= 2 * 1024 * 1024:
            break
    return out
