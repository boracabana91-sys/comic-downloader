"""Gets the NBA player pictures from Wikimedia Commons and cuts out the background.

This runs in the cloud when the app is built (GitHub Actions), so the Mac app already contains the pictures:
nobody has to run anything. It can also be run by hand:   python tools/get_players.py --out players

For every player in roster.PLAYERS it makes
    <out>/<Team - ACR - Player Name>/cutout.png   (player only, transparent background)
                                     credit.txt    (picture name, author, licence, link)
Only free-licence pictures are used (CC BY, CC BY-SA, CC0, public domain). Action shots (free throw, jump shot, dunk,
layup, dribble) and recent photos (current jersey) score higher.  Wikimedia asks for credit on CC BY / CC BY-SA pictures:
CREDITS.txt in the out folder lists them all.

  --team DEN,LAC     only these teams          --redo           make it again even if it is there
  --file "DEN:Nikola Jokic=File:Some picture.jpg"    use exactly this Commons file for a player
  --photo "DEN:Nikola Jokic=/path/my_picture.jpg"    use your own picture for a player
"""
from __future__ import annotations
import argparse
import html
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sportsclipper import roster  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
UA = "SportsClipper-vv11/1.0 (player thumbnails; https://github.com/boracabana91-sys/comic-downloader)"
GOOD_LICENCE = re.compile(r"^(cc[ -]by(-sa)?[ -]\d|cc0|cc[ -]zero|public domain|pd)", re.I)
ACTION = [("free throw", 6), ("freethrow", 6), ("shooting", 4), ("jump shot", 5), ("jumpshot", 5), ("dunk", 5),
          ("layup", 4), ("lay-up", 4), ("drives", 3), ("driving", 3), ("dribbl", 3), ("vs", 1), ("game", 1)]
BAD = ("logo", "signature", "crowd", "cheerleader", "mascot", "draft", "interview", "press conference", "jersey retire",
       "statue", "mural", "trophy", "ceremony", "wax", "cartoon", "autograph", "podium", "parade", "courtside", "fans")
MAX_H = 1100                     # cutouts are kept at most this tall: sharp enough for a 1080p thumbnail, small in the app


def surname(player: str) -> str:
    parts = roster.ascii_name(player).replace(".", "").split()
    if parts[-1].lower() in ("jr", "iii", "ii"):
        parts = parts[:-1]
    return parts[-1].lower()


def licence_ok(meta: dict) -> bool:
    name = html.unescape(re.sub("<[^>]+>", "", (meta.get("LicenseShortName") or {}).get("value", "")))
    return bool(GOOD_LICENCE.match(name.strip())) and "nc" not in name.lower().split()


def year_of(meta: dict) -> int:
    for k in ("DateTimeOriginal", "DateTime"):
        m = re.search(r"(20\d\d)", (meta.get(k) or {}).get("value", ""))
        if m:
            return int(m.group(1))
    return 0


def score(title: str, w: int, h: int, player: str, year: int = 0) -> float:
    t = roster.ascii_name(title).lower()
    if surname(player) not in t or any(b in t for b in BAD) or not t.endswith((".jpg", ".jpeg", ".png")):
        return -1
    if w < 1000:
        return -1
    s = sum(v for k, v in ACTION if k in t)
    s += 1.5 if h >= w * 0.9 else 0          # portrait or square frames give a bigger cutout
    s += min(w / 3000, 1)
    if year:
        s += max(0, min(year, 2026) - 2019) * 0.5     # recent photo: the current team's jersey is likelier
    return s


def _query(session, **params):
    for attempt in range(4):
        r = session.get(API, params={"format": "json", **params}, headers={"User-Agent": UA}, timeout=40)
        if r.status_code in (429, 503):
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Commons is busy, try again later")


def search(player: str, session) -> list:
    out = {}
    for extra in ("free throw", "shooting", "dunk", "layup dribbling", "basketball"):
        data = _query(session, action="query", generator="search", gsrnamespace=6, gsrlimit=25,
                      gsrsearch=f"{player} {extra}", prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800)
        for p in (data.get("query", {}).get("pages", {}) or {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            if not ii or not licence_ok(ii.get("extmetadata", {})):
                continue
            sc = score(p["title"], ii.get("width", 0), ii.get("height", 0), player, year_of(ii.get("extmetadata", {})))
            if sc >= 0:
                out[p["title"]] = (sc, ii)
        time.sleep(0.4)
    return sorted(((sc, t, ii) for t, (sc, ii) in out.items()), key=lambda x: -x[0])


def file_info(title: str, session) -> tuple:
    data = _query(session, action="query", titles=title, prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800)
    p = next(iter((data.get("query", {}).get("pages", {}) or {}).values()))
    ii = (p.get("imageinfo") or [None])[0]
    if not ii:
        raise RuntimeError(f"{title}: not found on Commons")
    return 0, title, ii


_session_cache = {}


def cut_out(src_path: str, out_png: str) -> None:
    try:
        from rembg import new_session, remove
    except ImportError:
        sys.exit("rembg is missing: pip install 'rembg[cpu]'")
    from PIL import Image
    if "s" not in _session_cache:
        _session_cache["s"] = new_session("isnet-general-use")
    im = Image.open(src_path).convert("RGB")
    cut = remove(im, session=_session_cache["s"], alpha_matting=False, post_process_mask=True)
    box = cut.getchannel("A").point(lambda a: 255 if a > 20 else 0).getbbox()
    if not box:
        raise RuntimeError("nothing left after removing the background")
    cut = cut.crop(box)
    if cut.height < 350 or cut.height < cut.width * 0.45:      # a sliver or a wide crop is not a player standing there
        raise RuntimeError(f"cut-out looks wrong ({cut.width}x{cut.height})")
    if cut.height > MAX_H:
        cut = cut.resize((max(1, round(cut.width * MAX_H / cut.height)), MAX_H), Image.LANCZOS)
    cut.save(out_png, optimize=True)


def _strip(meta, k):
    return html.unescape(re.sub("<[^>]+>", "", (meta.get(k) or {}).get("value", ""))).strip()


def do_player(acr, player, out_root, redo, session, forced=None, photo=None) -> str:
    fol = os.path.join(out_root, roster.folder_name(acr, player))
    os.makedirs(fol, exist_ok=True)
    png = os.path.join(fol, "cutout.png")
    if os.path.exists(png) and not redo and not forced and not photo:
        return "already there"
    if photo:
        cut_out(photo, png)
        with open(os.path.join(fol, "credit.txt"), "w", encoding="utf-8") as f:
            f.write(f"Picture supplied by the owner of the app: {os.path.basename(photo)}\n")
        return "cut out from your picture"
    hits = [file_info(forced, session)] if forced else search(player, session)
    src = os.path.join(fol, "_source.jpg")
    for sc, title, ii in hits[:4]:                       # try the best few, keep the first that cuts out cleanly
        try:
            r = session.get(ii.get("thumburl") or ii["url"], headers={"User-Agent": UA}, timeout=90)
            r.raise_for_status()
            with open(src, "wb") as f:
                f.write(r.content)
            cut_out(src, png)
        except Exception as e:                           # noqa: BLE001
            print(f"   skipped {title}: {e}", flush=True)
            continue
        finally:
            if os.path.exists(src):
                os.remove(src)
        meta = ii.get("extmetadata", {})
        with open(os.path.join(fol, "credit.txt"), "w", encoding="utf-8") as f:
            f.write(f"{title}\nAuthor: {_strip(meta, 'Artist')}\nLicence: {_strip(meta, 'LicenseShortName')}\n"
                    f"{ii.get('descriptionurl', '')}\n")
        return f"{title}  [{_strip(meta, 'LicenseShortName')}]"
    return "NO PICTURE FOUND"


def write_credits(out_root: str) -> None:
    lines = ["Player pictures: Wikimedia Commons, free licences. Credit these when a licence asks for it.\n"]
    for name in sorted(os.listdir(out_root)):
        c = os.path.join(out_root, name, "credit.txt")
        if os.path.exists(c):
            lines.append(f"== {name}\n" + open(c, encoding="utf-8").read())
    with open(os.path.join(out_root, "CREDITS.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _pairs(values):
    out = {}
    for v in values or []:
        key, _, val = v.partition("=")
        out[key.strip()] = val.strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=roster.players_dir())
    ap.add_argument("--team", help="acronyms, comma separated (default: all 30)")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--file", action="append", help='"DEN:Nikola Jokic=File:Name.jpg"')
    ap.add_argument("--photo", action="append", help='"DEN:Nikola Jokic=/path.jpg"')
    a = ap.parse_args()
    teams = [t.strip().upper() for t in a.team.split(",")] if a.team else list(roster.PLAYERS)
    bad = [t for t in teams if t not in roster.PLAYERS]
    if bad:
        sys.exit(f"unknown team acronym: {', '.join(bad)}")
    forced, photos = _pairs(a.file), _pairs(a.photo)
    import requests
    session = requests.Session()
    missing = []
    for acr in teams:
        for player, _alias in roster.PLAYERS[acr]:
            key = f"{acr}:{player}"
            print(f"{acr}  {player} ...", flush=True)
            try:
                msg = do_player(acr, player, a.out, a.redo, session, forced.get(key), photos.get(key))
            except Exception as e:                       # noqa: BLE001
                msg = f"FAILED: {e}"
            print("   " + msg, flush=True)
            if msg.startswith(("NO PICTURE", "FAILED")):
                missing.append(key)
    write_credits(a.out)
    print("\nDone." + (f" Still missing: {', '.join(missing)}" if missing else " Every player has a cutout."))


if __name__ == "__main__":
    main()
