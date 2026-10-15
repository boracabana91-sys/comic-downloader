"""Find new videos on licensed sources. Metadata listing only; downloads happen in fetch()."""
from __future__ import annotations
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

from .rights import Source

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".m4v", ".webm")
NS = {"a": "http://www.w3.org/2005/Atom", "y": "http://www.youtube.com/xml/schemas/2015"}


@dataclass
class Video:
    id: str
    title: str
    published: datetime          # UTC
    url: str = ""
    path: str = ""               # set for local files


def _channel_id(loc: str) -> str:
    m = re.search(r"(UC[\w-]{22})", loc)
    return m.group(1) if m else ""


def list_videos(src: Source, limit: int = 15) -> list:
    if src.kind == "folder":
        out = []
        if os.path.isdir(src.location):
            for n in sorted(os.listdir(src.location)):
                p = os.path.join(src.location, n)
                if n.lower().endswith(VIDEO_EXT) and os.path.isfile(p):
                    st = os.stat(p)
                    out.append(Video(f"{n}:{st.st_size}:{int(st.st_mtime)}", os.path.splitext(n)[0],
                                     datetime.fromtimestamp(st.st_mtime, timezone.utc), path=p))
        return out
    if src.kind == "youtube":
        cid = _channel_id(src.location)
        if cid:
            req = urllib.request.Request(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                                         headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(urllib.request.urlopen(req, timeout=30).read())
            out = []
            for e in root.findall("a:entry", NS)[:limit]:
                vid = e.findtext("y:videoId", namespaces=NS)
                pub = datetime.fromisoformat(e.findtext("a:published", namespaces=NS).replace("Z", "+00:00"))
                out.append(Video(vid, e.findtext("a:title", namespaces=NS) or vid, pub,
                                 url=f"https://www.youtube.com/watch?v={vid}"))
            return out
        # handle / playlist URL: ask yt-dlp for the list only
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "playlistend": limit}) as y:
            info = y.extract_info(src.location, download=False)
        out = []
        for e in info.get("entries", [])[:limit]:
            ts = e.get("timestamp")
            pub = datetime.fromtimestamp(ts, timezone.utc) if ts else datetime.now(timezone.utc)
            out.append(Video(e["id"], e.get("title") or e["id"], pub, url=f"https://www.youtube.com/watch?v={e['id']}"))
        return out
    if src.kind == "url":
        return [Video(src.location, os.path.basename(src.location) or "video",
                      datetime.now(timezone.utc), url=src.location)]
    return []


def fetch(v: Video, work_dir: str, max_height: int = 1080) -> str:
    """Bring the video into work_dir. Caller must already have passed rights.check()."""
    if v.path:
        return v.path
    os.makedirs(work_dir, exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "_", v.id)[:60]
    if "youtube.com" in v.url or "youtu.be" in v.url:
        import yt_dlp
        tpl = os.path.join(work_dir, safe + ".%(ext)s")
        opts = {"quiet": True, "outtmpl": tpl, "merge_output_format": "mp4",
                "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b"}
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(v.url, download=True)
            return y.prepare_filename(info).rsplit(".", 1)[0] + ".mp4"
    dest = os.path.join(work_dir, safe + ".mp4")
    urllib.request.urlretrieve(v.url, dest)
    return dest
