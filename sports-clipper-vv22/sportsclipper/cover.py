"""vv13: put the thumbnail inside the finished video file as its cover picture (the picture Finder / QuickTime show).
YouTube does NOT read this - it needs the separate thumbnail upload (uploader.set_thumbnail) - so this is optional."""
from __future__ import annotations
import os

from . import media


def add_cover_art(video: str, thumb: str, log=print) -> bool:
    """Copy the streams as they are (no re-encode, takes a moment) and attach the picture. Returns True on success."""
    if not (video and thumb and os.path.exists(video) and os.path.exists(thumb)):
        return False
    tmp = video + ".cover.mp4"
    try:
        media.run([media.need("ffmpeg"), "-v", "error", "-y", "-i", video, "-i", thumb, "-map", "0", "-map", "1",
                   "-c", "copy", "-disposition:v:1", "attached_pic", "-movflags", "+faststart", "-f", "mp4", tmp])
        os.replace(tmp, video)
        return True
    except Exception as e:
        log(f"cover picture could not be added to {os.path.basename(video)}: {e}")
        return False
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
