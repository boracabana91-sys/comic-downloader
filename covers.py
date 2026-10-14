"""Cover picture tools.

- fit_cover: turns your picture into page 1 of a Kobo/Kindle/other file.
- save_folder_cover: saves your picture as cover.jpg inside a folder.
- set_folder_icon: makes the folder itself show your picture (Mac and Windows).
"""
import json
import math
import os
import subprocess
import sys

try:
    from PIL import Image
    HAS_PIL = True
except Exception:  # pragma: no cover
    HAS_PIL = False

COVER_NAME = "cover.jpg"
COVER_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_cover_file(path):
    """True if the path is a picture we can use as a cover."""
    if not HAS_PIL or not path or not os.path.isfile(path):
        return False
    if os.path.splitext(path)[1].lower() not in COVER_EXTS:
        return False
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def load_cover(path):
    with Image.open(path) as opened:
        opened.load()
        if opened.mode in ("RGBA", "LA") or (opened.mode == "P" and "transparency" in opened.info):
            rgba = opened.convert("RGBA")
            bg = Image.new("RGB", rgba.size, "white")
            bg.paste(rgba, mask=rgba.split()[3])
            return bg
        return opened.convert("RGB")


def _edge_color(im):
    w, h = im.size
    pts = [im.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    return tuple(sum(c[i] for c in pts) // 4 for i in range(3))


def fit_cover(cover_path, width, height, gray, out_path):
    """The whole picture, fitted to the screen size (nothing cropped), as a JPEG."""
    im = load_cover(cover_path)
    scale = min(width / im.width, height / im.height)
    nw, nh = max(1, round(im.width * scale)), max(1, round(im.height * scale))
    bg = _edge_color(im)
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (width, height), bg)
    canvas.paste(im, ((width - nw) // 2, (height - nh) // 2))
    if gray:
        canvas = canvas.convert("L")
    canvas.save(out_path, "JPEG", quality=90)
    return out_path


def save_folder_cover(folder, cover_path):
    """Saves your picture as cover.jpg in the folder. Returns its path."""
    im = load_cover(cover_path)
    im.thumbnail((1200, 1200), Image.LANCZOS)
    dest = os.path.join(folder, COVER_NAME)
    im.save(dest, "JPEG", quality=90)
    return dest


def _square_icon(cover_path, size, out_path, fmt="PNG", **kw):
    im = load_cover(cover_path)
    im.thumbnail((size, size), Image.LANCZOS)
    sq = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sq.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    sq.save(out_path, fmt, **kw)


def _mac_icon(folder, cover_path):
    import tempfile
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        png = os.path.join(tmp, "icon.png")
        _square_icon(cover_path, 512, png)
        for call in ("setIconForFileOptions", "setIcon_forFile_options_"):
            script = ("ObjC.import('AppKit');"
                      f"var img = $.NSImage.alloc.initWithContentsOfFile({json.dumps(png)});"
                      f"var ok = $.NSWorkspace.sharedWorkspace.{call}(img, {json.dumps(folder)}, 0);"
                      "ok ? 'ok' : 'fail';")
            try:
                r = subprocess.run(["osascript", "-l", "JavaScript", "-e", script],
                                   capture_output=True, text=True, timeout=30)
            except Exception:
                return False
            if r.returncode == 0 and r.stdout.strip() == "ok":
                return True
    return False


def _win_attrib(*args):
    subprocess.run(["attrib", *args], capture_output=True, creationflags=_NO_WINDOW, timeout=30)


def _win_icon(folder, cover_path):
    ico = os.path.join(folder, "cover.ico")
    ini = os.path.join(folder, "desktop.ini")
    for p in (ico, ini):
        if os.path.exists(p):
            _win_attrib("-h", "-s", p)
    _square_icon(cover_path, 256, ico, "ICO",
                 sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    with open(ini, "w", encoding="utf-8") as f:
        f.write("[.ShellClassInfo]\r\nIconResource=cover.ico,0\r\n")
    _win_attrib("+h", "+s", ini)
    _win_attrib("+h", ico)
    _win_attrib("+s", folder)
    return True


def set_folder_icon(folder, cover_path):
    """Makes the folder show your picture. True if it worked (Mac and Windows only)."""
    try:
        if sys.platform == "darwin":
            return _mac_icon(folder, cover_path)
        if sys.platform.startswith("win"):
            return _win_icon(folder, cover_path)
    except Exception:
        return False
    return False


def apply_folder_covers(out_root, title, total, size, cover_path):
    """Cover picture + folder thumbnail for every 'Title - Pages A-B' folder of a chapter.
    Returns {'folders': n, 'icons': n_that_got_a_thumbnail, 'problems': [...]}."""
    import core
    res = {"folders": 0, "icons": 0, "problems": []}
    for g in range(math.ceil(total / size)):
        folder = os.path.join(out_root, core.group_folder_name(title, g * size + 1, total, size))
        if not os.path.isdir(folder):
            continue
        try:
            save_folder_cover(folder, cover_path)
            res["folders"] += 1
        except Exception as e:
            res["problems"].append(f"{os.path.basename(folder)}: {e}")
            continue
        if set_folder_icon(folder, cover_path):
            res["icons"] += 1
    return res
