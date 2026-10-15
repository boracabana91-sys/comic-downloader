"""Automatic thumbnail, following the layout of the reference template:
big stacked team names with a gold outline on the left, a date band, a duration badge bottom-right,
and ONE player close-up on the right. Creative change from the template: grey smoke/haze is re-graded to ember red.

Method (no AI model, runs offline):
  1. Sample the video every few seconds.
  2. Keep frames with exactly one prominent face (solo), a close-up size, and a sharp image.
  3. Crop 16:9 around that face, grade it, add the text.
"""
from __future__ import annotations
import os
import re

import cv2
import numpy as np

OUT = (1920, 1080)
YELLOW = (58, 226, 240)          # BGR gold-yellow from the template
FONT = cv2.FONT_HERSHEY_DUPLEX

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
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def parse_teams(title: str) -> list:
    found = []
    for name, abbr in NBA.items():
        i = title.lower().find(name.lower())
        if i >= 0 and abbr not in [a for _, a in found]:
            found.append((i, abbr))
    return [a for _, a in sorted(found)][:2]


def parse_date(title: str) -> str:
    m = re.search(r"(" + MONTHS + r")\s+(\d{1,2}),?\s+(\d{4})", title)
    return f"{m.group(1).upper()} {int(m.group(2))} {m.group(3)}" if m else ""


def _face_detector():
    """Haar face detector. Needs OpenCV 4.x (requirements pin it; OpenCV 5 dropped these data files)."""
    xml = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    return cv2.CascadeClassifier(xml)


def best_closeup(path: str, step_s: float = 4.0):
    """Returns (score, frame, face_box_in_frame_coords) or (-1, None, None)."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cas = _face_detector()
    best = (-1.0, None, None)
    margin = int(fps * 5)
    for i in range(margin, max(margin, n - margin), max(1, int(fps * step_s))):
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
            continue                                   # two big faces: not a solo shot
        ratio = main[2] / 640                          # face width as a share of the frame
        if not 0.10 <= ratio <= 0.40 or g.mean() < 25:
            continue
        sharp = cv2.Laplacian(g, cv2.CV_64F).var()
        score = min(sharp, 600) / 600 * 0.6 + (1 - min(abs(ratio - 0.22) / 0.22, 1)) * 0.4
        if score > best[0]:
            best = (score, f.copy(), tuple(int(v / k) for v in main))
    cap.release()
    return best


def crop_169(frame, face):
    fh, fw = frame.shape[:2]
    cw = min(fw, fh * 16 / 9)
    ch = cw * 9 / 16
    if ch > 0.78 * fh:                                # zoom in a little so the scoreboard bar is cut off
        ch = 0.78 * fh
        cw = ch * 16 / 9
    if face is None:
        x0, y0 = (fw - cw) / 2, (fh - ch) / 2
    else:
        fx, fy, fwid, fhei = face
        x0 = fx + fwid / 2 - 0.62 * cw                # player on the right, text space on the left
        y0 = fy + fhei / 2 - 0.42 * ch
        x0 = min(max(0, x0), fw - cw)
        y0 = min(max(0, y0), fh - ch)
        if y0 + ch > 0.78 * fh:                       # keep the broadcast scoreboard bar out of the shot
            y0 = max(0, 0.78 * fh - ch)
    return frame[int(y0):int(y0 + ch), int(x0):int(x0 + cw)]


def grade(img):
    """Grey / hazy areas become ember red; skin and colour areas are left alone; light warm vignette."""
    f = img.astype(np.float32) / 255.0
    lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1].astype(np.float32) / 255.0
    protect = np.clip((0.85 - lum) / 0.30, 0.0, 1.0)     # bright whites (jerseys, lights) stay white
    m = (np.clip(1.0 - sat / 0.30, 0.0, 1.0) * protect * 0.65)[..., None]
    L = (lum ** 0.8)[..., None]
    ember = np.concatenate([0.12 * L, 0.32 * L, 1.0 * L], axis=2)     # BGR: ember red-orange
    out = f * (1 - m) + ember * m
    out[..., 2] = np.clip(out[..., 2] * 1.05, 0, 1)
    out = np.clip((out - 0.5) * 1.12 + 0.5, 0, 1)
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2
    vig = np.clip(1.15 - 0.30 * r2, 0.6, 1.0)[..., None]
    return (np.clip(out * vig, 0, 1) * 255).astype(np.uint8)


def _text(img, s, org, scale, thick, color=YELLOW):
    cv2.putText(img, s, org, FONT, scale, (0, 0, 0), thick + 10, cv2.LINE_AA)
    cv2.putText(img, s, org, FONT, scale, color, thick, cv2.LINE_AA)


def _fit(s, max_w, base, thick):
    (w, _), _ = cv2.getTextSize(s, FONT, base, thick)
    return base * min(1.0, max_w / max(w, 1))


def _dark_box(img, x0, y0, x1, y1, keep=0.28):
    img[y0:y1, x0:x1] = (img[y0:y1, x0:x1].astype(np.float32) * keep).astype(np.uint8)


def overlay(img, teams: list, date: str, duration_s: float):
    H, W = img.shape[:2]
    x, y = 60, 150
    max_w = int(W * 0.40)
    if len(teams) == 2:
        big = min(_fit(teams[0], max_w, 4.5, 10), _fit(teams[1], max_w, 4.5, 10))
        for line, sc, th in ((teams[0], big, 10), ("VS", big * 0.45, 6), (teams[1], big, 10)):
            (tw, th_px), _ = cv2.getTextSize(line, FONT, sc, th)
            _text(img, line, (x, y + th_px), sc, th)
            y += th_px + 28
    if date:
        sc = _fit(date, max_w, 1.5, 3)
        (tw, th_px), base = cv2.getTextSize(date, FONT, sc, 3)
        y0, y1 = y + 4, min(H - 1, y + th_px + base + 30)
        _dark_box(img, max(0, x - 16), y0, min(W - 1, x + tw + 16), y1)
        _text(img, date, (x, y + th_px + 14), sc, 3)
    m, s = divmod(int(round(duration_s)), 60)
    hh, m = divmod(m, 60)
    dur = f"{hh}:{m:02d}:{s:02d}" if hh else f"{m}:{s:02d}"
    (tw, th_px), base = cv2.getTextSize(dur, FONT, 1.4, 3)
    x1, y1 = W - 40, H - 40
    x0, y0 = x1 - tw - 40, y1 - th_px - base - 30
    _dark_box(img, x0, y0, x1, y1, keep=0.22)
    cv2.putText(img, dur, (x0 + 20, y1 - 18), FONT, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
    return img


def make_thumbnail(path: str, title: str, duration_s: float, out: str, log=print) -> str:
    score, frame, face = best_closeup(path)
    if frame is None:
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) // 2)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise RuntimeError("could not read a frame for the thumbnail")
        log("no solo close-up found - the thumbnail uses a centre frame")
    else:
        log("thumbnail: solo close-up picked")
    img = cv2.resize(crop_169(frame, face), OUT, interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(img, (0, 0), 3)
    img = cv2.addWeighted(img, 1.35, blur, -0.35, 0)            # crisp after the upscale
    img = grade(img)
    overlay(img, parse_teams(title), parse_date(title), duration_s)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    for q in (92, 85, 75):                                       # YouTube thumbnails must be under 2 MB
        cv2.imwrite(out, img, [cv2.IMWRITE_JPEG_QUALITY, q])
        if os.path.getsize(out) <= 2 * 1024 * 1024:
            break
    return out
