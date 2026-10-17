"""vv21: the commentators' own words from the source video's auto-captions (when YouTube has them),
used for the short "what to expect" lines in the description."""
from __future__ import annotations
import glob
import json
import os
import re
import tempfile

HYPE = re.compile(
    r"\b(from (downtown|deep|way downtown)|bang|splash|drains?|nothing but net|rises? up|rise and fire|poster|posterize|"
    r"throws? (it )?down|slam|jam|alley|lob|oh my|what a|wow|unbelievable|incredible|buzzer|and[- ]one|steal|block|"
    r"swat|dagger|lights? out|heat check|on fire|cold[- ]blooded|marksman|dime|no[- ]look|behind the back|crossover|"
    r"step[- ]?back|fadeaway|catch and shoot|triple|from the logo|tough shot|circus|spin move|euro ?step)\b", re.I)


def parse_json3(data: dict) -> list:
    """[(start_s, text)] cues from YouTube's json3 caption format."""
    out = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs or "tStartMs" not in ev:
            continue
        text = re.sub(r"\s+", " ", "".join(s.get("utf8", "") for s in segs)).strip()
        if text and text != "\n":
            out.append((ev["tStartMs"] / 1000.0, text))
    return out


def fetch(url: str, log=print) -> list:
    """Auto-captions (English) of a YouTube video as cues; [] if there are none or yt-dlp cannot reach them."""
    if not url or "youtu" not in url:
        return []
    try:
        import yt_dlp
        with tempfile.TemporaryDirectory() as d:
            opts = {"skip_download": True, "writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": ["en.*", "en"],
                    "subtitlesformat": "json3", "outtmpl": os.path.join(d, "c.%(ext)s"), "quiet": True, "no_warnings": True}
            with yt_dlp.YoutubeDL(opts) as y:
                y.download([url])
            files = glob.glob(os.path.join(d, "*.json3"))
            if not files:
                return []
            with open(files[0], encoding="utf-8") as f:
                return parse_json3(json.load(f))
    except Exception as e:
        log(f"captions not available ({str(e)[:120]})")
        return []


def candidates(cues: list, segments: list | None = None, limit: int = 12) -> list:
    """The most excited commentary lines inside the parts of the game that are kept, best first.
    A line scores for exciting words, exclamation, and being short enough to quote; very long ones are dropped."""
    def kept(t):
        return not segments or any(a <= t <= b for a, b in segments)
    scored, seen = [], set()
    for t, text in cues:
        if not kept(t) or len(text) < 12 or len(text) > 110:
            continue
        key = re.sub(r"\W+", "", text.lower())
        if key in seen:
            continue
        seen.add(key)
        n = len(HYPE.findall(text))
        if not n:
            continue
        scored.append((n * 2 + text.count("!") + (1 if text.isupper() else 0), t, text))
    scored.sort(key=lambda r: -r[0])
    return [text for _, _, text in scored[:limit]]
