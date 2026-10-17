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


LEAD = re.compile(r"^(?:and|but|so|uh|um|well|now|then|yeah)\s+", re.I)


def clean_units(text: str) -> list:
    """vv28: auto-caption text -> quotable sentences: '>>' speaker marks, [Music] and '- ' removed, split at sentence ends,
    a leading 'and / but / so' dropped, first letter capitalised. Broken all-caps lines and one-word crumbs are dropped."""
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text or "")
    t = re.sub(r">>+|^\s*-\s+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    out, carry = [], ""
    for sent in re.findall(r"[^.!?]+[.!?]?", t):
        sent = LEAD.sub("", sent.strip())
        if not sent:
            continue
        sent = (carry + " " + sent).strip()
        words = sent.split()
        if len(words) < 4:                     # "Oh my!" -> glue it to the next sentence
            carry = sent
            continue
        carry = ""
        letters = [w for w in words if re.sub(r"[^A-Za-z]", "", w)]
        shouted = [w for w in letters if len(re.sub(r"[^A-Za-z]", "", w)) > 1 and re.sub(r"[^A-Za-z]", "", w).isupper()]
        if len(shouted) >= 3 or (letters and len(shouted) / len(letters) >= 0.4):   # broken ALL-CAPS captions
            continue
        out.append(sent[0].upper() + sent[1:])
    return out


def score_line(text: str) -> float:
    """How good a one-line teaser this is: exciting words, exclamation, a name in it, a natural length, finished sentence."""
    n = len(HYPE.findall(text))
    if not n:
        return 0.0
    names = len(re.findall(r"(?<!^)\b[A-Z][a-z]{2,}\b", text))
    ln = len(text)
    return n * 2 + text.count("!") + min(names, 2) * 0.6 + (0.8 if text[-1] in ".!?" else 0) - (1.0 if ln > 80 else 0) - (1.5 if ln < 20 else 0)


def candidates(cues: list, segments: list | None = None, limit: int = 12) -> list:
    """The most quotable excited commentary lines inside the parts of the game that are kept, best first (vv28: clean sentences)."""
    def kept(t):
        return not segments or any(a <= t <= b for a, b in segments)
    scored, seen = [], set()
    for t, text in cues:
        if not kept(t):
            continue
        for u in clean_units(text):
            key = re.sub(r"\W+", "", u.lower())
            if key in seen or len(u) > 110:
                continue
            seen.add(key)
            sc = score_line(u)
            if sc > 0:
                scored.append((sc, t, u))
    scored.sort(key=lambda r: -r[0])
    return [text for _, _, text in scored[:limit]]
