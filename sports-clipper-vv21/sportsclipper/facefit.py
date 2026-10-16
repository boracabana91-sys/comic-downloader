"""vv21: find the face in a player photo, judge it, and crop every player the same way.

Every thumbnail face is levelled (eyes on a horizontal line), sized to the same share of its panel and placed
with the eyes on the same line, so the two players always look equally proportioned. Photos where the player
looks sideways, up or down, has a tilted head, a tiny or blurry face, or a face cut by the edge are rejected
and the next photo is used."""
from __future__ import annotations
import math
import os
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "models", "face_detection_yunet_2023mar.onnx")

FACE_SHARE = 0.60        # face (YuNet box) width as a share of the panel width
EYE_LINE = 0.37          # the eyes sit this far down the panel
MIN_FACE_PX = 110        # smaller than this in the source would be blown up too much
MAX_YAW = 0.42           # |nose offset from the eye midpoint| / eye distance
MAX_ROLL = 14.0          # degrees of head tilt we level out; more than this is rejected
PITCH_RANGE = (0.55, 1.35)   # (eyes -> nose) / (nose -> mouth): outside = looking up / down


def _bg(path: str):
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
    bg.alpha_composite(im)
    return im, cv2.cvtColor(np.asarray(bg.convert("RGB")), cv2.COLOR_RGB2BGR)


@lru_cache(maxsize=1)
def _detector():
    return cv2.FaceDetectorYN.create(MODEL, "", (320, 320), 0.6, 0.3, 5000)


def analyse(path: str) -> dict:
    """{'ok': bool, 'why': str, 'score': float, 'box': (x,y,w,h), 'eyes': ((x,y),(x,y)), 'roll': deg, ...}"""
    try:
        im, bgr = _bg(path)
    except Exception as e:
        return {"ok": False, "why": f"cannot open ({e})", "score": 0.0}
    det = _detector()
    det.setInputSize((bgr.shape[1], bgr.shape[0]))
    _, r = det.detect(bgr)
    if r is None or len(r) == 0:
        return {"ok": False, "why": "no face found", "score": 0.0}
    r = sorted(r, key=lambda a: a[2] * a[3], reverse=True)[0]
    x, y, w, h = (float(v) for v in r[:4])
    re_, le_, nose = (r[4], r[5]), (r[6], r[7]), (r[8], r[9])
    mouth = ((r[10] + r[12]) / 2, (r[11] + r[13]) / 2)
    # YuNet's "right eye" is the one on the left of the picture
    (ex1, ey1), (ex2, ey2) = sorted([re_, le_], key=lambda p: p[0])
    d = math.hypot(ex2 - ex1, ey2 - ey1) or 1.0
    mid = ((ex1 + ex2) / 2, (ey1 + ey2) / 2)
    yaw = (nose[0] - mid[0]) / d
    roll = math.degrees(math.atan2(ey2 - ey1, ex2 - ex1))
    n2m = max(1e-6, mouth[1] - nose[1])
    pitch = (nose[1] - mid[1]) / n2m
    sharp = float(cv2.Laplacian(cv2.cvtColor(bgr[int(max(0, y)):int(y + h), int(max(0, x)):int(x + w)],
                                             cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
    out = {"box": (x, y, w, h), "eyes": ((ex1, ey1), (ex2, ey2)), "yaw": yaw, "roll": roll, "pitch": pitch,
           "sharp": sharp, "size": im.size, "conf": float(r[14]), "face_px": w}
    why = ""
    if w < MIN_FACE_PX:
        why = f"face only {int(w)} px wide"
    elif abs(yaw) > MAX_YAW:
        why = "head turned sideways"
    elif not PITCH_RANGE[0] <= pitch <= PITCH_RANGE[1]:
        why = "looking up or down"
    elif abs(roll) > MAX_ROLL:
        why = "head tilted"
    elif x < -0.05 * w or y < -0.1 * h or x + w > im.width * 1.02 or y + h > im.height * 1.02:
        why = "face cut by the edge"
    elif sharp < 60:
        why = "face too blurry"
    out["ok"], out["why"] = (not why), why or "good"
    out["score"] = (0 if why else 1.0) * (0.45 * min(w / 260, 1) + 0.25 * min(sharp / 400, 1) +
                                           0.20 * (1 - min(abs(yaw) / MAX_YAW, 1)) + 0.10 * (1 - min(abs(roll) / MAX_ROLL, 1)))
    return out


def fit(path: str, out_w: int, out_h: int, info: dict | None = None) -> Image.Image:
    """The photo levelled and cropped to out_w x out_h: face FACE_SHARE of the width, eyes on EYE_LINE.
    Transparent where the photo ends (the team colour shows through)."""
    info = info or analyse(path)
    im, _ = _bg(path)
    (ex1, ey1), (ex2, ey2) = info["eyes"]
    cx, cy = (ex1 + ex2) / 2, (ey1 + ey2) / 2
    scale = (FACE_SHARE * out_w) / info["box"][2]
    # affine: rotate about the eye midpoint to level the eyes, scale, then move the eyes to their target spot
    ang = info["roll"]
    M = cv2.getRotationMatrix2D((cx, cy), ang, scale)
    M[0, 2] += out_w / 2 - cx
    M[1, 2] += EYE_LINE * out_h - cy
    arr = cv2.warpAffine(np.asarray(im), M, (out_w, out_h), flags=cv2.INTER_LANCZOS4,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    return Image.fromarray(arr, "RGBA")


def pick(paths: list, prefer: str | None = None):
    """The photo to use: `prefer` if it passes, else the best-scoring photo that passes, else the best of the rest.
    Returns (path, info)."""
    seen = []
    if prefer:
        i = analyse(prefer)
        if i["ok"]:
            return prefer, i
        seen.append((prefer, i))
    for p in paths:
        if p != prefer:
            seen.append((p, analyse(p)))
    good = [(p, i) for p, i in seen if i["ok"]]
    if good:
        return max(good, key=lambda t: t[1]["score"])
    return (max(seen, key=lambda t: t[1].get("face_px", 0)) if seen else (None, {}))
