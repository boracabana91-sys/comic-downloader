"""Finds finished clips in the output folder so the window can show thumbnails and videos."""
from __future__ import annotations
import json
import os
import re

VIDEO_RE = re.compile(r"^(?P<slug>.+)_(?P<h>\d{3,4})p(?P<up>_upscaled)?\.mp4$")


def scan_outputs(output_dir: str) -> list:
    """Newest first: [{'title', 'folder', 'thumb' (path or None), 'videos' [(height, path)] best first}]."""
    out = []
    if not os.path.isdir(output_dir):
        return out
    for root, _dirs, files in os.walk(output_dir):
        groups = {}
        for f in files:
            m = VIDEO_RE.match(f)
            if m:
                groups.setdefault(m.group("slug"), []).append((int(m.group("h")), os.path.join(root, f)))
        for slug, vids in groups.items():
            thumb = os.path.join(root, slug + "_thumb.jpg")
            vids.sort(reverse=True)
            title = slug.replace("_", " ")
            meta = os.path.join(root, "clip.json")
            if os.path.exists(meta):
                try:
                    title = json.load(open(meta, encoding="utf-8")).get("title", title)
                except (OSError, ValueError):
                    pass
            out.append({"title": title, "folder": root,
                        "thumb": thumb if os.path.exists(thumb) else None, "videos": vids})
    out.sort(key=lambda r: max(os.path.getmtime(p) for _, p in r["videos"]), reverse=True)
    return out
