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
  --file "DEN:Nikola Jokic=File:A.jpg|File:B.jpg|File:C.jpg"    use exactly these Commons files for a player (up to 3: cutout.png, cutout2.png, cutout3.png)
  --pics 3           photos kept per player (different pictures, best first)
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
UA = "SportsClipper-vv13/1.0 (player thumbnails; https://github.com/boracabana91-sys/comic-downloader)"
GOOD_LICENCE = re.compile(r"^(cc[ -]by(-sa)?[ -]\d|cc0|cc[ -]zero|public domain|pd)", re.I)
ACTION = [("free throw", 6), ("freethrow", 6), ("shooting", 4), ("jump shot", 5), ("jumpshot", 5), ("dunk", 5),
          ("layup", 4), ("lay-up", 4), ("drives", 3), ("driving", 3), ("dribbl", 3), ("vs", 1), ("game", 1)]
BAD = ("logo", "signature", "crowd", "cheerleader", "mascot", "draft", "interview", "press conference", "jersey retire",
       "statue", "mural", "trophy", "ceremony", "wax", "cartoon", "autograph", "podium", "parade", "courtside", "fans")
MAX_H = 1100                     # cutouts are kept at most this tall: sharp enough for a 1080p thumbnail, small in the app


def _nick_pattern():
    out = {}
    for acr, (full, nick, _c) in roster.TEAMS.items():
        names = {nick.lower(), full.lower()}
        if nick == "Trail Blazers":
            names.add("blazers")
        out[acr] = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![a-z0-9])")
    return out


NICK = _nick_pattern()


def teams_in(text: str) -> set:
    """Acronyms of the NBA teams named in a picture's title / description / categories."""
    t = roster.ascii_name(text).lower()
    return {acr for acr, pat in NICK.items() if pat.search(t)}


def team_status(acr: str, text: str) -> str:
    """'current' = the picture names the player's present team; 'other' = it names only other NBA teams (probably an
    old jersey: Durant in OKC blue); 'unknown' = no NBA team named (college, national team, plain portrait)."""
    seen = teams_in(text)
    if acr in seen:
        return "current"
    return "other" if seen else "unknown"


TEAM_BONUS = {"current": 6.0, "other": -6.0, "unknown": 0.0}


def meta_text(title: str, ii: dict) -> str:
    m = ii.get("extmetadata", {}) if ii else {}
    return " ".join([title, _strip(m, "ImageDescription"), (m.get("Categories") or {}).get("value", "").replace("|", " ")])


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
    if w < 700:
        return -1
    s = sum(v for k, v in ACTION if k in t)
    s += 1.5 if h >= w * 0.9 else 0          # portrait or square frames give a bigger cutout
    s += min(w / 3000, 1)
    if year:
        s += max(0, min(year, 2026) - 2019) * 0.5     # recent photo: the current team's jersey is likelier
    return s


def _query(session, _url=None, **params):
    for attempt in range(4):
        r = session.get(_url or API, params={"format": "json", **params}, headers={"User-Agent": UA}, timeout=40)
        if r.status_code in (429, 503):
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Commons is busy, try again later")


def _plain(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", roster.ascii_name(s).lower().replace(".", "")).strip()


WIKI = "https://en.wikipedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"


def identify(player: str, session) -> tuple:
    """(Commons category title or None, main photo 'File:...' or None) of THIS basketball player, via Wikipedia + Wikidata,
    so a namesake (another 'Anthony Edwards') can never be mixed in."""
    data = _query(session, WIKI, action="query", generator="search", gsrsearch=f"{player} basketball", gsrlimit=5,
                  prop="pageprops", ppprop="wikibase_item")
    pages = sorted((data.get("query", {}).get("pages", {}) or {}).values(), key=lambda p: p.get("index", 99))
    for pg in pages:
        qid = (pg.get("pageprops") or {}).get("wikibase_item")
        if not qid or surname(player) not in _plain(pg["title"]).replace(" ", ""):
            continue
        ent = _query(session, WIKIDATA, action="wbgetentities", ids=qid, props="claims")["entities"][qid]["claims"]
        occ = {c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") for c in ent.get("P106", [])}
        if "Q3665646" not in occ:                       # not a basketball player: a namesake
            continue
        def first(prop):
            for c in ent.get(prop, []):
                v = c["mainsnak"].get("datavalue", {}).get("value")
                if isinstance(v, str):
                    return v
            return None
        cat, img = first("P373"), first("P18")
        return (f"Category:{cat}" if cat else None, f"File:{img}" if img else None)
    return _category_by_search(player, session), None


def _category_by_search(player: str, session):
    """Wikidata gave nothing: look for a category named like the player. A '(basketball...)' one beats a plain namesake."""
    data = _query(session, action="query", list="search", srnamespace=14, srsearch=player, srlimit=10)
    want, best = _plain(player), None
    for h in data.get("query", {}).get("search", []):
        name = h["title"].split(":", 1)[1]
        base = _plain(re.sub(r"\(.*\)", "", name))
        if base == want:
            if "basketball" in name.lower():
                return h["title"]
            best = best or h["title"]
    return best


def _collect(out: dict, data: dict, player: str, in_category: bool, acr: str = "") -> None:
    for p in (data.get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii or not licence_ok(ii.get("extmetadata", {})):
            continue
        t = roster.ascii_name(p["title"]).lower()
        if any(b in t for b in BAD) or not t.endswith((".jpg", ".jpeg", ".png")) or ii.get("width", 0) < 700:
            continue
        if not in_category and surname(player) not in t:
            continue
        sc = score(p["title"], ii.get("width", 0), ii.get("height", 0), player, year_of(ii.get("extmetadata", {})),
                   need_name=not in_category)
        if sc >= 0:
            st = team_status(acr, meta_text(p["title"], ii)) if acr else "unknown"
            out[p["title"]] = (sc + (1 if in_category else 0) + TEAM_BONUS[st], ii, st)


def search(player: str, session, acr: str = "") -> list:
    out = {}
    cat, main = identify(player, session)
    if cat:
        cont = {}
        for _ in range(10):                               # up to ~500 files of the category
            data = _query(session, action="query", generator="categorymembers", gcmtitle=cat, gcmtype="file",
                          gcmlimit=50, prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800, **cont)
            _collect(out, data, player, True, acr)
            cont = data.get("continue", {})
            if not cont:
                break
            time.sleep(0.3)
    if cat and len(out) < 25:                             # few pictures: also look inside his sub-categories (games, seasons)
        try:
            sub = _query(session, action="query", list="categorymembers", cmtitle=cat, cmtype="subcat", cmlimit=30)
            for sc_ in sub.get("query", {}).get("categorymembers", [])[:30]:
                if re.search(r"(?i)\b(by|in)\b.*\b(year|photo|video)|audio|video|logo|statistics|signature", sc_["title"]):
                    continue
                data = _query(session, action="query", generator="categorymembers", gcmtitle=sc_["title"], gcmtype="file",
                              gcmlimit=50, prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800)
                _collect(out, data, player, True, acr)
                time.sleep(0.3)
        except Exception as e:                            # noqa: BLE001
            print(f"   sub-categories skipped: {e}", flush=True)
    if main and main not in out:                          # his Wikipedia infobox photo: certainly him
        try:
            _, t, ii = file_info(main, session)
            if licence_ok(ii.get("extmetadata", {})):
                st = team_status(acr, meta_text(t, ii)) if acr else "unknown"
                out[t] = (2 + (ii.get("height", 0) >= ii.get("width", 0)) + TEAM_BONUS[st], ii, st)
        except Exception:                                 # noqa: BLE001
            pass
    if acr:                                               # newest photos: ones that name his CURRENT team (new jersey after a trade)
        nick = roster.TEAMS[acr][1]
        for extra in (nick, f"{nick} 2026", f"{nick} 2025"):
            try:
                data = _query(session, action="query", generator="search", gsrnamespace=6, gsrlimit=25,
                              gsrsearch=f"{player} {extra}", prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800)
                _collect(out, data, player, False, acr)
            except Exception as e:                        # noqa: BLE001
                print(f"   team search skipped: {e}", flush=True)
            time.sleep(0.3)
    if not cat or len(out) < 4:                           # nothing (or almost nothing) identified: add a text search, checked by eye later
        for extra in ("free throw", "shooting", "dunk", "layup dribbling"):
            data = _query(session, action="query", generator="search", gsrnamespace=6, gsrlimit=25,
                          gsrsearch=f"{player} {extra}", prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800)
            _collect(out, data, player, False, acr)
            time.sleep(0.3)
    print(f"   {cat or 'no category'}: {len(out)} usable pictures", flush=True)
    return sorted(((sc, t, ii, st) for t, (sc, ii, st) in out.items()), key=lambda x: -x[0])


def file_info(title: str, session) -> tuple:
    data = _query(session, action="query", titles=title, prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1800)
    p = next(iter((data.get("query", {}).get("pages", {}) or {}).values()))
    ii = (p.get("imageinfo") or [None])[0]
    if not ii:
        raise RuntimeError(f"{title}: not found on Commons")
    return 0, title, ii


_session_cache = {}


def tidy(cut, drop_big: bool = False):
    """Clean a cut-out: keep the main body, plus small bits touching its neighbourhood (ball, hands); drop floating specks.
    drop_big=True also drops another whole body (an opponent) when the main player is at least 2.2x bigger than it."""
    import cv2
    import numpy as np
    alpha = np.asarray(cut.getchannel("A"))
    mask = (alpha > 128).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n < 3:
        return cut
    areas = stats[1:, cv2.CC_STAT_AREA]
    big = int(areas.argmax()) + 1
    x, y, w, h, area = stats[big]
    ex, ey = 0.12 * w, 0.12 * h
    keep = np.zeros(n, bool); keep[0] = False; keep[big] = True
    for i in range(1, n):
        if i == big:
            continue
        xi, yi, wi, hi, ai = stats[i]
        near = xi >= x - ex and yi >= y - ey and xi + wi <= x + w + ex and yi + hi <= y + h + ey
        if ai < 0.04 * area:
            keep[i] = near
        elif drop_big and area >= 2.2 * ai:
            keep[i] = False
        else:
            keep[i] = True
    a2 = np.where(keep[lab], alpha, 0).astype(np.uint8)
    from PIL import Image
    out = cut.copy()
    out.putalpha(Image.fromarray(a2))
    return out


def judge(cut, strict_edge: bool = True):
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
    if strict_edge:       # vv13: a player touching the photo's left/right/top edge has an arm, a hand or the head cut off
        band = max(2, int(0.008 * alpha.shape[1]))
        m = (lab == big)
        side = max(int(m[:, :band].any(axis=1).sum()), int(m[:, -band:].any(axis=1).sum()))
        top = int(m[:band, :].any(axis=0).sum())
        if side > 0.04 * frame:
            return False, 0, "cut off at the side of the photo (arm or hand missing)"
        if top > 0.04 * alpha.shape[1]:
            return False, 0, "head cut off at the top of the photo"
    return True, fill + min(area / (w * h), 0.7), "ok"


def cut_out(src_path: str, out_png: str, check: bool = True, strict_edge: bool = True, trim: bool = False) -> float:
    try:
        from rembg import new_session, remove
    except ImportError:
        sys.exit("rembg is missing: pip install 'rembg[cpu]'")
    from PIL import Image
    if "s" not in _session_cache:
        _session_cache["s"] = new_session("isnet-general-use")
    im = Image.open(src_path).convert("RGB")
    cut = remove(im, session=_session_cache["s"], alpha_matting=False, post_process_mask=True)
    cut = tidy(cut, drop_big=trim)
    if check:
        ok, quality, why = judge(cut, strict_edge)
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


def _slot(k: int) -> str:
    """cutout.png, cutout2.png, cutout3.png ... (the file names the app reads, vv14: up to 3 photos per player)"""
    return "cutout.png" if k == 0 else f"cutout{k + 1}.png"


def _same_photo(title: str) -> str:
    """Two Commons files that are only crops of each other count as one photo."""
    t = roster.ascii_name(title).lower()
    t = re.sub(r"\s*\((cropped|crop)[^)]*\)", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _credit(title, ii) -> str:
    meta = ii.get("extmetadata", {})
    return (f"{title}\nAuthor: {_strip(meta, 'Artist')}\nLicence: {_strip(meta, 'LicenseShortName')}\n"
            f"{ii.get('descriptionurl', '')}\n")


def _download(session, ii, dest) -> None:
    r = session.get(ii.get("thumburl") or ii["url"], headers={"User-Agent": UA}, timeout=90)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)


def do_player(acr, player, out_root, redo, session, forced=None, photo=None, tries=12, cands=0, prefer=None, pics=1) -> str:
    """Make the player's cut-outs: cutout.png and, with pics > 1, cutout2.png, cutout3.png (different photos).
    forced = one or more Commons titles chosen by eye (used exactly, in this order)."""
    fol = os.path.join(out_root, roster.folder_name(acr, player))
    os.makedirs(fol, exist_ok=True)
    png = os.path.join(fol, "cutout.png")
    if os.path.exists(png) and not redo and not forced and not photo:
        return "already there"
    if redo or forced:
        for f in os.listdir(fol):                         # a redo must not leave old (maybe wrong) pictures behind
            if re.fullmatch(r"cutout\d*\.png", f) or f == "credit.txt":
                os.remove(os.path.join(fol, f))
    if photo:
        cut_out(photo, png, check=False)
        with open(os.path.join(fol, "credit.txt"), "w", encoding="utf-8") as f:
            f.write(f"Picture supplied by the owner of the app: {os.path.basename(photo)}\n")
        return "cut out from your picture"
    src = os.path.join(fol, "_source.jpg")
    credits, notes = [], []
    if forced:
        for k, title in enumerate(forced):
            _, t, ii = file_info(title, session)
            try:
                _download(session, ii, src)
                cut_out(src, os.path.join(fol, _slot(k)), check=False)
            finally:
                if os.path.exists(src):
                    os.remove(src)
            credits.append(f"[{_slot(k)}]\n" + _credit(t, ii))
            notes.append(t)
        with open(os.path.join(fol, "credit.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(credits))
        return f"{len(forced)} picture(s): " + " | ".join(notes)
    hits = search(player, session, acr)
    if prefer:                                            # an earlier hand-picked photo goes first, but is judged like any other
        try:
            _, t, ii = file_info(prefer, session)
            hits = [(99, t, ii, team_status(acr, meta_text(t, ii)))] + [h for h in hits if h[1] != t]
        except Exception as e:                            # noqa: BLE001
            print(f"   preferred picture not usable: {e}", flush=True)
    cdir = os.path.join(out_root, "_cands", roster.folder_name(acr, player))
    got, kept, seen = [], 0, set()
    for strict, trim in ((True, False), (True, True), (False, True)):    # later passes only when more are needed
        if (got and (strict, trim) == (False, True)) or len(got) >= pics and kept >= cands:
            break                                         # edge-cut photos only when there is nothing else
        if trim and strict and len(got) < pics:
            print("   fewer than wanted - also trying photos with a neighbouring player (he is cut away)", flush=True)
        if not strict:
            print("   no photo with the whole player in it - trying the ones cut at the edge", flush=True)
        for sc, title, ii, st in hits[:max(tries, 4 * max(cands, pics))]:   # best first
            key = _same_photo(title)
            if key in seen or (len(got) >= pics and kept >= cands):
                continue
            slot = _slot(len(got)) if len(got) < pics else "_try.png"
            try:
                _download(session, ii, src)
                target = os.path.join(fol, slot)
                cut_out(src, target, check=True, strict_edge=strict, trim=trim)
            except Exception as e:                        # noqa: BLE001
                print(f"   skipped {title}: {e}", flush=True)
                continue
            finally:
                if os.path.exists(src):
                    os.remove(src)
            seen.add(key)
            if cands and kept < cands:
                os.makedirs(cdir, exist_ok=True)
                from PIL import Image
                th = Image.open(target); th.thumbnail((420, 520)); th.save(os.path.join(cdir, f"{kept + 1}.png"))
                with open(os.path.join(cdir, "index.txt"), "a", encoding="utf-8") as f:
                    f.write(f"{kept + 1}\t{title}\t{st}\n")
                kept += 1
            if slot == "_try.png":
                os.remove(target)
                continue
            flag = {"other": "  [OLD TEAM? names another NBA team, not " + acr + "]", "current": f"  [{acr} jersey]"}.get(st, "")
            if trim and strict:
                flag += "  [neighbour removed]"
            if not strict:
                flag += "  [EDGE-CUT]"
            credits.append(f"[{slot}]\n" + _credit(title, ii))
            got.append(f"{title}{flag}")
    if credits:
        with open(os.path.join(fol, "credit.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(credits))
    return f"{len(got)} photo(s): " + " | ".join(got) if got else "NO PICTURE FOUND"


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
    ap.add_argument("--cands", type=int, default=0, help="also keep this many candidate cut-outs per player (_cands/) to choose by eye")
    ap.add_argument("--pics", type=int, default=3, help="photos to keep per player (cutout.png, cutout2.png, cutout3.png)")
    ap.add_argument("--tries", type=int, default=12, help="how many pictures to try per player (more = slower, finds more)")
    ap.add_argument("--only", help='"DEN:Nikola Jokic,LAC:Darius Garland": just these players')
    ap.add_argument("--shard", help='"i/n": only every n-th team, starting at i (to run several fetches side by side)')
    ap.add_argument("--credits-only", action="store_true", help="just rewrite CREDITS.txt")
    ap.add_argument("--file", action="append", help='"DEN:Nikola Jokic=File:Name.jpg"')
    ap.add_argument("--prefer", action="append", help='"DEN:Nikola Jokic=File:Name.jpg": try this picture first, but judge it like the rest')
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
    forced, photos, prefer = _pairs(a.file), _pairs(a.photo), _pairs(a.prefer)
    import requests
    session = requests.Session()
    missing = []
    for acr in teams:
        for player, _alias in roster.PLAYERS[acr]:
            key = f"{acr}:{player}"
            if a.only and key not in {x.strip() for x in a.only.split(",")}:
                continue
            print(f"{acr}  {player} ...", flush=True)
            try:
                msg = do_player(acr, player, a.out, a.redo, session, [x.strip() for x in forced[key].split('|')] if key in forced else None,
                                photos.get(key), cands=a.cands, prefer=prefer.get(key), tries=a.tries, pics=a.pics)
            except Exception as e:                       # noqa: BLE001
                msg = f"FAILED: {e}"
            print("   " + msg, flush=True)
            if msg.startswith(("NO PICTURE", "FAILED")):
                missing.append(key)
    print("\nDone." + (f" Still missing: {', '.join(missing)}" if missing else " Every player has a cutout."))


if __name__ == "__main__":
    main()
