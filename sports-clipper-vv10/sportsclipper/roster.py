"""NBA teams, each team's star player and the name shown under the team acronym on the thumbnail.

Player folders live in ~/SportsClipper/players and are named  "Team - ACR - Player Name",
for example  "Denver Nuggets - DEN - Nikola Jokic".  Inside a folder the app uses the first of
cutout.png / any .png (a player on a transparent background).  An optional alias.txt in the folder
replaces the name shown under the acronym.

To change a team's star, edit STARS below (or just add another folder for that team: the app uses the
star listed here first, and otherwise the first folder it finds for that team).
Picks follow the 2026-27 preseason top-100 rankings (CBS Sports, Yahoo Sports, NBA 2K27 ratings).
"""
from __future__ import annotations
import os
import re
import unicodedata

# acronym: (full name, nickname, accent colour that reads on a dark background)
TEAMS = {
    "ATL": ("Atlanta Hawks", "Hawks", "#E03A3E"),
    "BOS": ("Boston Celtics", "Celtics", "#13A04B"),
    "BKN": ("Brooklyn Nets", "Nets", "#B5B9BF"),
    "CHA": ("Charlotte Hornets", "Hornets", "#00A3B4"),
    "CHI": ("Chicago Bulls", "Bulls", "#CE1141"),
    "CLE": ("Cleveland Cavaliers", "Cavaliers", "#B0123F"),
    "DAL": ("Dallas Mavericks", "Mavericks", "#1C7FD1"),
    "DEN": ("Denver Nuggets", "Nuggets", "#FEC524"),
    "DET": ("Detroit Pistons", "Pistons", "#D61F3F"),
    "GSW": ("Golden State Warriors", "Warriors", "#FFC72C"),
    "HOU": ("Houston Rockets", "Rockets", "#CE1141"),
    "IND": ("Indiana Pacers", "Pacers", "#FDBB30"),
    "LAC": ("Los Angeles Clippers", "Clippers", "#D6213F"),
    "LAL": ("Los Angeles Lakers", "Lakers", "#FDB927"),
    "MEM": ("Memphis Grizzlies", "Grizzlies", "#6E8CC8"),
    "MIA": ("Miami Heat", "Heat", "#E8344E"),
    "MIL": ("Milwaukee Bucks", "Bucks", "#1FB04B"),
    "MIN": ("Minnesota Timberwolves", "Timberwolves", "#78BE20"),
    "NOP": ("New Orleans Pelicans", "Pelicans", "#C8A960"),
    "NYK": ("New York Knicks", "Knicks", "#F58426"),
    "OKC": ("Oklahoma City Thunder", "Thunder", "#1E90E0"),
    "ORL": ("Orlando Magic", "Magic", "#1E90E0"),
    "PHI": ("Philadelphia 76ers", "76ers", "#1E7BD0"),
    "PHX": ("Phoenix Suns", "Suns", "#F26A24"),
    "POR": ("Portland Trail Blazers", "Trail Blazers", "#E03A3E"),
    "SAC": ("Sacramento Kings", "Kings", "#8F66CC"),
    "SAS": ("San Antonio Spurs", "Spurs", "#C4CED4"),
    "TOR": ("Toronto Raptors", "Raptors", "#CE1141"),
    "UTA": ("Utah Jazz", "Jazz", "#F9A01B"),
    "WAS": ("Washington Wizards", "Wizards", "#E31837"),
}

# acronym: (player, name shown on the thumbnail).  No well-known alias -> the surname.
STARS = {
    "ATL": ("Jalen Johnson", "JOHNSON"),
    "BOS": ("Jayson Tatum", "TATUM"),
    "BKN": ("Michael Porter Jr.", "MPJ"),
    "CHA": ("Kon Knueppel", "KNUEPPEL"),
    "CHI": ("Josh Giddey", "GIDDEY"),
    "CLE": ("Donovan Mitchell", "SPIDA"),
    "DAL": ("Kyrie Irving", "UNCLE DREW"),
    "DEN": ("Nikola Jokic", "THE JOKER"),
    "DET": ("Cade Cunningham", "CUNNINGHAM"),
    "GSW": ("Stephen Curry", "CHEF CURRY"),
    "HOU": ("Kevin Durant", "KD"),
    "IND": ("Tyrese Haliburton", "HALI"),
    "LAC": ("Darius Garland", "GARLAND"),
    "LAL": ("Luka Doncic", "LUKA MAGIC"),
    "MEM": ("Cameron Boozer", "BOOZER"),
    "MIA": ("Giannis Antetokounmpo", "GREEK FREAK"),
    "MIL": ("Tyler Herro", "HERRO"),
    "MIN": ("Anthony Edwards", "ANT-MAN"),
    "NOP": ("Zion Williamson", "ZION"),
    "NYK": ("Jalen Brunson", "BRUNSON"),
    "OKC": ("Shai Gilgeous-Alexander", "SGA"),
    "ORL": ("Paolo Banchero", "PAOLO"),
    "PHI": ("Tyrese Maxey", "MAXEY"),
    "PHX": ("Devin Booker", "BOOK"),
    "POR": ("Deni Avdija", "AVDIJA"),
    "SAC": ("Domantas Sabonis", "SABONIS"),
    "SAS": ("Victor Wembanyama", "WEMBY"),
    "TOR": ("Kawhi Leonard", "THE KLAW"),
    "UTA": ("Jaren Jackson Jr.", "JJJ"),
    "WAS": ("Anthony Davis", "THE BROW"),
}



def players_dir() -> str:
    return os.environ.get("SPORTSCLIPPER_PLAYERS") or os.path.join(os.path.expanduser("~"), "SportsClipper", "players")


def ascii_name(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def folder_name(acr: str) -> str:
    """'Denver Nuggets - DEN - Nikola Jokic'"""
    return f"{TEAMS[acr][0]} - {acr} - {ascii_name(STARS[acr][0])}"


def team_color(acr: str) -> tuple:
    h = TEAMS[acr][2].lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _team_folders(acr: str, root: str) -> list:
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    pat = re.compile(rf"\s-\s{acr}\s-\s", re.I)
    return [os.path.join(root, n) for n in names if pat.search(n) and os.path.isdir(os.path.join(root, n))]


def find_star(acr: str, root: str | None = None):
    """(cutout_png_path, name_for_thumbnail) for a team, or None when no cutout is in the players folder.
    The listed star is used first; otherwise the first player folder found for the team."""
    root = root or players_dir()
    folders = _team_folders(acr, root)
    want = folder_name(acr).lower() if acr in STARS else ""
    folders.sort(key=lambda p: os.path.basename(p).lower() != want)      # the listed star first
    for fol in folders:
        pngs = sorted(f for f in os.listdir(fol) if f.lower().endswith(".png"))
        if not pngs:
            continue
        pick = "cutout.png" if "cutout.png" in [p.lower() for p in pngs] else pngs[0]
        pick = next(p for p in pngs if p.lower() == pick.lower())
        name = ""
        alias_file = os.path.join(fol, "alias.txt")
        if os.path.exists(alias_file):
            name = open(alias_file, encoding="utf-8").read().strip()
        if not name:
            if os.path.basename(fol).lower() == want and acr in STARS:
                name = STARS[acr][1]
            else:
                name = os.path.basename(fol).split(" - ")[-1].split()[-1]    # surname of an added folder
        return os.path.join(fol, pick), name.upper()
    return None
