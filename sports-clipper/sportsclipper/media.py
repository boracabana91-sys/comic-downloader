"""ffmpeg / ffprobe helpers."""
from __future__ import annotations
import json
import shutil
import subprocess


def need(tool: str) -> str:
    p = shutil.which(tool)
    if not p:
        raise RuntimeError(f"{tool} not found. On Mac run: brew install ffmpeg")
    return p


def probe(path: str) -> dict:
    out = subprocess.run([need("ffprobe"), "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,width,height,r_frame_rate",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    v = next(s for s in j["streams"] if s.get("codec_type") == "video")
    num, den = (v.get("r_frame_rate") or "30/1").split("/")
    return {"duration": float(j["format"]["duration"]), "width": int(v["width"]),
            "height": int(v["height"]), "fps": float(num) / max(float(den), 1.0),
            "has_audio": any(s.get("codec_type") == "audio" for s in j["streams"])}


def run(cmd: list, log=None) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + (p.stderr or "")[-600:])
