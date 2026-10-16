"""Gets each NBA team's star player picture from Wikimedia Commons and cuts out the background.

Run it on your Mac with tools/get_players.command (double-click). It makes, for every team,
    ~/SportsClipper/players/<Team - ACR - Player Name>/cutout.png   (player only, transparent background)
                                                         source.jpg  (the photo it came from)
                                                         credit.txt  (author, licence, link)
Only pictures with a free licence (CC BY, CC BY-SA, CC0, public domain) are used.
Action shots (free throw, shot, dunk, layup, dribble) are preferred. Wikimedia asks for credit on CC BY / CC BY-SA
pictures, so keep credit.txt and put the line in your video description if you publish the thumbnail.

Use your own picture for a team:   python get_players.py --team DEN --photo my_jokic.jpg
Redo one team:                     python get_players.py --team DEN --redo
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
UA = "SportsClipper-vv10/1.0 (player thumbnails; personal use)"
GOOD_LICENCE = re.compile(r"^(cc[ -]by(-sa)?[ -]\d|cc0|cc[ -]zero|public domain|pd)", re.I)
ACTION = [("free throw", 6), ("freethrow", 6), ("shooting", 4), ("jump shot", 5), ("jumpshot", 5), ("dunk", 5),
          ("layup", 4), ("lay-up", 4), ("drives", 3), ("driving", 3), ("dribbl", 3), ("vs", 1), ("game", 1)]
BAD = ("logo", "signature", "crowd", "cheerleader", "mascot", "draft", "interview", "press conference", "jersey retire")


def surname(player: str) -> str:
    return roster.ascii_name(player).replace(".", "").split()[-1 if not player.endswith(("Jr.", "III", "II")) else -2].lower()


def licence_ok(meta: dict) -> bool:
    name = html.unescape(re.sub("<[^>]+>", "", (meta.get("LicenseShortName") or {}).get("value", "")))
    return bool(GOOD_LICENCE.match(name.strip())) and "nc" not in name.lower().split()


def score(title: str, w: int, h: int, player: str) -> float:
    t = roster.ascii_name(title).lower()
    if surname(player) not in t or any(b in t for b in BAD) or not t.endswith((".jpg", ".jpeg", ".png")):
        return -1
    if w < 1000:
        return -1
    s = sum(v for k, v in ACTION if k in t)
    s += 1.5 if h >= w * 0.9 else 0          # portrait or square frames give a bigger cutout
    s += min(w / 3000, 1)
    return s


def search(player: str, session) -> list:
    out = {}
    for extra in ("free throw", "shooting", "dunk", "layup dribbling", "basketball"):
        r = session.get(API, params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 25,
            "gsrsearch": f"{player} {extra}", "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1800,
        }, headers={"User-Agent": UA}, timeout=40)
        r.raise_for_status()
        for p in (r.json().get("query", {}).get("pages", {}) or {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            if not ii or not licence_ok(ii.get("extmetadata", {})):
                continue
            sc = score(p["title"], ii.get("width", 0), ii.get("height", 0), player)
            if sc >= 0:
                out[p["title"]] = (sc, ii)
        time.sleep(0.4)
    return sorted(((sc, t, ii) for t, (sc, ii) in out.items()), key=lambda x: -x[0])


def cut_out(src_path: str, out_png: str) -> None:
    try:
        from rembg import new_session, remove
    except ImportError:
        sys.exit("rembg is missing - run tools/get_players.command (it installs it) or: pip install 'rembg[cpu]'")
    from PIL import Image
    session = new_session("isnet-general-use")
    im = Image.open(src_path).convert("RGB")
    cut = remove(im, session=session, alpha_matting=False, post_process_mask=True)
    box = cut.getchannel("A").point(lambda a: 255 if a > 20 else 0).getbbox()
    if not box:
        raise RuntimeError("nothing left after removing the background")
    cut.crop(box).save(out_png)


def do_team(acr: str, out_root: str, redo: bool, photo: str | None, session) -> str:
    player = roster.STARS[acr][0]
    fol = os.path.join(out_root, roster.folder_name(acr))
    os.makedirs(fol, exist_ok=True)
    png = os.path.join(fol, "cutout.png")
    if os.path.exists(png) and not redo and not photo:
        return "already there"
    if photo:
        cut_out(photo, png)
        open(os.path.join(fol, "credit.txt"), "w", encoding="utf-8").write(f"Picture supplied by the user: {photo}\n")
        return "cut out from your picture"
    hits = search(player, session)
    for sc, title, ii in hits[:3]:                       # try the best three, keep the first that cuts out cleanly
        src = os.path.join(fol, "source.jpg")
        data = session.get(ii.get("thumburl") or ii["url"], headers={"User-Agent": UA}, timeout=90)
        data.raise_for_status()
        open(src, "wb").write(data.content)
        try:
            cut_out(src, png)
        except Exception as e:                           # noqa: BLE001
            print(f"   {title}: {e}")
            continue
        meta = ii.get("extmetadata", {})
        strip = lambda k: html.unescape(re.sub("<[^>]+>", "", (meta.get(k) or {}).get("value", ""))).strip()  # noqa: E731
        open(os.path.join(fol, "credit.txt"), "w", encoding="utf-8").write(
            f"{title}\nAuthor: {strip('Artist')}\nLicence: {strip('LicenseShortName')}\n{ii.get('descriptionurl', '')}\n")
        return f"{title}  [{strip('LicenseShortName')}]"
    return "NO PICTURE FOUND - drop a picture in with --photo"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=roster.players_dir())
    ap.add_argument("--team", help="one or more acronyms, comma separated (default: all 30)")
    ap.add_argument("--photo", help="use this picture for --team instead of searching Commons")
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    teams = [t.strip().upper() for t in a.team.split(",")] if a.team else list(roster.STARS)
    bad = [t for t in teams if t not in roster.STARS]
    if bad:
        sys.exit(f"unknown team acronym: {', '.join(bad)}")
    if a.photo and len(teams) != 1:
        sys.exit("--photo needs exactly one --team")
    import requests
    session = requests.Session()
    missing = []
    for acr in teams:
        print(f"{acr}  {roster.STARS[acr][0]} ...", flush=True)
        try:
            msg = do_team(acr, a.out, a.redo, a.photo, session)
        except Exception as e:                           # noqa: BLE001
            msg = f"FAILED: {e}"
        print("   " + msg)
        if msg.startswith(("NO PICTURE", "FAILED")):
            missing.append(acr)
    print("\nDone." + (f" Still missing: {', '.join(missing)}" if missing else " All teams have a cutout."))
    print(f"Folder: {a.out}")


if __name__ == "__main__":
    main()
