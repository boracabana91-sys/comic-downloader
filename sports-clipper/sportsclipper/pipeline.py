"""Scan -> rights check -> fetch -> analyze -> render -> thumbnail -> (backup) -> upload."""
from __future__ import annotations
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from . import progress
from . import analyze, config, media, metadata, render, rights, schedule, sources, store, uploader


def _dur(s: float) -> str:
    m, s = divmod(int(round(s)), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


class Pipeline:
    def __init__(self, cfg: dict, log=print, stop: threading.Event | None = None):
        self.cfg = cfg
        self.log = log
        self.stop = stop or threading.Event()
        self.db = store.Store(os.path.join(config.HOME, "state.sqlite"))

    def process(self, src: rights.Source, v: sources.Video, upload: bool = True) -> dict:
        cfg = self.cfg
        rights.check(src)                                          # hard gate: nothing runs unless licensed
        self.db.set(src.name, v.id, v.title, "working")
        self.log(f"[{src.name}] {v.title}")
        t = time.time()
        path = sources.fetch(v, cfg["work_dir"], min(max(cfg["resolutions"]), 2160))
        self.log(f"download took {_dur(time.time() - t)}")
        progress.set("analysing the video", None)
        t = time.time()
        info_in = media.probe(path)
        res = analyze.plan(path, cfg, self.log)
        self.log(f"analysis took {_dur(time.time() - t)}")
        slug = re.sub(r"[^\w-]+", "_", v.title)[:50]
        out_base = os.path.join(cfg["output_dir"], datetime.now().strftime("%Y%m%d"), slug, slug)

        # the upload size first, on its own, so it can go up while the other sizes are made
        hs = render.ladder(info_in["height"], cfg["resolutions"], cfg["allow_upscale"])
        first = render.first_size(hs, cfg["upload_resolution"])
        t = time.time()
        outs = render.render(path, res["segments"], info_in, cfg, out_base, self.log, only=[first])
        self.log(f"{first}p ready in {_dur(time.time() - t)}")
        result = {"outputs": outs, "kept_s": res["kept_s"]}

        thumb = None
        if cfg["thumbnail"]["enabled"]:
            try:
                from . import thumbnail
                progress.set("making the thumbnail", None)
                thumb = thumbnail.make_thumbnail(outs[first], v.title, res["kept_s"], out_base + "_thumb.jpg", self.log)
                result["thumbnail"] = thumb
            except Exception as e:
                self.log(f"thumbnail skipped: {e}")

        if upload and cfg["upload"]["enabled"]:
            best = outs[first]
            meta = metadata.build(cfg, v.title, src.name, res["kept_s"], self.log)
            lo, hi = cfg["publish_delay_min"]
            due = v.published + timedelta(minutes=random.uniform(lo, hi))
            publish_at = None
            if due > datetime.now(timezone.utc) + timedelta(minutes=2):
                publish_at = due.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                self.log(f"scheduled to go public at {due.astimezone().strftime('%H:%M')} (source + {lo}-{hi} min)")
            progress.set("uploading to YouTube", None)
            t = time.time()
            result["youtube_id"] = uploader.upload_youtube(cfg, best, meta, publish_at, self.log)
            self.log(f"uploaded in {_dur(time.time() - t)}: https://youtu.be/{result['youtube_id']}")
            if thumb:
                try:
                    uploader.set_thumbnail(cfg, result["youtube_id"], thumb)
                    self.log("thumbnail set on YouTube")
                except Exception as e:
                    self.log(f"thumbnail upload failed: {e}")
        self.db.set(src.name, v.id, v.title, "done", str(result.get("youtube_id", "")))

        # the other sizes, several at once
        rest = [h for h in hs if h != first]
        if rest:
            t = time.time()
            outs.update(render.render(path, res["segments"], info_in, cfg, out_base, self.log, only=rest))
            self.log(f"other sizes ({', '.join(f'{h}p' for h in rest)}) took {_dur(time.time() - t)}")
        if cfg["cloudinary"]["enabled"]:
            try:
                result["cloudinary"] = uploader.backup_cloudinary(cfg, outs[max(outs)], self.log)
            except Exception as e:
                self.log(f"Cloudinary backup failed: {e}")
        return result

    def scan_once(self, upload: bool = True) -> int:
        n = 0
        for d in self.cfg["sources"]:
            if self.stop.is_set():
                break
            src = rights.Source.from_dict(d)
            if not src.enabled:
                continue
            try:
                rights.check(src)
            except rights.NotLicensed as e:
                self.log(str(e)); continue
            try:
                vids = sources.list_videos(src)
            except Exception as e:
                self.log(f"[{src.name}] could not list videos: {e}"); continue
            first = not any(r[0] == src.name for r in self.db.rows(1000))
            if first and src.kind != "folder":                  # don't clip the whole back catalogue
                for v in vids:
                    self.db.set(src.name, v.id, v.title, "baseline")
                self.log(f"[{src.name}] first scan: {len(vids)} existing videos noted; only new uploads will be processed")
                continue
            for v in reversed(vids):
                if self.stop.is_set():
                    break
                if self.db.seen(src.name, v.id):
                    continue
                try:
                    self.process(src, v, upload)
                    n += 1
                except Exception as e:
                    self.db.set(src.name, v.id, v.title, "error", str(e)[:300])
                    self.log(f"[{src.name}] FAILED {v.title}: {e}")
        return n

    def run_forever(self):
        last = None
        while not self.stop.is_set():
            now = datetime.now()
            nxt = schedule.next_scan(now, self.cfg["schedule"], last)
            self.log(f"next scan at {nxt.strftime('%a %H:%M')}")
            while datetime.now() < nxt and not self.stop.is_set():
                time.sleep(min(30, max(1, (nxt - datetime.now()).total_seconds())))
            if self.stop.is_set():
                break
            last = datetime.now()
            done = self.scan_once()
            self.log(f"scan finished: {done} new video(s) processed")
