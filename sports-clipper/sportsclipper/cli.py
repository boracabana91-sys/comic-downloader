from __future__ import annotations
import argparse
import os
import sys

from . import analyze, config, media, pipeline, render


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sportsclipper")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("clip", help="cut one local video (no upload) - for testing")
    c.add_argument("file"); c.add_argument("--out", default=None)
    c.add_argument("--ratio", type=float, default=None)
    sub.add_parser("scan", help="scan all licensed sources once")
    sub.add_parser("run", help="scan on your schedule, 24/7")
    sub.add_parser("gui", help="open the window")
    sub.add_parser("install-launchd", help="Mac: start automatically at login and keep running")
    a = ap.parse_args(argv)
    cfg = config.load()
    if a.cmd in (None, "gui"):
        from . import gui
        return gui.main()
    if a.cmd == "clip":
        if a.ratio:
            cfg["target_ratio"] = a.ratio
        p = analyze.plan(a.file, cfg)
        out = a.out or os.path.join(cfg["output_dir"], "manual", os.path.splitext(os.path.basename(a.file))[0])
        outs = render.render(a.file, p["segments"], p["info"], cfg, out)
        for h, f in sorted(outs.items(), reverse=True):
            print(f"{h}p  {f}")
        return 0
    pl = pipeline.Pipeline(cfg)
    if a.cmd == "scan":
        pl.scan_once(); return 0
    if a.cmd == "run":
        try:
            pl.run_forever()
        except KeyboardInterrupt:
            pass
        return 0
    if a.cmd == "install-launchd":
        return install_launchd()
    return 1


def install_launchd() -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    plist = os.path.expanduser("~/Library/LaunchAgents/com.sportsclipper.plist")
    log = os.path.join(config.HOME, "service.log")
    os.makedirs(config.HOME, exist_ok=True)
    os.makedirs(os.path.dirname(plist), exist_ok=True)
    open(plist, "w").write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.sportsclipper</string>
<key>ProgramArguments</key><array><string>{sys.executable}</string><string>-m</string><string>sportsclipper</string><string>run</string></array>
<key>WorkingDirectory</key><string>{here}</string>
<key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>{log}</string><key>StandardErrorPath</key><string>{log}</string>
</dict></plist>
""")
    print(f"Wrote {plist}\nStart now with:  launchctl load {plist}\nStop with:       launchctl unload {plist}")
    print("Keep the Mac awake for 24/7: System Settings > Battery/Energy > prevent sleep, or run: caffeinate -s")
    return 0
