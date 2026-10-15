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


_UC = r"(UC[\w-]{22})"


def parse_channel_html(page: str):
    """Pull (channel_id, display_name) out of a YouTube channel page."""
    import html as _h
    cid = None
    for pat in (r'"channelId":"' + _UC + '"', r'itemprop="channelId" content="' + _UC + '"',
                r'"browseId":"' + _UC + '"'):
        m = re.search(pat, page)
        if m:
            cid = m.group(1)
            break
    nm = re.search(r'<meta property="og:title" content="([^"]+)"', page)
    return cid, (_h.unescape(nm.group(1)) if nm else "")


def resolve_youtube(text: str) -> dict:
    """Any YouTube channel link (or @name, or UC... id) -> {'name', 'location'} with the channel ID filled in."""
    s = (text or "").strip()
    if not s:
        raise ValueError("Paste the channel link first.")
    m = re.search(r"/channel/" + _UC, s) or re.fullmatch(_UC, s)
    name = ""
    if m:
        cid = m.group(1)
    else:
        if s.startswith("@"):
            s = "https://www.youtube.com/" + s
        if not s.startswith("http"):
            s = "https://" + s
        if "youtube.com" not in s and "youtu.be" not in s:
            raise ValueError("That is not a YouTube link.")
        req = urllib.request.Request(s, headers={"User-Agent": "Mozilla/5.0",
                                                 "Accept-Language": "en-US,en;q=0.9"})
        page = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        cid, name = parse_channel_html(page)
        if not cid:
            raise ValueError("Could not find a channel in that link. Paste the channel's main page link, "
                             "for example https://www.youtube.com/@ChannelName")
    if not name:  # the channel's RSS feed gives the name; if offline, the ID is used as the name for now
        try:
            feed = ET.fromstring(urllib.request.urlopen(
                f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", timeout=30).read())
            name = feed.findtext("a:author/a:name", namespaces=NS) or cid
        except Exception:
            name = cid
    return {"name": name, "kind": "youtube", "location": cid}
