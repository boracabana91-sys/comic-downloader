"""Entry point for the packaged Mac app."""
import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def selftest(out):
    ok = "OK"
    try:
        import subprocess
        import googleapiclient, google_auth_oauthlib, numpy, yt_dlp  # noqa: F401
        from sportsclipper import media
        subprocess.run([media.need("ffmpeg"), "-version"], capture_output=True, check=True)
        import sportsclipper.gui, sportsclipper.pipeline  # noqa: F401
    except Exception as e:
        ok = f"FAIL {e!r}"
    open(out, "w").write(ok)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    else:
        from sportsclipper.gui import main
        sys.exit(main())
