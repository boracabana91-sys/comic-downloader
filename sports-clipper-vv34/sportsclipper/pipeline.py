"""Scan -> rights check -> fetch -> analyze -> render -> thumbnail -> (backup) -> upload."""
from __future__ import annotations
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from . import progress
from . import analyze, captions, config, finish, media, post, render, rights, rules, schedule, sources, store, uploader, wake


def _dur(s: float) -> str:
    m, s = divmod(int(round(s)), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


class Pipeline:
    def __init__(self, cfg: dict, log=print, stop: threading.Event | None = None):
        self.cfg = cfg
        self.log = log
        self.stop = stop or threading.Event()
        self.db = store.Store(os.path.join(config.HOME, "state.sqlite"))
        sources.configure(cfg)                                      # vv33: browser to borrow the YouTube login from, if YouTube asks
        self.on_preview = None                                      # vv24: called with the planned post BEFORE the video is cut
        self.left_out = []                                          # vv30: videos the last scan_view left out (with the reason)
        self.on_scanned = None                                      # vv28/vv29: called with (new, held, older videos) after each channel is looked at

    def process(self, src: rights.Source, v: sources.Video, upload: bool = True, enforce: bool = False) -> dict:
        """enforce=True (the 24/7 scan): only a game video that follows the channel's pattern is taken."""
        cfg = self.cfg
        rights.check(src)                                          # hard gate: nothing runs unless licensed
        if enforce:
            why = rules.skip_reason(v.title, v.url, v.group, v.duration)
            if why:
                self.db.set(src.name, v.id, v.title, "skipped", why)
                self.log(f"[{src.name}] skipped '{v.title}': {why}")
                return {"skipped": why}
        if enforce and self.db.status(src.name, v.id) == "done":
            self.log(f"[{src.name}] already clipped/uploaded: {v.title}")
            return {"skipped": "already done"}
        if enforce:
            w = rules.hold_match(v.title, cfg.get("hold_words"))
            if w:                                                  # vv28: a hold word in the title: not downloaded, not reclipped
                self.db.set(src.name, v.id, v.title, "hold", f"hold word: {w}")
                self.log(f"[{src.name}] HELD '{v.title}': hold word '{w}' - not reclipped (use its link to reclip it yourself)")
                return {"held_word": w}
        self.db.set(src.name, v.id, v.title, "working")
        self.log(f"[{src.name}] {v.title}")
        t = time.time()
        path = sources.fetch(v, cfg["work_dir"], 4320)             # always the best resolution there is
        self.log(f"download took {_dur(time.time() - t)}")
        progress.set("analysing the video", None)
        t = time.time()
        info_in = media.probe(path)
        if enforce and info_in.get("duration") and info_in["duration"] < rules.MIN_GAME_S:
            why = rules.skip_reason(v.title, v.url, v.group, info_in["duration"])
            self.db.set(src.name, v.id, v.title, "skipped", why)
            self.log(f"[{src.name}] skipped '{v.title}': {why}")
            return {"skipped": why}
        cues = captions.fetch(v.url, self.log) if (v.url and cfg["ai"]["enabled"]) else []   # the announcers' words, once
        res = analyze.plan(path, cfg, self.log, cues=cues)
        self.log(f"analysis took {_dur(time.time() - t)}")
        do_up = upload and cfg["upload"]["enabled"]
        pp = post.plan_post(cfg, v.title, v.published.astimezone(), res["kept_s"], self.log, v.url, src.name, cues=cues)
        slug = pp["stem"] if pp and pp["stem"] else re.sub(r"[^\w-]+", "_", v.title)[:50]
        out_base = os.path.join(cfg["output_dir"], datetime.now().strftime("%Y%m%d"), slug, slug)
        ttl = post.upload_title(pp, v.title) if pp else v.title
        self._preview(pp, v.title, out_base, cfg, info_in)

        # the upload size first, on its own, so it can go up while the other sizes are made
        hs = render.ladder(info_in["height"], cfg["resolutions"], cfg["allow_upscale"])
        first = render.first_size(hs, cfg["upload_resolution"])
        intro = finish.intro_picture(cfg, ttl, res["kept_s"], out_base, self.log)
        t = time.time()
        outs = render.render(path, res["segments"], info_in, cfg, out_base, self.log, only=[first], intro=intro)
        self.log(f"{first}p ready in {_dur(time.time() - t)}")
        result = {"outputs": outs, "kept_s": res["kept_s"], "upload_file": outs[first]}
        if pp:
            result["post"] = pp

        thumb = finish.make_thumb(cfg, outs[first], ttl, res["kept_s"], out_base, self.log, ready=intro)
        if thumb:
            result["thumbnail"] = thumb
        finish.add_cover(cfg, outs, thumb, self.log, only=[first])

        result["checks"] = rules.check(pp["meta"], outs[first], pp["teams"], v.title, cfg)       # on the finished file
        if do_up:
            best = outs[first]
            meta = pp["meta"]
            checks = rules.check(meta, best, pp["teams"], v.title, cfg)
            result["checks"] = checks
            bad = rules.failed(checks)
            if bad:                                                # the guidelines are not met: nothing is uploaded
                folder = os.path.dirname(out_base)
                result["held"] = bad
                self.log("!! HELD, NOT UPLOADED: '" + v.title + "' breaks the channel rules: " + "; ".join(bad)
                         + f"  -- the finished videos are kept here: {folder}")
                self.db.set(src.name, v.id, v.title, "held", "; ".join(bad)[:300])
                self._render_rest(path, res, info_in, cfg, out_base, outs, hs, first, thumb, intro)
                return result
            lo, hi = cfg["publish_delay_min"]
            due = v.published + timedelta(minutes=random.uniform(lo, hi))
            publish_at = None
            if cfg["upload"].get("privacy") == "public" and due > datetime.now(timezone.utc) + timedelta(minutes=2):   # private / unlisted means exactly that: never scheduled public
                publish_at = due.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                self.log(f"scheduled to go public at {due.astimezone().strftime('%H:%M')} (source + {lo}-{hi} min)")
            progress.set("uploading to YouTube", None)
            t = time.time()
            try:
                result["youtube_id"] = uploader.upload_youtube(cfg, best, meta, publish_at, self.log)
            except Exception as e:
                folder = os.path.dirname(out_base)
                self.log(f"!! UPLOAD FAILED for '{v.title}': {e}  -- the finished videos are kept here: {folder}")
                self._render_rest(path, res, info_in, cfg, out_base, outs, hs, first, thumb, intro)
                raise
            self.log(f"uploaded in {_dur(time.time() - t)}: https://youtu.be/{result['youtube_id']}")
            if thumb:
                try:
                    progress.set("setting the YouTube thumbnail", None)
                    uploader.set_thumbnail(cfg, result["youtube_id"], thumb, self.log)
                    self.log("thumbnail set on YouTube (confirmed by YouTube)")
                except Exception as e:
                    result["thumbnail_error"] = str(e)
                    self.log(f"!! The video is on YouTube, but its thumbnail was NOT set: {e}  "
                             f"The picture is saved here: {thumb}")
            elif cfg["thumbnail"]["enabled"]:
                self.log("!! The video is on YouTube, but no thumbnail was made, so YouTube picked its own.")
        self.db.set(src.name, v.id, v.title, "done", str(result.get("youtube_id", "")))
        self._render_rest(path, res, info_in, cfg, out_base, outs, hs, first, thumb, intro)
        if cfg["cloudinary"]["enabled"]:
            try:
                result["cloudinary"] = uploader.backup_cloudinary(cfg, outs[max(outs)], self.log)
            except Exception as e:
                self.log(f"Cloudinary backup failed: {e}")
        return result

    def _preview(self, pp, title, out_base, cfg, info_in):
        """vv24: show the YT Preview now (file name, title, description, tags, rules) - the video is not cut yet."""
        self.log(f"YT Preview ready: {pp['meta']['title']}")
        if not self.on_preview:
            return
        hs = render.ladder(info_in["height"], cfg["resolutions"], cfg["allow_upscale"])
        first = render.first_size(hs, cfg["upload_resolution"])
        f = render.out_path(out_base, first, info_in["height"])
        try:
            self.on_preview({"post": pp, "preview": True, "upload_file": f,
                             "checks": rules.check(pp["meta"], f, pp["teams"], title, cfg, pending=True)})
        except Exception as e:                                      # the preview must never stop a clip
            self.log(f"(YT Preview skipped: {e})")

    def _render_rest(self, path, res, info_in, cfg, out_base, outs, hs, first, thumb, intro):
        """The other sizes (kept on the drive; YouTube makes its own lower sizes from the uploaded one)."""
        rest = [h for h in hs if h != first and h not in outs]
        if rest:
            t = time.time()
            new = render.render(path, res["segments"], info_in, cfg, out_base, self.log, only=rest, intro=intro)
            finish.add_cover(cfg, new, thumb, self.log)
            outs.update(new)
            self.log(f"other sizes ({', '.join(f'{h}p' for h in rest)}) took {_dur(time.time() - t)}")

    def selected_sources(self) -> list:
        """Only the channels highlighted in the list (saved as cfg['scan_only']) are scanned."""
        only = set(self.cfg.get("scan_only") or [])
        return [d for d in self.cfg["sources"] if d.get("name") in only]

    def scan_view(self, src: rights.Source, limit: int = 5, baseline_is_old: bool = False, vids: list | None = None) -> tuple:
        """vv29: (new, held, old) for a channel. new = the newest `limit` game videos not clipped/uploaded yet (green);
        held = a hold word is in the title (red, remembered in the held list); old = every other game video, shown with its date.
        Shorts, reels, clips and titles that are not 'Team vs Team ... Highlights' are left out. Nothing here downloads."""
        new, held, old = [], [], []
        words = self.cfg.get("hold_words")
        counts = {"skip": 0}
        left = []
        if vids is None:
            vids = sources.list_recent(src, 50, self.log)
        for v in vids:
            v.src_name = src.name
            why = rules.skip_reason(v.title, v.url, v.group, v.duration)
            if why:
                counts["skip"] += 1
                v.state = "left out: " + why
                left.append(v)
                continue
            st = self.db.status(src.name, v.id)
            if st == "done" or (baseline_is_old and st in ("baseline", "skipped")):
                v.state = "done" if st == "done" else ""
                old.append(v)
                continue
            w = rules.hold_match(v.title, words)
            if w:
                if st != "hold":
                    self.db.set(src.name, v.id, v.title, "hold", f"hold word: {w}")
                v.state = "held"
                held.append(v)
            elif len(new) < limit:
                v.state = "new"
                new.append(v)
            else:
                old.append(v)
        owner = next((v.channel_name for v in vids if v.channel_name), "")
        if owner and src.kind == "youtube" and not src.location.startswith("playlist:") and owner.strip().lower() != src.name.strip().lower():
            self.log(f"[{src.name}] WARNING: this channel id belongs to '{owner}', not '{src.name}'. "
                     f"Remove it and add the channel again (paste its link) so the right videos are scanned.")
        for v in left[:12]:                                       # vv30: say WHY each one was left out
            self.log(f"[{src.name}]   left out: '{v.title[:90]}' ({v.state[10:]}; {int(v.duration or 0)}s, {v.group or 'feed'})")
        self.left_out = left
        self.log(f"[{src.name}] checked {len(vids)} videos: {counts['skip']} Shorts/clips/other titles left out, "
                 f"{len(new)} new, {len(held)} held, {len(old)} older")
        return new, held, old

    def scan_preview(self, src: rights.Source, limit: int = 5) -> tuple:
        """(good, held) kept for older callers: the newest unprocessed game videos and the held ones."""
        new, held, _old = self.scan_view(src, limit, baseline_is_old=True)
        return new, held

    def latest_new(self, src: rights.Source, limit: int = 5) -> list:
        """The newest videos of a channel that were not processed yet (newest first), without the held ones."""
        return self.scan_preview(src, limit)[0]

    def scan_once(self, upload: bool = True) -> int:
        n = 0
        picked = self.selected_sources()
        if not picked:
            self.log("nothing is highlighted: click the channel(s) to scan in the channel list, then scan again")
            return 0
        budget = int(self.cfg.get("videos_per_scan", 3))
        for d in picked:
            if self.stop.is_set() or n >= budget:
                break
            src = rights.Source.from_dict(d)
            if not src.enabled:
                continue
            try:
                rights.check(src)
            except rights.NotLicensed as e:
                self.log(str(e)); continue
            try:
                vids = sources.list_recent(src, 50, self.log)
            except Exception as e:
                self.log(f"[{src.name}] could not list videos: {e}"); continue
            first = not any(r[0] == src.name for r in self.db.rows(1000))
            if first and src.kind != "folder":                  # don't clip the whole back catalogue
                for v in vids:
                    self.db.set(src.name, v.id, v.title, "baseline")
                self.log(f"[{src.name}] first scan: {len(vids)} existing videos noted; only new uploads will be processed")
                continue
            unseen, held_now = [], []
            for x in vids:
                if self.db.seen(src.name, x.id):
                    continue
                why = rules.skip_reason(x.title, x.url, x.group, x.duration)     # Shorts, clips, other sports: never downloaded
                if why:
                    self.db.set(src.name, x.id, x.title, "skipped", why)
                    self.log(f"[{src.name}] skipped '{x.title}': {why}")
                    continue
                w = rules.hold_match(x.title, self.cfg.get("hold_words"))
                if w:                                                          # vv28: hold words: not downloaded, not reclipped
                    if not self.db.is_held(src.name, x.id):
                        self.log(f"[{src.name}] HELD '{x.title}': hold word '{w}' - not reclipped (see the Held titles list)")
                    self.db.set(src.name, x.id, x.title, "hold", f"hold word: {w}")
                    x.src_name = src.name
                    held_now.append(x)
                else:
                    unseen.append(x)
            if self.on_scanned:
                for x in unseen:
                    x.src_name = src.name
                old = [x for x in vids if x.id not in {u.id for u in unseen[:budget]} and x.id not in {h.id for h in held_now}
                       and not rules.skip_reason(x.title, x.url, x.group, x.duration)]
                for x in unseen[:budget]:
                    x.state = "new"
                for x in held_now:
                    x.state = "held"
                for x in old:
                    x.state = "done" if self.db.status(src.name, x.id) == "done" else ""
                self.on_scanned(unseen[:budget], held_now, old)
            for v in reversed(unseen[:budget]):                                  # the newest few, oldest first
                if self.stop.is_set() or n >= budget:
                    break
                try:
                    r = self.process(src, v, upload, enforce=True)
                    if not r.get("skipped"):
                        n += 1
                except Exception as e:
                    self.db.set(src.name, v.id, v.title, "error", str(e)[:300])
                    self.log(f"[{src.name}] FAILED {v.title}: {e}")
        return n

    def run_forever(self):
        with wake.KeepAwake():                                  # the Mac stays awake while the 24/7 loop runs
            self._loop()

    def _loop(self):
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
