"""Title / description / tags, written by three AI writers (vv21).

  writer 1 - SEO and title: the best title in the fixed format and which headline word (FLASHY / GREAT) engages better;
             also picks the 2-3 commentary lines for the description from the captions.
  writer 2 - reach: tags and hashtags for NBA fans and basketball nerds.
  writer 3 - team fans: tags and hashtags for the true supporters of the two teams playing.

Without an Anthropic key (or with the AI off) a plain template is used, so the pipeline never stops."""
from __future__ import annotations
import json
import os
import re
import threading
import urllib.request
from datetime import datetime

from . import roster, thumbnail

DISCLAIMER = ("This video was edited to follow youtube's fair use guidelines: Copyright Disclaimer under Section 107 of "
              "the copyright act 1976, allowance is made for fair use for purposes such as criticism, comment, news "
              "reporting, scholarship, and research.")


def api_key(cfg: dict) -> str:
    return cfg["ai"].get("api_key") or os.environ.get(cfg["ai"]["api_key_env"], "")


def long_date(d: datetime) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def team_names(title: str) -> list:
    return [roster.TEAMS[a][0] for a in thumbnail.parse_teams(title) if a in roster.TEAMS]


def game_date(title: str, published: datetime | None = None) -> str:
    m = re.search(r"\b(" + "|".join(x[:3] for x in thumbnail.MONTHS) + r")[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", title, re.I)
    if m:
        full = next(x for x in thumbnail.MONTHS if x[:3].lower() == m.group(1).lower())
        return f"{full} {int(m.group(2))}, {m.group(3)}"
    return long_date(published or datetime.now())


def make_title(names: list, word: str, date: str, fallback: str) -> str:
    if len(names) != 2:
        return fallback[:100]
    return f"{names[0]} VS {names[1]} - {word} HIGHLIGHTS - {date}"[:100]


def hashtags(items, limit=15) -> list:
    out, seen = [], set()
    for t in items:
        t = re.sub(r"[^A-Za-z0-9_]", "", str(t).lstrip("#"))
        if t and t.lower() not in seen:
            seen.add(t.lower()); out.append("#" + t)
    return out[:limit]


def tag_list(items, limit=30) -> list:
    out, seen, total = [], set(), 0
    for t in items:
        t = re.sub(r"\s+", " ", str(t).lstrip("#")).strip()
        if not t or t.lower() in seen or len(t) > 40:
            continue
        if total + len(t) + 1 > 480:                       # YouTube allows 500 characters of tags in all
            break
        seen.add(t.lower()); out.append(t); total += len(t) + 1
    return out[:limit]


def description(teasers: list, tags: list, cta: str) -> str:
    parts = [DISCLAIMER]
    if teasers:
        parts.append("\n".join(f"“{t.strip().strip('“”\"')}”" for t in teasers[:3]))
    if cta:
        parts.append(cta)
    if tags:
        parts.append(" ".join(tags[:15]))
    return "\n\n".join(parts)


def _ask(cfg: dict, prompt: str, max_tokens: int = 700) -> dict:
    ai = cfg["ai"]
    body = json.dumps({"model": ai["model"], "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": api_key(cfg), "anthropic-version": "2023-06-01", "content-type": "application/json"})
    txt = json.load(urllib.request.urlopen(req, timeout=90))["content"][0]["text"]
    return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])


def seo_prompt(names, date, cands, kept_min):
    return (
        "You are the SEO writer for an NBA highlights YouTube channel: the best there is at titles that earn clicks and "
        f"watch time honestly. Game: {' vs '.join(names)}, {date}. The video is a {kept_min:.0f}-minute condensed cut.\n"
        "1) Choose the headline word that will engage better for this matchup: FLASHY (highlight-reel plays, "
        "star power, a high-scoring or high-flying game) or GREAT (a tight, quality or historic game). "
        "Think about how these titles perform on YouTube and pick one.\n"
        "2) From the commentary lines below choose the 2 or 3 best, most vivid lines of a commentator describing a great "
        "play. Copy them exactly as written (they may be shortened); never invent a line. If none is usable return [].\n"
        f"Commentary lines: {json.dumps(cands)}\n"
        'Return ONLY JSON: {"word": "FLASHY" or "GREAT", "why": "<10 words", "teasers": ["...", "..."]}')


def tags_prompt(kind, names, date):
    who = ("the wider audience: NBA fans, basketball nerds, highlight and fantasy-basketball viewers" if kind == "reach"
           else f"die-hard, true supporters of the {names[0]} and the {names[1]} - use each team's nickname, "
                "its stars, its fan-base slang and the matchup")
    return (f"You write YouTube tags and hashtags for an NBA highlights video: {' vs '.join(names)}, {date}. "
            f"Target audience: {who}. Be specific, no spam, nothing misleading, no other sport. "
            'Return ONLY JSON: {"tags": [up to 20 short search tags], "hashtags": [up to 8 hashtag words, no #]}')


def build(cfg: dict, source_title: str, source_name: str, kept_s: float, log=print,
          captions: list | None = None, published: datetime | None = None) -> dict:
    names = team_names(source_title)
    date = game_date(source_title, published)
    cta = cfg.get("description_cta", "Subscribe for every game's highlights.")
    base_tags = list(cfg.get("tags", []))
    fb_title = (make_title(names, "GREAT", date, f"{source_title} | Condensed Highlights") if names
                else f"{source_title} | Condensed Highlights"[:100])
    fallback = {"title": fb_title, "description": description([], hashtags(names and ["NBA", "NBAHighlights"] or ["NBA"]), cta),
                "tags": tag_list(base_tags + ["NBA", "NBA highlights"] + names)}
    ai = cfg["ai"]
    if not ai["enabled"]:
        return fallback
    if not api_key(cfg):
        log("no Anthropic API key set - using plain titles (add it in config.json, see README)")
        return fallback
    from . import captions as cap
    cands = cap.candidates(captions or [])
    if not captions:
        log("no captions found for this video - the description has no commentator lines")
    res: dict = {}

    def run(key, prompt):
        try:
            res[key] = _ask(cfg, prompt)
        except Exception as e:                              # one writer failing never stops the others
            log(f"AI writer '{key}' failed ({str(e)[:120]})")
    nm = names or [source_title]
    threads = [threading.Thread(target=run, args=a) for a in (
        ("seo", seo_prompt(nm, date, cands, kept_s / 60)),
        ("reach", tags_prompt("reach", nm, date)),
        ("fans", tags_prompt("fans", nm, date)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seo = res.get("seo", {})
    word = "FLASHY" if str(seo.get("word", "")).upper() == "FLASHY" else "GREAT"
    teasers = [t for t in (seo.get("teasers") or [])          # only real commentary: each line must come from the captions
               if isinstance(t, str) and t.strip() and any(t.strip().lower() in c.lower() for c in cands)][:3]
    tags_all = (res.get("fans", {}).get("tags", []) + res.get("reach", {}).get("tags", []) + base_tags +
                ["NBA", "NBA highlights"])
    tag_hash = hashtags(res.get("fans", {}).get("hashtags", [])[:4] + res.get("reach", {}).get("hashtags", [])[:4] + ["NBA"])
    if log:
        log(f"title word: {word} ({seo.get('why', 'no reason given')})")
    return {"title": make_title(names, word, date, fb_title) if names else fb_title,
            "description": description(teasers, tag_hash, cta),
            "tags": tag_list(tags_all)}
