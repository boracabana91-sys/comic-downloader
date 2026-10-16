"""vv13: the thumbnail steps around rendering, shared by the 24/7 pipeline and the window's test button."""
from __future__ import annotations

from . import cover, progress, thumbnail


def style_of(cfg: dict) -> str:
    s = cfg.get("thumb_font") or thumbnail.DEFAULT_STYLE
    return s if s in thumbnail.FONT_STYLES else thumbnail.DEFAULT_STYLE


def intro_picture(cfg: dict, title: str, kept_s: float, base: str, log=print):
    """When "show the thumbnail for 1 second at the start" is ticked: make the thumbnail before rendering, so the
    renderer can put it first. Returns the picture, or None (not ticked, or no two-star picture for this title)."""
    if not (cfg.get("thumb_intro") and cfg.get("thumbnail", {}).get("enabled", True)):
        return None
    try:
        pic = thumbnail.make_versus_only(title, kept_s, base + "_thumb.jpg", log, cfg.get("player_choice"), style_of(cfg))
    except Exception as e:
        log(f"thumbnail intro skipped: {e}")
        return None
    if pic is None:
        log("thumbnail intro skipped: it needs the two-player thumbnail, and this title does not have pictures for both teams")
    return pic


def make_thumb(cfg: dict, video: str, title: str, kept_s: float, base: str, log=print, ready: str | None = None):
    """The thumbnail file (made now from the rendered video unless the intro step already made it), or None."""
    if not cfg.get("thumbnail", {}).get("enabled", True):
        return None
    if ready:
        return ready
    try:
        progress.set("making the thumbnail", None)
        return thumbnail.make_thumbnail(video, title, kept_s, base + "_thumb.jpg", log,
                                        picks=cfg.get("player_choice"), style=style_of(cfg))
    except Exception as e:
        log(f"thumbnail skipped: {e}")
        return None


def add_cover(cfg: dict, outs: dict, thumb: str | None, log=print, only=None) -> None:
    """Optional: the thumbnail as the video file's own cover picture (YouTube does not use it)."""
    if not (thumb and cfg.get("thumb_cover_art")):
        return
    for h, p in outs.items():
        if only is None or h in only:
            if cover.add_cover_art(p, thumb, log):
                log(f"{h}p: thumbnail saved inside the video file as its cover picture")
