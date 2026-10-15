"""Render the cut list to every resolution in a single decode pass.

Video and audio are cut with select/aselect so they stay in sync; the audio is never
re-mixed, filtered or loudness-changed - only re-encoded to AAC.
"""
from __future__ import annotations
import os
import platform
import subprocess
import tempfile

from . import media


def pick_encoder(pref: str) -> str:
    if pref != "auto":
        return pref
    if platform.system() == "Darwin":
        return "h264_videotoolbox"      # Mac hardware encoder: much lower CPU/heat
    return "libx264"


def ladder(src_h: int, wanted: list, allow_upscale: bool) -> list:
    hs = sorted({h for h in wanted if allow_upscale or h <= src_h}, reverse=True)
    return hs or [src_h]


def _bitrate(h: int) -> str:
    return {2160: "20M", 1440: "12M", 1080: "6M", 720: "3M", 480: "1500k"}.get(h, "800k")


def render(path: str, segments: list, info: dict, cfg: dict, out_base: str, log=print) -> dict:
    """Returns {height: output_path}."""
    if not segments:
        raise RuntimeError("no live play found - nothing to render")
    hs = ladder(info["height"], cfg["resolutions"], cfg["allow_upscale"])
    enc = pick_encoder(cfg["encoder"])
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in segments)
    fc = [f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB,split={len(hs)}" + "".join(f"[s{h}]" for h in hs)]
    for h in hs:
        fc.append(f"[s{h}]scale=-2:{h}:flags=lanczos,format=yuv420p[v{h}]")
    if info["has_audio"]:
        fc.append(f"[0:a]aselect='{expr}',asetpts=N/SR/TB[a]" + ";[a]asplit=%d%s" % (len(hs), "".join(f"[a{h}]" for h in hs)))
    os.makedirs(os.path.dirname(out_base), exist_ok=True)
    outs = {h: f"{out_base}_{h}p.mp4" for h in hs}
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(";".join(fc)); script = f.name

    def build(enc):
        cmd = [media.need("ffmpeg"), "-v", "error", "-y", "-i", path, "-filter_complex_script", script]
        for h in hs:
            cmd += ["-map", f"[v{h}]"]
            if info["has_audio"]:
                cmd += ["-map", f"[a{h}]"]
            br = _bitrate(h)
            if enc == "libx264":
                cap = str(int(float(br[:-1]) * (1000 if br.endswith("M") else 1))) + "k"
                cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", cap, "-bufsize", f"{2 * int(cap[:-1])}k"]
            else:
                cmd += ["-c:v", enc, "-b:v", br]
            cmd += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", outs[h]]
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
