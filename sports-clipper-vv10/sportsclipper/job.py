"""One clip from one local file: cut, make the main size first, the thumbnail, then the other sizes.
Used by the window's test button. Logs how long each step took."""
from __future__ import annotations
import json
import os
import re
import time

from . import analyze, media, progress, render, thumbnail
from .pipeline import _dur


def clip_file(path: str, cfg: dict, title: str, log=print) -> dict:
    progress.set("analysing the video", None)
    t = time.time()
    info = media.probe(path)
    plan = analyze.plan(path, cfg, log)
    log(f"analysis took {_dur(time.time() - t)}")
    slug = re.sub(r"[^\w-]+", "_", title)[:50] or "clip"
    folder = os.path.join(cfg["output_dir"], "manual", slug)
    base = os.path.join(folder, slug)
    hs = render.ladder(info["height"], cfg["resolutions"], cfg["allow_upscale"])
    first = render.first_size(hs, cfg.get("upload_resolution", 1080))
    t = time.time()
    outs = render.render(path, plan["segments"], info, cfg, base, log, only=[first])
    log(f"{first}p ready in {_dur(time.time() - t)}")
    thumb = None
    if cfg["thumbnail"]["enabled"]:
        progress.set("making the thumbnail", None)
        try:
            thumb = thumbnail.make_thumbnail(outs[first], title, plan["kept_s"], base + "_thumb.jpg", log)
        except Exception as e:
            log(f"thumbnail skipped: {e}")
    with open(os.path.join(folder, "clip.json"), "w", encoding="utf-8") as f:
        json.dump({"title": title}, f)
    rest = [h for h in hs if h != first]
    if rest:
        t = time.time()
        outs.update(render.render(path, plan["segments"], info, cfg, base, log, only=rest))
        log(f"other sizes ({', '.join(f'{h}p' for h in rest)}) took {_dur(time.time() - t)}")
    return {"outputs": outs, "thumb": thumb, "kept_s": plan["kept_s"]}
