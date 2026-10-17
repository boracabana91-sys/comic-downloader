"""vv22: the channel's rules in one place - which videos to take, what the file and the YouTube post must look like,
and the check that decides whether a video may be uploaded by itself.

File:   <star alias of team 1> vs <star alias of team 2> <MMDDYY>[_<size>p].mp4        e.g.  JOKER vs KAWHI 101526_1080p.mp4
Title:  <Team 1> vs <Team 2> - <FLASHY|GREAT|FULL GAME> [PLAYOFF ]HIGHLIGHTS | <Month D, YYYY>
Description: starts with the fair-use text; hashtags at the end.
"""
from __future__ import annotations
import os
import re
from datetime import datetime

from . import metadata, roster, thumbnail

MIN_GAME_S = 5 * 60            # anything shorter than this is a clip / reel / short, not a game video
TITLE_RE = re.compile(r"^(?P<a>[A-Za-z0-9 .'\-]+?) vs (?P<b>[A-Za-z0-9 .'\-]+?) - (?P<w>FLASHY|GREAT|FULL GAME)"
                      r"(?: (?P<po>PLAYOFF))? HIGHLIGHTS \| (?P<d>[A-Z][a-z]+ \d{1,2}, \d{4})$")
FILE_RE = re.compile(r"^(?P<a>[A-Z0-9 .'\-]+) vs (?P<b>[A-Z0-9 .'\-]+) (?P<d>\d{6})(?:_\d+p(?:_upscaled)?)?\.mp4$")
SHORT_WORDS = re.compile(r"(?i)#shorts?\b|\bshorts?\b|\breels?\b|\bclips?\b|\btop \d+\b")


def teams_of(title: str) -> list:
    return thumbnail.parse_teams(title)


def is_game_title(title: str) -> bool:
    """Two NBA teams and the word highlight(s): 'Denver Nuggets vs LA Clippers Full Game Highlights ...'."""
    return len(teams_of(title)) == 2 and bool(re.search(r"(?i)highlight", title))


def skip_reason(title: str, url: str = "", group: str = "", duration_s: float | None = None) -> str:
    """'' when the video should be taken; otherwise why it is skipped (Shorts, reels, clips, wrong title ...)."""
    if group.lower().startswith("short") or "/shorts/" in (url or ""):
        return "a Short"
    if duration_s is not None and 0 < duration_s < MIN_GAME_S:
        return f"too short for a game video ({int(duration_s // 60)} min)"
    if SHORT_WORDS.search(title) and not re.search(r"(?i)full game", title):
        return "looks like a clip / reel"
    if not is_game_title(title):
        return "the title does not name two NBA teams and 'highlights'"
    return ""


is_playoffs = metadata.is_playoffs


def game_datetime(title: str, published: datetime | None = None) -> datetime:
    s = metadata.game_date(title, published)
    return datetime.strptime(s, "%B %d, %Y")


def alias_of(cfg: dict, acr: str) -> str:
    """The star player's alias for a team, following the window's player drop-down (default star otherwise)."""
    opts = roster.options(acr)
    if not opts:
        return acr
    choice = (cfg.get("player_choice") or {}).get(acr)
    pick = next((o for o in opts if choice and o["name"].lower() == choice.lower()), opts[0])
    return re.sub(r"[^A-Z0-9 .'\-]", "", (pick.get("alias") or pick["name"]).upper()).strip() or acr


def file_stem(cfg: dict, teams: list, when: datetime) -> str:
    if len(teams) != 2:
        return ""
    return f"{alias_of(cfg, teams[0])} vs {alias_of(cfg, teams[1])} {when:%m%d%y}"


def make_title(names: list, word: str, date: str, playoffs: bool = False) -> str:
    return f"{names[0]} vs {names[1]} - {word}{' PLAYOFF' if playoffs else ''} HIGHLIGHTS | {date}"


def check(meta: dict, file_path: str, teams: list, source_title: str, cfg: dict | None = None) -> list:
    """[(ok, rule, detail)] - every rule the post must follow. The video may be uploaded by itself only if all are ok."""
    out = []

    def add(ok, rule, detail=""):
        out.append((bool(ok), rule, detail))

    title, desc, tags = meta.get("title", ""), meta.get("description", ""), meta.get("tags", [])
    m = TITLE_RE.match(title)
    add(m, "Title follows 'Team vs Team - WORD HIGHLIGHTS | Month D, YYYY'", title if not m else "")
    names = [roster.TEAMS[a][0] for a in teams if a in roster.TEAMS]
    add(len(teams) == 2 and m and [m.group("a"), m.group("b")] == names, "Both team names in the title are the two teams playing",
        "" if len(teams) == 2 else "could not read two NBA teams from the video title")
    add(len(title) <= 100, "Title is 100 characters or fewer", f"{len(title)} characters")
    po = is_playoffs(source_title)
    add(bool(m) and bool(m.group("po")) == po, "PLAYOFF in the title matches the source ('playoffs' written = playoffs)",
        "the source says playoffs but the title does not" if po else "the title says PLAYOFF but the source does not")
    add(desc.startswith(metadata.DISCLAIMER), "Description starts with the fair-use text")
    add(re.search(r"#\w+", desc), "Description ends with hashtags")
    add(len(tags) >= 8, "At least 8 tags", f"{len(tags)} tags")
    add(sum(len(t) + 1 for t in tags) <= 500, "Tags are within YouTube's 500-character limit")
    base = os.path.basename(file_path or "")
    fm = FILE_RE.match(base)
    add(fm, "File name follows 'ALIAS vs ALIAS MMDDYY'", base if not fm else "")
    if fm and len(teams) == 2 and cfg is not None:
        add(fm.group("a") == alias_of(cfg, teams[0]) and fm.group("b") == alias_of(cfg, teams[1]),
            "File name has the star player of each team (team 1 first)")
    add(file_path and os.path.isfile(file_path) and os.path.getsize(file_path) > 0, "Video file exists and is not empty")
    return out


def failed(checks: list) -> list:
    return [f"{rule}" + (f" - {d}" if d else "") for ok, rule, d in checks if not ok]
