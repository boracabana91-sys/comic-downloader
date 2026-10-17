"""One clip from one local file: cut, make the main size first, the thumbnail, then the other sizes.
Used by the window's test button. Logs how long each step took."""
from __future__ import annotations
import json
import os
import re
import time

from . import analyze, finish, media, post, progress, render, rules
from .pipeline import _dur


def clip_file(path: str, cfg: dict, title: str, log=print) -> dict:
    progress.set("analysing the video", None)
    t = time.time()
    info = media.probe(path)
    plan = analyze.plan(path, cfg, log)
    log(f"analysis took {_dur(time.time() - t)}")
    pp = post.plan_post(cfg, title, None, plan["kept_s"], log)          # title, tags, description, file name: same rules as the scan
    ttl = post.upload_title(pp, title)
    slug = pp["stem"] or re.sub(r"[^\w-]+", "_", title)[:50] or "clip"
    folder = os.path.join(cfg["output_dir"], "manual", slug)
    base = os.path.join(folder, slug)
    hs = render.ladder(info["height"], cfg["resolutions"], cfg["allow_upscale"])
    first = render.first_size(hs, cfg.get("upload_resolution", 1080))
    intro = finish.intro_picture(cfg, ttl, plan["kept_s"], base, log)
    t = time.time()
    outs = render.render(path, plan["segments"], info, cfg, base, log, only=[first], intro=intro)
    log(f"{first}p ready in {_dur(time.time() - t)}")
    thumb = finish.make_thumb(cfg, outs[first], ttl, plan["kept_s"], base, log, ready=intro)
    finish.add_cover(cfg, outs, thumb, log, only=[first])
    with open(os.path.join(folder, "clip.json"), "w", encoding="utf-8") as f:
        json.dump({"title": title}, f)
    rest = [h for h in hs if h != first]
    if rest:
        t = time.time()
        new = render.render(path, plan["segments"], info, cfg, base, log, only=rest, intro=intro)
        finish.add_cover(cfg, new, thumb, log)
        outs.update(new)
        log(f"other sizes ({', '.join(f'{h}p' for h in rest)}) took {_dur(time.time() - t)}")
    checks = rules.check(pp["meta"], outs[first], pp["teams"], title, cfg)
    return {"outputs": outs, "thumb": thumb, "kept_s": plan["kept_s"], "post": pp, "checks": checks, "upload_file": outs[first]}
