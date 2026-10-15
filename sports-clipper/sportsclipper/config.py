"""Settings, stored as JSON in ~/SportsClipper/config.json."""
from __future__ import annotations
import json
import os
from copy import deepcopy

HOME = os.path.join(os.path.expanduser("~"), "SportsClipper")
CONFIG_PATH = os.path.join(HOME, "config.json")

DEFAULTS = {
    "work_dir": os.path.join(HOME, "work"),
    "output_dir": os.path.join(HOME, "output"),
    "sources": [],  # see rights.Source
    "schedule": {"mode": "interval", "hours": 2, "times": ["09:00", "21:00"]},
    "publish_delay_min": [5, 10],      # minutes after the source was published
    "resolutions": [2160, 1080, 720, 480, 360],
    "allow_upscale": True,      # 1080p/4K ticked on a 720p source are upscaled and labelled            # a 720p source cannot become real 4K
    "upload_resolution": 1080,
    "target_ratio": 0.59,              # Reclip kept 59% of Original
    "min_dead_s": 4,                   # clock frozen longer than this = cut
    "pad_s": 1.0,                      # context kept around each live run
    "min_clip_s": 6,
    "trim_start_s": 0,
    "clock_roi": [0.475, 0.828, 0.052, 0.050],  # x, y, w, h as fractions of the frame
    "highlights": False,                  # tick in the window: cut only dead time, keep play in game order
    "highlight_start_s": 60,              # highlights: cut the first minute (pre-game)
    "preset": "fast",                     # x264 speed: fast is ~1.5x quicker than medium at the same CRF
    "encoder": "libx264",                 # auto | libx264 | h264_videotoolbox
    "upload": {"enabled": False, "privacy": "public", "category_id": "17",
               "client_secret": "", "token": os.path.join(HOME, "youtube_token.json")},
    "cloudinary": {"enabled": False, "cloud_name": "", "api_key": "", "api_secret": ""},
    "ai": {"enabled": True, "model": "claude-haiku-5-5", "api_key_env": "ANTHROPIC_API_KEY", "api_key": ""},
    "channel_name": "",
    "thumbnail": {"enabled": True},
    "tags": [],
}


def _merge(base: dict, over: dict) -> dict:
    out = deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str = CONFIG_PATH) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _merge(DEFAULTS, json.load(f))
    except (OSError, ValueError):
        return deepcopy(DEFAULTS)


def save(cfg: dict, path: str = CONFIG_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, path)
