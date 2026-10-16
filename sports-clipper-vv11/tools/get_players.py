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


def score(title: str, w: int, h: int, player: str, year: int = 0, need_name: bool = True) -> float:
    t = roster.ascii_name(title).lower()
    if (need_name and surname(player) not in t) or any(b in t for b in BAD) or not t.endswith((".jpg", ".jpeg", ".png")):
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


def _plain(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", roster.ascii_name(s).lower().replace(".", "")).strip()


def find_category(player: str, session) -> str | None:
    """The player's own Commons category ('Category:Nikola Jokic'): every file in it shows that person."""
    data = _query(session, action="query", list="search", srnamespace=14, srsearch=player, srlimit=10)
    want = _plain(player)
    titles = [h["title"] for h in data.get("query", {}).get("search", [])]
    for t in titles:
        if _plain(t.split(":", 1)[1]) == want:
            return t
    return None


def _collect(out: dict, data: dict, player: str, in_category: bool) -> None:
    for p in (data.get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii or not licence_ok(ii.get("extmetadata", {})):
            continue
        t = roster.ascii_name(p["title"]).lower()
        if any(b in t for b in BAD) or not t.endswith((".jpg", ".jpeg", ".png")) or ii.get("width", 0) < 1000:
            continue
        if not in_category and surname(player) not in t:
            continue
        sc = score(p["title"], ii.get("width", 0), ii.get("height", 0), player, year_of(ii.get("extmetadata", {})),
                   need_name=not in_category)
        if sc >= 0:
            out[p["title"]] = (sc + (1 if in_category else 0), ii)


def search(player: str, session) -> list:
    out = {}
    cat = find_category(player, session)
    if cat:
        cont = {}
        for _ in range(8):                                # up to ~400 files of the category
            data = _query(session, action="query", generator="categorymembers", gcmtitle=cat, gcmtype="file",
                          gcmlimit=50, prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800, **cont)
            _collect(out, data, player, True)
            cont = data.get("continue", {})
            if not cont:
                break
            time.sleep(0.3)
    for extra in ("free throw", "shooting", "dunk", "layup dribbling"):
        data = _query(session, action="query", generator="search", gsrnamespace=6, gsrlimit=25,
                      gsrsearch=f"{player} {extra}", prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800)
        _collect(out, data, player, False)
        time.sleep(0.3)
    print(f"   {cat or 'no category'}: {len(out)} usable pictures", flush=True)
    return sorted(((sc, t, ii) for t, (sc, ii) in out.items()), key=lambda x: -x[0])


def file_info(title: str, session) -> tuple:
    data = _query(session, action="query", titles=title, prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800)
    p = next(iter((data.get("query", {}).get("pages", {}) or {}).values()))
    ii = (p.get("imageinfo") or [None])[0]
    if not ii:
        raise RuntimeError(f"{title}: not found on Commons")
    return 0, title, ii


_session_cache = {}


def judge(cut):
    """(ok, quality, why). A good cut-out is ONE player who fills the picture: not a group, not a tiny figure."""
    import cv2
    import numpy as np
    alpha = np.asarray(cut.getchannel("A"))
    mask = (alpha > 128).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n < 2:
        return False, 0, "nothing left"
    areas = stats[1:, cv2.CC_STAT_AREA]
    big = int(areas.argmax()) + 1
    total = float(areas.sum())
    x, y, w, h, area = stats[big]
    others = [int(a) for i, a in enumerate(areas, 1) if i != big and a > 0.04 * area]
    if others:
        return False, 0, f"{1 + len(others)} bodies in the picture"
    if area / total < 0.8:
        return False, 0, "scattered"
    frame = alpha.shape[0]
    fill = h / frame
    if h < 450 or fill < 0.45:
        return False, 0, f"player too small in the photo ({h}px, {fill:.0%} of the frame)"
    if w > 1.15 * h:
        return False, 0, "too wide for one player standing"
    return True, fill + min(area / (w * h), 0.7), "ok"


def cut_out(src_path: str, out_png: str, check: bool = True) -> float:
    try:
        from rembg import new_session, remove
    except ImportError:
        sys.exit("rembg is missing: pip install 'rembg[cpu]'")
    from PIL import Image
    if "s" not in _session_cache:
        _session_cache["s"] = new_session("isnet-general-use")
    im = Image.open(src_path).convert("RGB")
    cut = remove(im, session=_session_cache["s"], alpha_matting=False, post_process_mask=True)
    if check:
        ok, quality, why = judge(cut)
        if not ok:
            raise RuntimeError(why)
    else:
        quality = 1.0
    box = cut.getchannel("A").point(lambda a: 255 if a > 20 else 0).getbbox()
    if not box:
        raise RuntimeError("nothing left after removing the background")
    cut = cut.crop(box)
    if cut.height > MAX_H:
        cut = cut.resize((max(1, round(cut.width * MAX_H / cut.height)), MAX_H), Image.LANCZOS)
    cut.save(out_png, optimize=True)
    return quality


def _strip(meta, k):
    return html.unescape(re.sub("<[^>]+>", "", (meta.get(k) or {}).get("value", ""))).strip()


def do_player(acr, player, out_root, redo, session, forced=None, photo=None, tries=12) -> str:
    fol = os.path.join(out_root, roster.folder_name(acr, player))
    os.makedirs(fol, exist_ok=True)
    png = os.path.join(fol, "cutout.png")
    if os.path.exists(png) and not redo and not forced and not photo:
        return "already there"
    if redo and os.path.exists(png):
        os.remove(png)                                   # a redo must not leave the old (maybe wrong) picture behind
    if photo:
        cut_out(photo, png, check=False)
        with open(os.path.join(fol, "credit.txt"), "w", encoding="utf-8") as f:
            f.write(f"Picture supplied by the owner of the app: {os.path.basename(photo)}\n")
        return "cut out from your picture"
    hits = [file_info(forced, session)] if forced else search(player, session)
    src = os.path.join(fol, "_source.jpg")
    for sc, title, ii in hits[:tries]:                   # best first; keep the first that cuts out as one clear player
        try:
            r = session.get(ii.get("thumburl") or ii["url"], headers={"User-Agent": UA}, timeout=90)
            r.raise_for_status()
            with open(src, "wb") as f:
                f.write(r.content)
            cut_out(src, png, check=not forced)
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
    ap.add_argument("--shard", help='"i/n": only every n-th team, starting at i (to run several fetches side by side)')
    ap.add_argument("--credits-only", action="store_true", help="just rewrite CREDITS.txt")
    ap.add_argument("--file", action="append", help='"DEN:Nikola Jokic=File:Name.jpg"')
    ap.add_argument("--photo", action="append", help='"DEN:Nikola Jokic=/path.jpg"')
    a = ap.parse_args()
    teams = [t.strip().upper() for t in a.team.split(",")] if a.team else list(roster.PLAYERS)
    bad = [t for t in teams if t not in roster.PLAYERS]
    if bad:
        sys.exit(f"unknown team acronym: {', '.join(bad)}")
    if a.credits_only:
        write_credits(a.out)
        return
    if a.shard:
        i, n = (int(x) for x in a.shard.split("/"))
        teams = [t for k, t in enumerate(teams) if k % n == i]
    os.makedirs(a.out, exist_ok=True)
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
    print("\nDone." + (f" Still missing: {', '.join(missing)}" if missing else " Every player has a cutout."))


if __name__ == "__main__":
    main()
