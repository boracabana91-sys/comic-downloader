"""vv27: update the app by dragging the new SportsClipper-Mac.zip (or the new SportsClipper.app) onto the window.
The old app is kept as a backup, your settings and files in ~/SportsClipper are never touched, and the new app opens by itself."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import zipfile

from . import config

APP = "SportsClipper.app"
EXE = os.path.join("Contents", "MacOS", "SportsClipper")


def bundle_path() -> str | None:
    """The .app that is running now (only when this is the packaged Mac app), else None."""
    exe = os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else ""
    marker = ".app" + os.sep
    i = exe.find(marker)
    return exe[: i + 4] if i > 0 else None


def parse_drop(data: str) -> list:
    """The file paths in a drag-and-drop event string ({paths with spaces} are wrapped in braces by Tk)."""
    out, cur, depth = [], "", 0
    for ch in data or "":
        if ch == "{":
            depth += 1
            if depth == 1:
                continue
        elif ch == "}":
            depth -= 1
            if depth == 0:
                out.append(cur); cur = ""
                continue
        elif ch == " " and depth == 0:
            if cur:
                out.append(cur); cur = ""
            continue
        cur += ch
    if cur:
        out.append(cur)
    return [p for p in out if p]


def _extract(zip_path: str, dest: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["/usr/bin/ditto", "-x", "-k", zip_path, dest], check=True)       # keeps the app's links and permissions
    else:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(dest)


def find_app(root: str) -> str | None:
    """The SportsClipper.app folder inside an extracted update (it may be a few folders down)."""
    depth0 = root.rstrip(os.sep).count(os.sep)
    for base, dirs, _ in os.walk(root):
        if os.path.basename(base) == APP and os.path.isfile(os.path.join(base, EXE)):
            return base
        if os.path.basename(base) == APP or base.count(os.sep) - depth0 >= 4:
            dirs[:] = []                                         # do not look inside an app, or too deep
    return None


def prepare(dropped: str, work: str | None = None) -> str:
    """Turn what was dropped (the zip or the .app) into a ready new SportsClipper.app; returns its path. Raises ValueError in plain words."""
    work = work or os.path.join(config.HOME, "update")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    if os.path.isdir(dropped) and os.path.basename(dropped.rstrip(os.sep)) == APP:
        found = dropped if os.path.isfile(os.path.join(dropped, EXE)) else None
        if found:
            dest = os.path.join(work, APP)
            subprocess.run(["/bin/cp", "-R", found, dest], check=True) if sys.platform == "darwin" else shutil.copytree(found, dest)
            found = dest
    elif dropped.lower().endswith(".zip") and os.path.isfile(dropped):
        stage = os.path.join(work, "new")
        os.makedirs(stage, exist_ok=True)
        try:
            _extract(dropped, stage)
        except Exception as e:                                  # noqa: BLE001
            raise ValueError(f"could not open that zip: {str(e)[:120]}")
        found = find_app(stage)
    else:
        raise ValueError("drop the SportsClipper-Mac.zip you downloaded (or the new SportsClipper.app)")
    if not found:
        raise ValueError("that is not a Sports Clipper update (no SportsClipper.app inside)")
    if sys.platform == "darwin":                                 # the downloaded file is 'quarantined': clear it so the new app opens like the old one
        subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", found], check=False)
    return found


def check_target(bundle: str | None) -> str:
    """'' when this app can be replaced; otherwise the reason, in plain words."""
    if not bundle:
        return "updating by drag and drop works in the installed Mac app (not when running from the source files)"
    if "AppTranslocation" in bundle:
        return "macOS is running the app from a protected copy: drag SportsClipper.app into the Applications folder, open it from there, then drop the update again"
    if not os.access(os.path.dirname(bundle), os.W_OK):
        return f"the app's folder is not writable: {os.path.dirname(bundle)}. Move SportsClipper.app into your Applications folder and try again"
    return ""


def helper_script(pid: int, old: str, new: str, backup: str) -> str:
    """The small script that waits for this app to quit, swaps the app, and opens the new one. The old app is kept at `backup`."""
    q = lambda p: "'" + p.replace("'", "'\\''") + "'"
    return f"""#!/bin/bash
while kill -0 {pid} 2>/dev/null; do sleep 1; done
rm -rf {q(backup)}
if mv {q(old)} {q(backup)} && mv {q(new)} {q(old)}; then
  /usr/bin/open {q(old)}
else
  [ -d {q(backup)} ] && [ ! -d {q(old)} ] && mv {q(backup)} {q(old)}
  /usr/bin/open {q(old)}
fi
"""


def start(new_app: str, bundle: str) -> str:
    """Write and launch the swap script; the caller then quits the app. Returns where the old app is kept."""
    work = os.path.join(config.HOME, "update")
    backup = os.path.join(work, "previous", APP)
    os.makedirs(os.path.dirname(backup), exist_ok=True)
    script = os.path.join(work, "swap.sh")
    with open(script, "w") as f:
        f.write(helper_script(os.getpid(), bundle, new_app, backup))
    os.chmod(script, 0o755)
    subprocess.Popen(["/bin/bash", script], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return backup
