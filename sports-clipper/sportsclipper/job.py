"""One clip from one local file: cut, render every size, make the thumbnail. Used by the window's test button."""
from __future__ import annotations
import json
import os
import re

from . import analyze, media, render, thumbnail


def clip_file(path: str, cfg: dict, title: str, log=print) -> dict:
    info = media.probe(path)
    plan = analyze.plan(path, cfg, log)
    slug = re.sub(r"[^\w-]+", "_", title)[:50] or "clip"
    folder = os.path.join(cfg["output_dir"], "manual", slug)
    outs = render.render(path, plan["segments"], info, cfg, os.path.join(folder, slug), log)
    thumb = None
    if cfg["thumbnail"]["enabled"]:
        try:
            pick = min(outs, key=lambda k: abs(k - 720))
            thumb = thumbnail.make_thumbnail(outs[pick], title, plan["kept_s"],
                                             os.path.join(folder, slug + "_thumb.jpg"), log)
        except Exception as e:
            log(f"thumbnail skipped: {e}")
    with open(os.path.join(folder, "clip.json"), "w", encoding="utf-8") as f:
        json.dump({"title": title}, f)
    return {"outputs": outs, "thumb": thumb, "kept_s": plan["kept_s"]}
