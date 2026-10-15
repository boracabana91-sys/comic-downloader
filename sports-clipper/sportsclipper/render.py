"""Render the cut list to every chosen resolution in one decode pass.

Quality rules:
- Sizes at or below the source use Lanczos scaling.
- Sizes ABOVE the source are upscaled with Lanczos plus a light sharpen, and their file
  name says "_upscaled". They are sharper than a plain stretch, but they cannot add detail
  that the source never had. Real 1080p needs a 1080p source.
- libx264 by default (more detail per megabit than the Mac hardware encoder). CRF is set per size.
- Audio is only re-encoded to AAC; it is never re-mixed or loudness-changed.
"""
from __future__ import annotations
import os
import tempfile

from . import media

CRF = {2160: 18, 1440: 19, 1080: 20, 720: 21, 480: 22, 360: 23}
AUDIO = {2160: "320k", 1440: "256k", 1080: "256k", 720: "192k", 480: "160k", 360: "128k"}
BITRATE = {2160: "20M", 1440: "12M", 1080: "8M", 720: "4M", 480: "2M", 360: "1M"}   # hardware encoder only


def pick_encoder(pref: str) -> str:
    return "libx264" if pref in ("auto", "", None) else pref


def ladder(src_h: int, wanted: list, allow_upscale: bool) -> list:
    hs = sorted({h for h in wanted if allow_upscale or h <= src_h}, reverse=True)
    return hs or [src_h]


def is_upscale(h: int, src_h: int) -> bool:
    return h > src_h


def render(path: str, segments: list, info: dict, cfg: dict, out_base: str, log=print) -> dict:
    """Returns {height: output_path}."""
    if not segments:
        raise RuntimeError("no live play found - nothing to render")
    src_h = info["height"]
    hs = ladder(src_h, cfg["resolutions"], cfg["allow_upscale"])
    enc = pick_encoder(cfg["encoder"])
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in segments)
    fc = [f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB,split={len(hs)}" + "".join(f"[s{h}]" for h in hs)]
    for h in hs:
        chain = f"[s{h}]scale=-2:{h}:flags=lanczos"
        if is_upscale(h, src_h):
            chain += ",unsharp=5:5:0.8:5:5:0.0"
        fc.append(chain + f",format=yuv420p[v{h}]")
    if info["has_audio"]:
        fc.append(f"[0:a]aselect='{expr}',asetpts=N/SR/TB[a];[a]asplit={len(hs)}" + "".join(f"[a{h}]" for h in hs))
    os.makedirs(os.path.dirname(out_base), exist_ok=True)
    outs = {h: f"{out_base}_{h}p{'_upscaled' if is_upscale(h, src_h) else ''}.mp4" for h in hs}
    for h in hs:
        if is_upscale(h, src_h):
            log(f"{h}p is upscaled from your {src_h}p source: sharper than a plain stretch, but not real {h}p detail")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(";".join(fc)); script = f.name

    def build(codec):
        cmd = [media.need("ffmpeg"), "-v", "error", "-y", "-i", path, "-filter_complex_script", script]
        for h in hs:
            cmd += ["-map", f"[v{h}]"]
            if info["has_audio"]:
                cmd += ["-map", f"[a{h}]"]
            if codec == "libx264":
                cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(CRF.get(h, 22)), "-profile:v", "high"]
            else:
                cmd += ["-c:v", codec, "-b:v", BITRATE.get(h, "1M")]
            cmd += ["-c:a", "aac", "-b:a", AUDIO.get(h, "160k"), "-movflags", "+faststart", outs[h]]
        return cmd

    log(f"rendering {', '.join(f'{h}p' for h in hs)} with {enc} ...")
    try:
        try:
            media.run(build(enc))
        except RuntimeError:
            if enc == "libx264":
                raise
            log(f"{enc} not available, using the software encoder")
            media.run(build("libx264"))
    finally:
        os.unlink(script)
    return outs
