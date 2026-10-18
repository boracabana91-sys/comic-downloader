"""Updating the program by dropping the new download onto it.

What you drop:
  Mac:     the downloaded EBZ-CNVRBINE-NN-Mac.zip (or the unzipped app)
  Windows: the downloaded EBZ-CNVRBINE-NN-Windows.exe

What happens:
  1. The new app is unpacked into a work folder (your download is not changed).
  2. It is asked for its name and version (it is started with --version-file and writes them
     to a small file), so a wrong or broken file is refused before anything is replaced.
  3. Mac: the old app is moved to the Trash (you can put it back), the new one takes its place.
     Windows: the old program file is renamed to "...exe.old" (a running program can be
     renamed but not deleted) and the new file is put next to it; the .old file is deleted
     the next time the program starts.
  4. The new version is opened and the old one closes.

Your settings live in a separate file in your home folder, so they are kept."""
import glob
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time

import version

FAMILY = ("EBZ CNVRBINE", "EBZ CNVRTR")   # names this program has had
RELEASES = "https://github.com/boracabana91-sys/comic-downloader/releases"


class UpdateError(Exception):
    """A plain-language reason the update could not be done."""


def number(v):
    try:
        return int(str(v).strip())
    except ValueError:
        return -1


# ---------------------------------------------------------------------------
# Where the running program is
# ---------------------------------------------------------------------------
def current_install(executable=None, frozen=None):
    """('mac', path of the .app) or ('win', path of the .exe). Raises UpdateError when the
    program is not an installed app (for example run from the source code)."""
    exe = executable or sys.executable
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen:
        raise UpdateError("updating works only in the installed app, not when run from the code.")
    if ".app/Contents/MacOS/" in exe:
        bundle = exe.split(".app/Contents/MacOS/")[0] + ".app"
        if "/AppTranslocation/" in bundle:
            raise UpdateError("macOS is running this app from a hidden copy. Move the app into your "
                              "Applications folder, open it from there, then drop the update again.")
        return "mac", bundle
    if exe.lower().endswith(".exe"):
        return "win", exe
    raise UpdateError("this kind of installation cannot be updated by dropping a file.")


def cleanup_old(executable=None):
    """Windows: delete the old program file left by the last update."""
    exe = executable or sys.executable
    if not exe.lower().endswith(".exe"):
        return
    for old in glob.glob(os.path.join(os.path.dirname(exe), "*.exe.old")):
        try:
            os.remove(old)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# The dropped file -> the new app, ready to check
# ---------------------------------------------------------------------------
def _find_app(folder):
    for root, dirs, _files in os.walk(folder):
        for d in dirs:
            if d.endswith(".app") and not d.startswith("."):
                return os.path.join(root, d)
        if root.count(os.sep) - folder.count(os.sep) >= 2:
            break
    return None


def unpack(dropped, kind, work):
    """Copy/unpack what was dropped into work. Returns the new .app or .exe path."""
    dropped = dropped.rstrip("/\\")
    if not os.path.exists(dropped):
        raise UpdateError("the dropped file could not be found.")
    low = dropped.lower()
    if kind == "mac":
        if low.endswith(".zip"):
            if shutil.which("ditto"):   # keeps the app's links and permissions exactly
                r = subprocess.run(["ditto", "-x", "-k", dropped, work], capture_output=True)
            else:
                r = subprocess.run(["unzip", "-q", "-o", dropped, "-d", work], capture_output=True)
            if r.returncode != 0:
                raise UpdateError("the zip file could not be opened (is the download complete?).")
            app = _find_app(work)
        elif low.endswith(".app") and os.path.isdir(dropped):
            app = os.path.join(work, os.path.basename(dropped))
            if shutil.which("ditto"):
                subprocess.run(["ditto", dropped, app], check=True)
            else:
                shutil.copytree(dropped, app, symlinks=True)
        else:
            raise UpdateError("on a Mac, drop the downloaded EBZ-CNVRBINE-...-Mac.zip (or the app).")
        if not app:
            raise UpdateError("there is no app inside that zip file.")
        if shutil.which("xattr"):   # the same as typing xattr -cr: lets the Mac open the new app
            subprocess.run(["xattr", "-cr", app], capture_output=True)
        return app
    if not low.endswith(".exe"):
        raise UpdateError("on Windows, drop the downloaded EBZ-CNVRBINE-...-Windows.exe file.")
    return dropped   # checked where it is; copied into place by install()


def _app_executable(app):
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
            name = plistlib.load(f).get("CFBundleExecutable")
    except Exception:
        name = None
    exe = os.path.join(app, "Contents", "MacOS", name or os.path.splitext(os.path.basename(app))[0])
    if not os.path.isfile(exe):
        raise UpdateError("the app inside the download is incomplete.")
    return exe


def probe(candidate, kind, timeout=180):
    """Start the new app just long enough to tell its name and version. Returns (name, version)."""
    exe = _app_executable(candidate) if kind == "mac" else candidate
    fd, out = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.run([exe, "--version-file", out], timeout=timeout, capture_output=True,
                           creationflags=flags)
        except subprocess.TimeoutExpired:
            raise UpdateError("the new version did not answer in time.")
        except OSError as e:
            raise UpdateError(f"the new version could not be started ({e}).")
        try:
            with open(out, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
    finally:
        try:
            os.remove(out)
        except OSError:
            pass
    if len(lines) < 2 or lines[0] not in FAMILY:
        raise UpdateError("that file is not EBZ CNVRBINE (or it is an older build that cannot be "
                          "checked).")
    return lines[0], lines[1]


# ---------------------------------------------------------------------------
# Putting the new app in place
# ---------------------------------------------------------------------------
def _unique(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    return f"{base} {time.strftime('%Y-%m-%d %H.%M.%S')}{ext}"


def _trash_dir():
    t = os.environ.get("EBZ_TRASH") or os.path.join(os.path.expanduser("~"), ".Trash")
    os.makedirs(t, exist_ok=True)
    return t


def install(kind, current, candidate):
    """Swap the old app for the new one. Returns the path of the new app/exe."""
    folder = os.path.dirname(current)
    if not os.access(folder, os.W_OK):
        raise UpdateError(f"the program's folder cannot be changed ({folder}). Move the program to "
                          "a folder you can change (for example Applications), then try again.")
    if kind == "mac":
        dest = os.path.join(folder, os.path.basename(candidate))
        trash = _trash_dir()
        moved = []
        try:
            for old in dict.fromkeys([current, dest]):   # the old app (and anything in the way)
                if os.path.exists(old):
                    to = _unique(os.path.join(trash, os.path.basename(old)))
                    shutil.move(old, to)
                    moved.append((to, old))
            shutil.move(candidate, dest)
        except Exception as e:
            for to, old in reversed(moved):   # put the old app back
                try:
                    if not os.path.exists(old):
                        shutil.move(to, old)
                except Exception:
                    pass
            raise UpdateError(f"the new app could not be put in place ({e}). Your old app is unchanged.")
        return dest
    # Windows
    dest = os.path.join(folder, os.path.basename(candidate))
    old = _unique(current + ".old")
    os.replace(current, old)   # allowed while the program runs
    try:
        if os.path.exists(dest) and os.path.abspath(dest) != os.path.abspath(current):
            os.replace(dest, _unique(dest + ".old"))
        shutil.copyfile(candidate, dest + ".part")
        os.replace(dest + ".part", dest)
    except Exception as e:
        try:
            os.replace(old, current)
        except Exception:
            pass
        raise UpdateError(f"the new program could not be put in place ({e}). Your old program is unchanged.")
    return dest


def launch(kind, path):
    if kind == "mac":
        subprocess.Popen(["open", "-n", path])
    else:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([path], close_fds=True, creationflags=flags, cwd=os.path.dirname(path))


def prepare(dropped, work, executable=None, frozen=None):
    """Steps 1-2: returns a dict with kind, current, candidate, name, version, newer (bool)."""
    kind, current = current_install(executable, frozen)
    candidate = unpack(dropped, kind, work)
    name, ver = probe(candidate, kind)
    return {"kind": kind, "current": current, "candidate": candidate, "name": name, "version": ver,
            "newer": number(ver) > number(version.VERSION)}


def apply(dropped, launch_after=True, executable=None, frozen=None):
    """The whole update without questions (used by the build's test). Returns the new path."""
    work = tempfile.mkdtemp(prefix="ebz_update_")
    info = prepare(dropped, work, executable, frozen)
    new = install(info["kind"], info["current"], info["candidate"])
    if launch_after:
        launch(info["kind"], new)
    return new, info
