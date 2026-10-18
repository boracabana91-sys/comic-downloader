"""Cover pictures and the chapter number on them.

stamp_cover is the one from Comic Series Downloader (bold dark numbers with a white edge,
about 7% of the cover's height, upper right), with three choices added: corner, size and
light or dark numbers. The cover is fitted whole on the screen with pagecore.fit_cover."""
import re

from PIL import ImageDraw, ImageFont

import pagecore

CORNERS = {"Upper right": "ur", "Upper left": "ul", "Lower right": "lr", "Lower left": "ll"}
SIZES = {"Small": 0.05, "Medium": 0.07, "Large": 0.10}
STYLES = {"Dark numbers, white edge": "dark", "White numbers, dark edge": "light"}
COVER_MODES = {"No cover": "none", "My cover picture": "picture",
               "Each book's first page": "first"}

_FONTS = ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
          "/System/Library/Fonts/Supplemental/Arial Black.ttf",
          "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf")

_KEYWORD = re.compile(r"(?:\b(?:chapter|chap|ch|episode|ep|part|vol|volume|book)|#)[\s._-]*"
                      r"(\d+(?:\.\d+)?)", re.I)
_LAST = re.compile(r"(\d+(?:\.\d+)?)(?!.*\d)")


def number_in(name):
    """The chapter number in a book name: 'Series - Chapter 052' -> '52', 'Ep 3.5' -> '3.5',
    'Solo Leveling 15' -> '15'. None when there is no number."""
    hits = _KEYWORD.findall(name)
    raw = hits[-1] if hits else None
    if raw is None:
        m = _LAST.search(name)
        raw = m.group(1) if m else None
    if raw is None:
        return None
    whole, _, frac = raw.partition(".")
    return str(int(whole)) + (f".{frac}" if frac and int(frac) else "")


def badge_text(names):
    """'#52' for one book, '#1-6' for several (first and last number)."""
    nums = [number_in(n) for n in names]
    nums = [n for n in nums if n]
    if not nums:
        return None
    if len(nums) == 1 or nums[0] == nums[-1]:
        return f"#{nums[0]}"
    return f"#{nums[0]}-{nums[-1]}"


def _font(px):
    for f in _FONTS:
        try:
            return ImageFont.truetype(f, px)
        except Exception:
            continue
    try:
        return ImageFont.load_default(px)
    except Exception:
        return ImageFont.load_default()


def stamp_cover(cover_path, text, out_path, corner="ur", size=0.07, style="dark"):
    """The cover picture with the number in a corner, readable on any picture."""
    im = pagecore.load_cover(cover_path).convert("RGB")
    w, h = im.size
    px = max(16, int(h * size))
    font = _font(px)
    d = ImageDraw.Draw(im)
    edge = max(2, px // 7)
    box = d.textbbox((0, 0), text, font=font, stroke_width=edge)
    while box[2] - box[0] > w * 0.45 and px > 12:   # long numbers like #112-120 stay modest
        px -= 2
        font = _font(px)
        edge = max(2, px // 7)
        box = d.textbbox((0, 0), text, font=font, stroke_width=edge)
    margin = int(w * 0.05)
    tw, th = box[2] - box[0], box[3] - box[1]
    x = w - margin - tw - box[0] if corner in ("ur", "lr") else margin - box[0]
    y = margin - box[1] if corner in ("ur", "ul") else h - margin - th - box[1]
    ink, rim = ((25, 25, 60), (255, 255, 255)) if style == "dark" else ((255, 255, 255), (20, 20, 20))
    d.text((x, y), text, font=font, fill=rim, stroke_width=edge, stroke_fill=rim)
    d.text((x, y), text, font=font, fill=ink, stroke_width=max(1, px // 28), stroke_fill=ink)
    im.save(out_path, "PNG")
    return out_path


def default_options():
    return {"mode": "none", "path": None, "number": True, "corner": "ur", "size": 0.07,
            "style": "dark"}
