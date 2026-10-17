"""vv22: everything about one YouTube post, decided before any upload: file name stem, title, description, tags.
Used by the 24/7 scan, the reclip buttons and the test button, so they all follow the same rules."""
from __future__ import annotations
from datetime import datetime

from . import captions, metadata, rules


def plan_post(cfg: dict, source_title: str, published: datetime | None, kept_s: float, log=print, url: str = "",
              source_name: str = "") -> dict:
    teams = rules.teams_of(source_title)
    when = rules.game_datetime(source_title, published)
    stem = rules.file_stem(cfg, teams, when)
    cues = captions.fetch(url, log) if (url and cfg["ai"]["enabled"]) else []
    meta = metadata.build(cfg, source_title, source_name, kept_s, log, captions=cues, published=published)
    return {"teams": teams, "stem": stem, "meta": meta, "when": when}


def upload_title(plan: dict, source_title: str) -> str:
    """The title the thumbnail and the intro picture read (FLASHY / GREAT / FULL GAME follows the post's title)."""
    return plan["meta"]["title"] if plan["teams"] else source_title
