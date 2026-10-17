"""Game stats from ESPN's public scoreboard / box score (no key needed).

Used for: the final score, and each team's top scorer. Only these facts go on the thumbnail;
a player's name is printed only when the video frame itself shows that name (see thumbnail.py),
so the thumbnail never labels the wrong player.
If the feed can't be reached, the functions return None and the thumbnail uses team text only.
"""
from __future__ import annotations
import json
import urllib.request
from dataclasses import dataclass, field

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


@dataclass
class Leader:
    name: str
    last: str                      # upper-case last name, used for matching captions
    pts: int
    reb: int
    ast: int


@dataclass
class GameInfo:
    event_id: str
    home: str
    away: str
    home_score: int
    away_score: int
    leaders: dict = field(default_factory=dict)     # abbr -> Leader (top scorer)


def _get(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def find_event(yyyymmdd: str, abbrs: list):
    """Find the game between two team abbreviations on a date. Returns the event id or None."""
    data = _get(f"{BASE}/scoreboard?dates={yyyymmdd}")
    want = {a.upper() for a in abbrs}
    for ev in data.get("events", []):
        comp = ev["competitions"][0]
        got = {c["team"]["abbreviation"].upper() for c in comp["competitors"]}
        if want <= got:
            return ev["id"]
    return None


def parse_summary(data: dict) -> GameInfo | None:
    """Turn an ESPN game summary into GameInfo. Pure function, tested with a fixture."""
    comp = data["header"]["competitions"][0]
    teams = {}
    for c in comp["competitors"]:
        teams[c["homeAway"]] = (c["team"]["abbreviation"].upper(), int(float(c.get("score", 0))))
    if "home" not in teams or "away" not in teams:
        return None
    info = GameInfo(data["header"]["id"], teams["home"][0], teams["away"][0], teams["home"][1], teams["away"][1])
    for team_block in data.get("boxscore", {}).get("players", []):
        abbr = team_block["team"]["abbreviation"].upper()
        best = None
        for group in team_block.get("statistics", []):
            labels = group.get("labels") or group.get("names") or []
            for a in group.get("athletes", []):
                st = dict(zip(labels, a.get("stats", [])))
                try:
                    pts = int(st.get("PTS", 0)); reb = int(st.get("REB", 0)); ast = int(st.get("AST", 0))
                except ValueError:
                    continue
                name = a["athlete"].get("displayName", "")
                if name and (best is None or pts > best.pts):
                    best = Leader(name, name.split()[-1].upper(), pts, reb, ast)
        if best:
            info.leaders[abbr] = best
    return info


def game_info(yyyymmdd: str, abbrs: list):
    """Score and top scorers for a game, or None if anything is unavailable."""
    try:
        eid = find_event(yyyymmdd, abbrs)
        if not eid:
            return None
        return parse_summary(_get(f"{BASE}/summary?event={eid}"))
    except Exception:
        return None
