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
    "resolutions": [1080, 720, 480, 360],
    "allow_upscale": True,      # 1080p/4K ticked on a 720p source are upscaled and labelled            # a 720p source cannot become real 4K
    "upload_resolution": 1080,
    "min_minutes": 8,                  # the finished clip is between these two lengths (minutes)
    "max_minutes": 12,
    "min_dead_s": 4,                   # clock frozen longer than this = cut
    "pad_s": 1.0,                      # context kept around each live run
    "min_clip_s": 6,
    "trim_start_s": 0,
    "clock_roi": [0.475, 0.828, 0.052, 0.050],  # x, y, w, h as fractions of the frame
    "highlights": False,                  # tick in the window: dead time out, then whole chunks to reach the length
    "highlight_lead_s": 3,                # highlights: keep this many seconds before tip-off
    "highlight_chunk_s": 45,              # highlights: longest chunk that can be dropped in one piece
    "preset": "fast",                     # x264 speed (software encoder only)
    "encoder": "auto",                    # auto = Apple hardware encoder on a Mac, libx264 elsewhere
    "parallel_renders": 3,                # sizes made at the same time after the upload size (Mac)
    "config_version": 11,
    "upload": {"enabled": False, "privacy": "public", "category_id": "17",
               "client_secret": "", "token": os.path.join(HOME, "youtube_token.json")},
    "cloudinary": {"enabled": False, "cloud_name": "", "api_key": "", "api_secret": ""},
    "ai": {"enabled": True, "model": "claude-sonnet-5-5", "api_key_env": "ANTHROPIC_API_KEY", "api_key": ""},
    "channel_name": "",
    "thumbnail": {"enabled": True},
    "include_interview": False,           # vv13: tick in the window to keep the post-game interview
    "thumb_font": "Impact",               # vv13: font style of the thumbnail (drop-down in the window)
    "thumb_cover_art": False,             # vv13: also save the thumbnail inside the video file as its cover picture
    "thumb_intro": False,                 # vv13: show the thumbnail for 1 second at the start of the video
    "photo_choice": {},                   # vv14: {"Nikola Jokic": 1} = the 2nd of his photos (0 = the first)
    "start_at_tipoff": True,              # vv14: the clip starts at the jump ball (vv19: ticked by default; untick to keep the opening)
    "player_choice": {},                  # {"DEN": "Jamal Murray"}: the player picked in the window's drop-down for a team
    "tags": [],
    "thumb_layout": "closeup",            # vv21: "closeup" (two big faces, stacked headline) or "stars" (older full-body layout)
    "description_cta": "Subscribe for every game's highlights.",   # vv21: one short line in the description ("" = none)
    "scan_only": [],                      # vv20: channel names highlighted in the list; only these are scanned
    "videos_per_scan": 3,                 # vv20: newest unprocessed videos taken per scan
    "wake": {"enabled": False},           # vv20: Mac wake-up for scheduled scans (needs the one-time setup button)
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
            saved = json.load(f)
        if saved.get("config_version", 0) < 9:          # 0.9: older files saved the slow software encoder
            saved["encoder"] = "auto"
        if saved.get("config_version", 0) < 10:         # 0.9.1: 4K off by default (tick it again if you want it)
            if "resolutions" in saved:
                saved["resolutions"] = [h for h in saved["resolutions"] if h != 2160] or [1080]
        if saved.get("config_version", 0) < 11 and saved.get("ai", {}).get("model") == "claude-haiku-5-5":
            saved["ai"]["model"] = "claude-sonnet-5-5"        # vv21: three writers on the better model
        saved["config_version"] = 11
        return _merge(DEFAULTS, saved)
    except (OSError, ValueError):
        return deepcopy(DEFAULTS)


def save(cfg: dict, path: str = CONFIG_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, path)
