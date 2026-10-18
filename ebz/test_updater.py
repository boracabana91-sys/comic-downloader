"""Updater tests with stand-in apps (small scripts that answer --version-file like the real one).
The real end-to-end update is also tested by the build on Mac and Windows."""
import os
import stat
import subprocess
import sys
import tempfile
import traceback
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebz_app  # noqa: E402
import updater  # noqa: E402
import version  # noqa: E402


def fake_exe(path, name="EBZ CNVRBINE", ver="09"):
    """A program that writes its name and version like the real app does."""
    with open(path, "w") as f:
        f.write("#!/bin/sh\n"
                f'if [ "$1" = "--version-file" ]; then printf "{name}\\n{ver}\\n" > "$2"; fi\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def fake_app(folder, ver="09", name="EBZ CNVRBINE"):
    app = os.path.join(folder, "EBZ CNVRBINE.app")
    os.makedirs(os.path.join(app, "Contents", "MacOS"))
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        import plistlib
        plistlib.dump({"CFBundleExecutable": "EBZ CNVRBINE"}, f)
    fake_exe(os.path.join(app, "Contents", "MacOS", "EBZ CNVRBINE"), name, ver)
    return app


def test_where_am_i():
    k, p = updater.current_install("/Applications/EBZ CNVRBINE.app/Contents/MacOS/EBZ CNVRBINE", True)
    assert (k, p) == ("mac", "/Applications/EBZ CNVRBINE.app")
    k, p = updater.current_install(r"C:\Users\me\Desktop\EBZ-CNVRBINE-02-Windows.exe", True)
    assert k == "win"
    for exe, frozen, word in (("/usr/bin/python3", False, "installed app"),
                              ("/private/var/folders/x/AppTranslocation/y/EBZ CNVRBINE.app/Contents/MacOS/E",
                               True, "Applications")):
        try:
            updater.current_install(exe, frozen)
        except updater.UpdateError as e:
            assert word in str(e), e
        else:
            raise AssertionError(exe)


def test_mac_update_from_zip():
    with tempfile.TemporaryDirectory() as d:
        apps = os.path.join(d, "Applications")
        os.makedirs(apps)
        old = fake_app(apps, "02")
        open(os.path.join(old, "old-marker"), "w").close()
        # the download: a zip with the new app inside
        build = os.path.join(d, "build")
        os.makedirs(build)
        new_app = fake_app(build, "09")
        zp = os.path.join(d, "Downloads", "EBZ-CNVRBINE-09-Mac.zip")
        os.makedirs(os.path.dirname(zp))
        subprocess.run(["sh", "-c", f'cd "{build}" && zip -qry "{zp}" "EBZ CNVRBINE.app"'], check=True)
        os.environ["EBZ_TRASH"] = os.path.join(d, "Trash")
        exe = os.path.join(old, "Contents", "MacOS", "EBZ CNVRBINE")
        new, info = updater.apply(zp, launch_after=False, executable=exe, frozen=True)
        assert new == old and info["version"] == "09" and info["newer"], info
        assert not os.path.exists(os.path.join(new, "old-marker")), "the new app took the old one's place"
        trashed = os.listdir(os.path.join(d, "Trash"))
        assert trashed and os.path.exists(os.path.join(d, "Trash", trashed[0], "old-marker")), trashed
        assert os.path.isfile(zp), "your download is not touched"
        assert updater.probe(new, "mac") == ("EBZ CNVRBINE", "09")


def test_windows_update():
    if os.name == "nt":
        print("   (skipped on Windows: the stand-in apps are scripts; the build tests the real program)")
        return
    with tempfile.TemporaryDirectory() as d:
        desk = os.path.join(d, "Desktop")
        os.makedirs(desk)
        cur = fake_exe(os.path.join(desk, "EBZ-CNVRBINE-02-Windows.exe"), ver="02")
        dl = fake_exe(os.path.join(d, "EBZ-CNVRBINE-09-Windows.exe"), ver="09")
        new, info = updater.apply(dl, launch_after=False, executable=cur, frozen=True)
        assert os.path.basename(new) == "EBZ-CNVRBINE-09-Windows.exe" and os.path.dirname(new) == desk
        names = sorted(os.listdir(desk))
        assert names == ["EBZ-CNVRBINE-02-Windows.exe.old", "EBZ-CNVRBINE-09-Windows.exe"], names
        updater.cleanup_old(new)   # what the new program does when it starts
        assert os.listdir(desk) == ["EBZ-CNVRBINE-09-Windows.exe"]
        # the same version again (same file name) also works
        new2, info2 = updater.apply(dl, launch_after=False, executable=new, frozen=True)
        assert new2 == new and os.listdir(desk) == ["EBZ-CNVRBINE-09-Windows.exe", "EBZ-CNVRBINE-09-Windows.exe.old"] or sorted(os.listdir(desk)) == ["EBZ-CNVRBINE-09-Windows.exe", "EBZ-CNVRBINE-09-Windows.exe.old"], os.listdir(desk)


def test_wrong_files_refused():
    if os.name == "nt":
        print("   (skipped on Windows: the stand-in apps are scripts; the build tests the real program)")
        return
    with tempfile.TemporaryDirectory() as d:
        cur = fake_exe(os.path.join(d, "EBZ-CNVRBINE-02-Windows.exe"), ver="02")
        other = fake_exe(os.path.join(d, "Other-Program.exe"), name="Something Else", ver="5")
        broken = os.path.join(d, "EBZ-CNVRBINE-09-Windows.exe")
        open(broken, "w").write("not a program")
        for f, word in ((other, "not EBZ"), (broken, "")):
            try:
                updater.apply(f, launch_after=False, executable=cur, frozen=True)
            except updater.UpdateError as e:
                assert word in str(e), e
            else:
                raise AssertionError(f)
        assert os.listdir(d) and os.path.isfile(cur), "nothing was replaced"
        open(os.path.join(d, "x.pdf"), "w").close()
        try:
            updater.prepare(os.path.join(d, "x.pdf"), d, cur, True)
        except updater.UpdateError as e:
            assert ".exe" in str(e)
        else:
            raise AssertionError("pdf accepted")


def test_version_answer_and_drop_routing():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "v.txt")
        subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "ebz_app.py"),
                        "--version-file", out], check=True, timeout=120)
        assert open(out).read().split("\n")[:2] == [version.APP_NAME, version.VERSION]
    assert ebz_app.looks_like_update("/Users/x/Downloads/EBZ-CNVRBINE-03-Mac.zip")
    assert ebz_app.looks_like_update(r"C:\dl\EBZ-CNVRBINE-03-Windows.exe")
    assert ebz_app.looks_like_update("/Applications/EBZ CNVRBINE.app/")
    assert not ebz_app.looks_like_update("/x/Chapter 1.zip")
    assert version.full_name() == "EBZ CNVRBINE " + version.VERSION


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok ", name)
            except Exception:
                failed += 1
                print(f"::error title={name}::" + traceback.format_exc().strip().replace("\n", "%0A"))
                print("FAILED", name)
    if failed:
        sys.exit(1)
    print("updater tests OK")
