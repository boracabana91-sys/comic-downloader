"""NBA teams, each team's star player and the name shown under the team acronym on the thumbnail.

Each team has up to two players (PLAYERS below): the first is the default, the drop-down in the window switches.
Pictures come inside the app (players folder); your own folders in ~/SportsClipper/players win. Folders are named  "Team - ACR - Player Name",
for example  "Denver Nuggets - DEN - Nikola Jokic".  Inside a folder the app uses the first of
cutout.png / any .png (a player on a transparent background).  An optional alias.txt in the folder
replaces the name shown under the acronym.

To change who is listed, edit PLAYERS below (or just add another folder for that team: it appears in the drop-down too).
Picks follow the 2026-27 preseason top-100 rankings (CBS Sports, Yahoo Sports, NBA 2K27 ratings).
"""
from __future__ import annotations
import os
import re
import sys
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

# acronym: [(player, name shown on the thumbnail), ...]  - the first one is the default, the second is in the drop-down.
# No well-known alias -> the surname.  Max 2 per team.
PLAYERS = {
    "ATL": [("Jalen Johnson", "JOHNSON"), ("CJ McCollum", "CJ")],
    "BOS": [("Jayson Tatum", "TATUM"), ("Derrick White", "WHITE")],
    "BKN": [("Michael Porter Jr.", "MPJ"), ("Julius Randle", "RANDLE")],
    "CHA": [("Kon Knueppel", "KNUEPPEL"), ("Brandon Miller", "MILLER")],
    "CHI": [("Josh Giddey", "GIDDEY"), ("Matas Buzelis", "BUZELIS")],
    "CLE": [("Donovan Mitchell", "SPIDA"), ("James Harden", "THE BEARD")],
    "DAL": [("Kyrie Irving", "UNCLE DREW"), ("Cooper Flagg", "FLAGG")],
    "DEN": [("Nikola Jokic", "THE JOKER"), ("Jamal Murray", "MURRAY")],
    "DET": [("Cade Cunningham", "CUNNINGHAM"), ("Jalen Duren", "DUREN")],
    "GSW": [("Stephen Curry", "CHEF CURRY"), ("Draymond Green", "DRAYMOND")],
    "HOU": [("Kevin Durant", "KD"), ("Alperen Sengun", "SENGUN")],
    "IND": [("Tyrese Haliburton", "HALI"), ("Ivica Zubac", "ZUBAC")],
    "LAC": [("Darius Garland", "GARLAND"), ("Brandon Ingram", "INGRAM")],
    "LAL": [("Luka Doncic", "LUKA MAGIC"), ("Austin Reaves", "REAVES")],
    "MEM": [("Cameron Boozer", "BOOZER"), ("Zach Edey", "EDEY")],
    "MIA": [("Giannis Antetokounmpo", "GREEK FREAK"), ("Bam Adebayo", "BAM")],
    "MIL": [("Tyler Herro", "HERRO"), ("Myles Turner", "TURNER")],
    "MIN": [("Anthony Edwards", "ANT-MAN"), ("LaMelo Ball", "LAMELO")],
    "NOP": [("Zion Williamson", "ZION")],
    "NYK": [("Jalen Brunson", "BRUNSON"), ("Karl-Anthony Towns", "KAT")],
    "OKC": [("Shai Gilgeous-Alexander", "SGA"), ("Jalen Williams", "J-DUB")],
    "ORL": [("Paolo Banchero", "PAOLO"), ("Franz Wagner", "FRANZ")],
    "PHI": [("Tyrese Maxey", "MAXEY"), ("LeBron James", "KING JAMES")],
    "PHX": [("Devin Booker", "BOOK")],
    "POR": [("Deni Avdija", "AVDIJA"), ("Ja Morant", "JA")],
    "SAC": [("Domantas Sabonis", "SABONIS")],
    "SAS": [("Victor Wembanyama", "WEMBY")],
    "TOR": [("Kawhi Leonard", "THE KLAW"), ("Scottie Barnes", "BARNES")],
    "UTA": [("Lauri Markkanen", "THE FINNISHER"), ("Keyonte George", "KEYONTE")],
    "WAS": [("Anthony Davis", "THE BROW"), ("Trae Young", "ICE TRAE")],
}
STARS = {a: v[0] for a, v in PLAYERS.items()}      # the default player of each team


def players_dir() -> str:
    """Your own pictures (they win over the bundled ones)."""
    return os.environ.get("SPORTSCLIPPER_PLAYERS") or os.path.join(os.path.expanduser("~"), "SportsClipper", "players")


def bundled_dir() -> str:
    """The pictures that come inside the app."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "players")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "players")


def ascii_name(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def folder_name(acr: str, player: str | None = None) -> str:
    """'Denver Nuggets - DEN - Nikola Jokic'  (the team's default player unless one is named)"""
    return f"{TEAMS[acr][0]} - {acr} - {ascii_name(player or STARS[acr][0])}"


def team_color(acr: str) -> tuple:
    h = TEAMS[acr][2].lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _roots(root):
    return [root] if root else [players_dir(), bundled_dir()]


def _team_folders(acr: str, root: str) -> list:
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    pat = re.compile(rf"\s-\s{acr}\s-\s", re.I)
    return [os.path.join(root, n) for n in names if pat.search(n) and os.path.isdir(os.path.join(root, n))]


def _cutout_in(fol: str):
    try:
        pngs = sorted(f for f in os.listdir(fol) if f.lower().endswith(".png"))
    except OSError:
        return None
    if not pngs:
        return None
    pick = next((p for p in pngs if p.lower() == "cutout.png"), pngs[0])
    return os.path.join(fol, pick)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def options(acr: str, root: str | None = None) -> list:
    """The players of a team that have a picture, default player first:
    [{"name": "Nikola Jokic", "alias": "THE JOKER", "cutout": path}, ...].
    A folder you add yourself ("Team - ACR - Name") shows up too, with the surname as its alias."""
    if acr not in TEAMS:
        return []
    roots = _roots(root)
    out, seen = [], set()
    for name, alias in PLAYERS.get(acr, []):
        want = folder_name(acr, name).lower()
        for r in roots:                                     # your own folder first, then the bundled one
            fol = next((f for f in _team_folders(acr, r) if os.path.basename(f).lower() == want), None)
            png = _cutout_in(fol) if fol else None
            if png:
                af = os.path.join(fol, "alias.txt")
                a = alias
                if os.path.exists(af):
                    a = _read(af).upper() or alias
                out.append({"name": name, "alias": a, "cutout": png})
                seen.add(want)
                break
    for r in roots:
        for fol in _team_folders(acr, r):
            base = os.path.basename(fol)
            if base.lower() in seen:
                continue
            png = _cutout_in(fol)
            if not png:
                continue
            seen.add(base.lower())
            name = base.split(" - ", 2)[-1]
            a = ""
            af = os.path.join(fol, "alias.txt")
            if os.path.exists(af):
                a = _read(af)
            out.append({"name": name, "alias": (a or name.split()[-1]).upper(), "cutout": png})
    return out


def label(opt: dict) -> str:
    """Text shown in the drop-down."""
    return f"{opt['name']}  -  {opt['alias']}"


def find_star(acr: str, root: str | None = None, choice: str | None = None):
    """(cutout_png_path, name_for_thumbnail) for a team, or None when it has no picture.
    `choice` is the player's name picked in the drop-down; without one (or if that picture is missing)
    the team's default player is used."""
    opts = options(acr, root)
    if not opts:
        return None
    pick = next((o for o in opts if choice and o["name"].lower() == choice.lower()), opts[0])
    return pick["cutout"], pick["alias"]
