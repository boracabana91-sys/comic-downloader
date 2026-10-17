"""vv22: everything about one YouTube post, decided before any upload: file name stem, title, description, tags.
Used by the 24/7 scan, the reclip buttons and the test button, so they all follow the same rules."""
from __future__ import annotations
from datetime import datetime

from . import captions, metadata, rules


def plan_post(cfg: dict, source_title: str, published: datetime | None, kept_s: float, log=print, url: str = "",
              source_name: str = "", cues: list | None = None) -> dict:
    teams = rules.teams_of(source_title)
    when = rules.game_datetime(source_title, published)
    stem = rules.file_stem(cfg, teams, when)
    if cues is None:
        cues = captions.fetch(url, log) if (url and cfg["ai"]["enabled"]) else []
    meta = metadata.build(cfg, source_title, source_name, kept_s, log, captions=cues, published=published)
    return {"teams": teams, "stem": stem, "meta": meta, "when": when}


def upload_title(plan: dict, source_title: str) -> str:
    """The title the thumbnail and the intro picture read (FLASHY / GREAT / FULL GAME follows the post's title)."""
    return plan["meta"]["title"] if plan["teams"] else source_title


PENDING_LINE = "[Pending - the announcer's best lines are added after the video is downloaded]"


def preview_post(cfg: dict, source_title: str, published: datetime | None, source_name: str = "") -> dict:
    """vv25: the post as far as it can be known BEFORE the download: file name, title, tags, and the description with
    the commentary lines marked pending. No network, no AI, instant."""
    c = dict(cfg); c["ai"] = dict(cfg["ai"], enabled=False)
    pp = plan_post(c, source_title, published, 0.0, lambda m: None, "", source_name, cues=[])
    d = pp["meta"]["description"]
    parts = d.split("\n\n")
    parts.insert(1, PENDING_LINE)
    pp["meta"] = dict(pp["meta"], description="\n\n".join(parts))
    return pp
