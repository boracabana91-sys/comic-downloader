"""ffmpeg helpers. Uses the ffmpeg bundled with the app (imageio-ffmpeg); falls back to one on PATH."""
from __future__ import annotations
import re
import shutil
import subprocess


def need(tool: str) -> str:
    if tool == "ffmpeg":
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    p = shutil.which(tool)
    if not p:
        raise RuntimeError(f"{tool} not found")
    return p


def probe(path: str) -> dict:
    """Read duration / size / audio from `ffmpeg -i` (no ffprobe needed)."""
    err = subprocess.run([need("ffmpeg"), "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    d = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    v = re.search(r"Video:.*?(?<![\w])(\d{2,5})x(\d{2,5})", err)
    if not d or not v:
        raise RuntimeError("could not read this video: " + err[-300:])
    fps = re.search(r"([\d.]+)\s*fps", err)
    return {"duration": int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3)),
            "width": int(v.group(1)), "height": int(v.group(2)),
            "fps": float(fps.group(1)) if fps else 30.0, "has_audio": "Audio:" in err}


def run(cmd: list, log=None) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + (p.stderr or "")[-600:])
