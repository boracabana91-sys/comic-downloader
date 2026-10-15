"""Setup check: shows which parts work right now. Run: python -m sportsclipper check (or the Check setup button)."""
from __future__ import annotations
import os
import subprocess
import tempfile

from . import analyze, config, media, metadata, rights, selfcheck, sources


def run(cfg: dict, log=print, network: bool = True) -> list:
    results = []

    def add(ok, label, detail=""):
        results.append((ok, label, detail))
        log(f"{'OK  ' if ok else 'FAIL'} {label}" + (f" - {detail}" if detail else ""))

    try:
        out = subprocess.run([media.need("ffmpeg"), "-version"], capture_output=True, text=True)
        add(out.returncode == 0, "video engine (ffmpeg)", out.stdout.split("\n")[0][:60])
    except Exception as e:
        add(False, "video engine (ffmpeg)", str(e))

    try:
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "fake.mp4")
            selfcheck.make_video(p)
            c = config.load("/nonexistent")
            c.update(target_ratio=1.0, pad_s=0.5, min_clip_s=3)
            pl = analyze.plan(p, c, log=lambda *_: None)
            cov = lambda x: any(a <= x <= b for a, b in pl["segments"])
            ok = cov(5) and cov(35) and not cov(24) and not cov(55)
        add(ok, "cutting engine (test broadcast)", "live play kept, dead time cut" if ok else "cuts are wrong")
    except Exception as e:
        add(False, "cutting engine (test broadcast)", str(e)[:150])

    srcs = cfg["sources"]
    add(bool(srcs), "channels added", f"{len(srcs)} channel(s)" if srcs else "none yet - paste a channel link in the app")
    for d in srcs:
        s = rights.Source.from_dict(d)
        try:
            rights.check(s)
            add(True, f"permission: {s.name}", "confirmed")
        except rights.NotLicensed:
            add(False, f"permission: {s.name}", "not confirmed - this channel is skipped")
            continue
        if network and s.enabled and s.kind == "youtube":
            try:
                vids = sources.list_videos(s, limit=3)
                add(True, f"can reach: {s.name}", f"latest: {vids[0].title[:60]}" if vids else "no videos yet")
            except Exception as e:
                add(False, f"can reach: {s.name}", str(e)[:120])

    ai = cfg["ai"]
    if ai["enabled"]:
        key = metadata.api_key(cfg)
        add(bool(key), "titles by Claude Haiku 5.5", "key found" if key else "no key - plain titles will be used")
    else:
        add(True, "titles by Claude Haiku 5.5", "off - plain titles")

    up = cfg["upload"]
    if up["enabled"]:
        add(os.path.exists(up["client_secret"]), "YouTube: client secret file",
            up["client_secret"] or "not chosen")
        add(True, "YouTube: signed in", "yes" if os.path.exists(up["token"]) else
            "not yet - the first upload asks you to approve in the browser")
    else:
        add(True, "YouTube upload", "off - videos stay on your Mac")

    cl = cfg["cloudinary"]
    if cl["enabled"]:
        add(all(cl[k] for k in ("cloud_name", "api_key", "api_secret")), "Cloudinary backup",
            "keys set" if all(cl[k] for k in ("cloud_name", "api_key", "api_secret")) else "keys missing in config.json")
    else:
        add(True, "Cloudinary backup", "off")

    try:
        os.makedirs(cfg["output_dir"], exist_ok=True)
        tempfile.NamedTemporaryFile(dir=cfg["output_dir"]).close()
        add(True, "output folder", cfg["output_dir"])
    except Exception as e:
        add(False, "output folder", str(e))

    failed = [r for r in results if not r[0]]
    log("ALL GOOD" if not failed else f"{len(failed)} item(s) need attention (marked FAIL above)")
    return results
