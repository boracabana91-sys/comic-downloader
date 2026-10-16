"""Render the cut list to each chosen size.

Speed (0.9):
- On a Mac the Apple hardware encoder (VideoToolbox) is used, with hardware decoding. If it is not
  available or fails, the size is redone with libx264 automatically.
- One ffmpeg run per size, so the upload size can be made first and the rest afterwards, several at once.

Quality rules:
- The source frame rate is kept exactly (29.97 stays 29.97): no frames are dropped or repeated.
- Sizes at or below the source use Lanczos scaling.
- Sizes ABOVE the source are upscaled with Lanczos plus a light sharpen, and their file name says
  "_upscaled". They are sharper than a plain stretch, but cannot add detail the source never had.
- Bitrate is capped per size so files stay a sensible size and play smoothly.
- Audio is only re-encoded to AAC; it is never re-mixed or loudness-changed.
"""
from __future__ import annotations
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

from . import media, progress

CRF = {2160: 18, 1440: 19, 1080: 20, 720: 21, 480: 22, 360: 23}                        # libx264
X264_MAX = {2160: 16, 1440: 10, 1080: 6, 720: 3, 480: 1.6, 360: 0.9}                       # Mbit/s cap, libx264
VT_RATE = {2160: 20, 1440: 12, 1080: 7, 720: 3.5, 480: 1.8, 360: 1.0}                  # Mbit/s, hardware encoder
AUDIO = {2160: "256k", 1440: "256k", 1080: "192k", 720: "160k", 480: "128k", 360: "96k"}
HW = "h264_videotoolbox"


def pick_encoder(pref: str) -> str:
    if pref in ("auto", "", None):
        return HW if sys.platform == "darwin" else "libx264"
    return pref


def rate_str(fps: float) -> str:
    """Exact frame rate as ffmpeg wants it: 29.97 -> 30000/1001."""
    for num in (24000, 30000, 48000, 60000):
        if abs(fps - num / 1001) < 0.01:
            return f"{num}/1001"
    return f"{fps:.3f}".rstrip("0").rstrip(".") if fps > 0 else "30"


def ladder(src_h: int, wanted: list, allow_upscale: bool) -> list:
    hs = sorted({h for h in wanted if allow_upscale or h <= src_h}, reverse=True)
    return hs or [src_h]


def is_upscale(h: int, src_h: int) -> bool:
    return h > src_h


def first_size(hs: list, want: int) -> int:
    """The size to make first: the upload size, or the closest one that is being made."""
    return min(hs, key=lambda h: (abs(h - want), -h))


def out_path(out_base: str, h: int, src_h: int) -> str:
    return f"{out_base}_{h}p{'_upscaled' if is_upscale(h, src_h) else ''}.mp4"


INTRO_S = 1.0                      # vv13: seconds the thumbnail is shown at the start (when ticked)


def _script(segments: list, h: int, src_h: int, rate: str, has_audio: bool, intro: bool = False,
            src_w: int = 0) -> str:
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in segments)
    v = f"[0:v]select='{expr}',setpts=N/({rate})/TB,scale=-2:{h}:flags=lanczos"
    if is_upscale(h, src_h):
        v += ",unsharp=5:5:0.8:5:5:0.0"
    if intro:                                                # vv13: the thumbnail picture first, then the clip
        ow = max(2, int(round(src_w * h / max(1, src_h) / 2)) * 2) if src_w else int(round(h * 16 / 9 / 2)) * 2
        parts = [v + ",setsar=1,format=yuv420p[mv]",
                 f"[1:v]fps={rate},scale={ow}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                 f"pad={ow}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,setpts=N/({rate})/TB[iv]"]
        if has_audio:
            parts.append(f"[0:a]aselect='{expr}',asetpts=N/SR/TB,aformat=sample_rates=48000:channel_layouts=stereo[ma]")
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{INTRO_S},asetpts=N/SR/TB[ia]")
            parts.append("[iv][ia][mv][ma]concat=n=2:v=1:a=1[v][a]")
        else:
            parts.append("[iv][mv]concat=n=2:v=1:a=0[v]")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(";".join(parts))
            return f.name
    parts = [v + ",format=yuv420p[v]"]
    if has_audio:
        parts.append(f"[0:a]aselect='{expr}',asetpts=N/SR/TB[a]")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(";".join(parts))
        return f.name


def _cmd(path: str, script: str, h: int, codec: str, out: str, info: dict, rate: str, cfg: dict,
         intro: str | None = None) -> list:
    cmd = [media.need("ffmpeg"), "-v", "error", "-y"]
    if codec == HW:
        cmd += ["-hwaccel", "videotoolbox"]                 # decode on the media engine too
    cmd += ["-i", path]
    if intro:
        cmd += ["-loop", "1", "-framerate", rate, "-t", str(INTRO_S), "-i", intro]
    cmd += ["-filter_complex_script", script, "-map", "[v]"]
    if info["has_audio"]:
        cmd += ["-map", "[a]"]
    n, _, d = rate.partition("/")
    gop = str(int(round(float(n) / float(d or 1) * 2)))       # a keyframe every 2 s: quick seeking
    if codec == HW:
        r = VT_RATE.get(h, 2)
        cmd += ["-c:v", HW, "-b:v", f"{r}M", "-maxrate", f"{r * 1.5:.1f}M", "-bufsize", f"{r * 2:.1f}M",
                "-profile:v", "high", "-realtime", "0"]
    else:
        m = X264_MAX.get(h, 2)
        cmd += ["-c:v", "libx264", "-preset", cfg.get("preset", "fast"), "-crf", str(CRF.get(h, 22)),
                "-maxrate", f"{m}M", "-bufsize", f"{m * 2}M", "-profile:v", "high"]
    cmd += ["-g", gop, "-r", rate, "-c:a", "aac", "-b:a", AUDIO.get(h, "128k"), "-movflags", "+faststart", out]
    return cmd


def render_one(path, segments, info, cfg, h, out, log=print, on_pct=lambda p: None, intro: str | None = None) -> str:
    """Make one size. Returns the encoder that worked. intro = a picture shown for 1 s before the clip (optional)."""
    rate = rate_str(info.get("fps", 30.0))
    total = sum(b - a for a, b in segments) + (INTRO_S if intro else 0)
    script = _script(segments, h, info["height"], rate, info["has_audio"], bool(intro), info.get("width", 0))
    enc = pick_encoder(cfg.get("encoder", "auto"))
    try:
        for codec in [enc] + (["libx264"] if enc != "libx264" else []):
            try:
                media.run_progress(_cmd(path, script, h, codec, out, info, rate, cfg, intro), total, on_pct)
                return codec
            except RuntimeError as e:
                if codec == "libx264":
                    raise
                log(f"{h}p: hardware encoder failed ({str(e)[-160:].strip()}) - using the software encoder")
    finally:
        os.unlink(script)
    return "libx264"


def render(path: str, segments: list, info: dict, cfg: dict, out_base: str, log=print, only=None,
           intro: str | None = None) -> dict:
    """Make the sizes (all ticked ones, or only those in `only`). Returns {height: output_path}."""
    if not segments:
        raise RuntimeError("no live play found - nothing to render")
    src_h = info["height"]
    hs = ladder(src_h, cfg["resolutions"], cfg["allow_upscale"])
    if only is not None:
        hs = [h for h in hs if h in only]
    if not hs:
        return {}
    os.makedirs(os.path.dirname(out_base), exist_ok=True)
    outs = {h: out_path(out_base, h, src_h) for h in hs}
    for h in hs:
        if is_upscale(h, src_h):
            log(f"{h}p is upscaled from your {src_h}p source: sharper than a plain stretch, but not real {h}p detail")
    names = ", ".join(f"{h}p" for h in hs)
    pct = {h: 0 for h in hs}
    lock = threading.Lock()

    def on(h):
        def f(p):
            with lock:
                pct[h] = p
                progress.set(f"rendering {names}", int(sum(pct.values()) / len(pct)))
        return f

    workers = max(1, min(len(hs), int(cfg.get("parallel_renders", 3 if sys.platform == "darwin" else 1))))
    log(f"rendering {names} with {pick_encoder(cfg.get('encoder', 'auto'))} ({workers} at a time) ...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {h: ex.submit(render_one, path, segments, info, cfg, h, outs[h], log, on(h), intro) for h in hs}
        for h in hs:
            futs[h].result()                                  # re-raises a failure
    return outs
