"""Find new videos on licensed sources. Metadata listing only; downloads happen in fetch()."""
from __future__ import annotations
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

from . import progress
from .rights import Source

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".m4v", ".webm")
NS = {"a": "http://www.w3.org/2005/Atom", "y": "http://www.youtube.com/xml/schemas/2015", "m": "http://search.yahoo.com/mrss/"}


@dataclass
class Video:
    id: str
    title: str
    published: datetime          # UTC
    url: str = ""
    path: str = ""               # set for local files
    group: str = ""              # "Videos", "Live", "Shorts" or "Playlist: name" (set by list_all)
    channel_id: str = ""         # the channel that owns the video, when the listing says
    src_name: str = ""           # the source (channel) this video was listed from
    dated: bool = True           # False when the listing did not give a posting date
    duration: float | None = None   # seconds, when the listing says (vv22: used to skip Shorts and clips)
    channel_name: str = ""       # vv23: the channel's display name, when the listing says
    views: int | None = None     # vv29: view count, when the listing says (colour coding)
    state: str = ""              # vv29: "new" / "held" / "done" (already clipped or uploaded) / "" (older post)


def _channel_id(loc: str) -> str:
    m = re.search(r"(UC[\w-]{22})", loc)
    return m.group(1) if m else ""


def _playlist_url(loc: str) -> str:
    return f"https://www.youtube.com/playlist?list={loc.split(':', 1)[1]}" if loc.startswith("playlist:") else loc


def parse_flat(info: dict, group: str = "") -> list:
    """Turn a yt-dlp flat listing (a channel tab or a playlist) into Video rows. Pure function, tested."""
    out = []
    for e in (info or {}).get("entries") or []:
        if not e or not e.get("id"):
            continue
        if str(e.get("ie_key", "")).lower() == "youtubetab" or (e.get("url") or "").find("/playlist?") >= 0:
            continue                                         # a playlist entry on the Playlists tab, not a video
        ts, ud = e.get("timestamp"), e.get("upload_date")
        pub, dated = datetime.now(timezone.utc), False
        if ts:
            pub, dated = datetime.fromtimestamp(ts, timezone.utc), True
        elif ud and re.fullmatch(r"\d{8}", str(ud)):
            pub, dated = datetime.strptime(str(ud), "%Y%m%d").replace(tzinfo=timezone.utc), True
        out.append(Video(e["id"], e.get("title") or e["id"], pub, url=f"https://www.youtube.com/watch?v={e['id']}",
                         group=group, dated=dated, channel_id=str(e.get("channel_id") or ""),
                         channel_name=str(e.get("channel") or e.get("uploader") or ""),
                         duration=float(e["duration"]) if isinstance(e.get("duration"), (int, float)) else None,
                         views=int(e["view_count"]) if isinstance(e.get("view_count"), (int, float)) else None))
    return out


_PL = r"((?:PL|OL|UU|FL)[\w-]{10,})"


def playlist_id(text: str) -> str:
    """The playlist id in a pasted playlist link (or a bare playlist id); '' if the text is not one."""
    s = (text or "").strip()
    m = re.search(r"[?&]list=([\w-]+)", s) or re.fullmatch(_PL, s)
    return m.group(1) if m else ""


_VIDEO_URL = re.compile(
    r"(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:shorts/|live/|embed/|v/)|[?&]v=)([\w-]{11})(?![\w-])", re.I)


def video_id(text: str) -> str:
    """vv17: the video id in a pasted link to ONE video (watch?v=, youtu.be/, /shorts/, /live/, /embed/); '' if it is not one.
    Only links count, so a title typed in the search bar is never mistaken for an id."""
    s = (text or "").strip()
    if not re.search(r"(?:youtu\.be|youtube(?:-nocookie)?\.com)", s, re.I):
        return ""
    m = _VIDEO_URL.search(s)
    return m.group(1) if m else ""


def fetch_video(text: str, log=print) -> list:
    """vv17: the one video behind a pasted link, as a one-row list (like a scan). Reads its details only; nothing is downloaded."""
    vid = video_id(text)
    if not vid:
        raise ValueError("That is not a YouTube video link.")
    info = _flat(f"https://www.youtube.com/watch?v={vid}", noplaylist=True, extract_flat=False) or {}
    if not info.get("id"):
        raise ValueError("Could not read that video (private, removed or not available?).")
    vids = parse_flat({"entries": [info]}, "Single video")
    log(f"video {vids[0].title}")
    return vids


def scan_playlist(text: str, log=print) -> list:
    """Every video in one playlist, from a pasted link. Lists only; nothing is downloaded."""
    pid = playlist_id(text)
    if not pid:
        raise ValueError("That is not a YouTube playlist link.")
    info = _flat(f"https://www.youtube.com/playlist?list={pid}") or {}
    title = info.get("title") or pid
    vids = parse_flat(info, f"Playlist: {title}")
    log(f"playlist {title}: {len(vids)} videos")
    return vids


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def owner_source(v: "Video", srcs: list):
    """vv23: the source (a dict from config) this video counts as owned by, or None.
    Yours when ANY of these hold: its channel id is one of your channels; the channel it was listed from is in your
    list; its channel name is one of your channels; it sits in a playlist you added. (vv22 refused whenever the id
    did not match, even for a video listed from your own channel.)"""
    yt = [d for d in srcs if d.get("enabled", True) is not False]
    if v.channel_id:
        for d in yt:
            if d.get("kind") == "youtube" and _channel_id(d.get("location", "")) == v.channel_id:
                return d
    if v.src_name:
        for d in yt:
            if d.get("name") == v.src_name:
                own = _channel_id(d.get("location", ""))
                # listed from one of your channels: yours, unless it is plainly another channel's video
                # (its id differs from the channel's own id) - that one asks to be added first
                if not (own and v.channel_id and own != v.channel_id and d.get("kind") == "youtube"
                        and not str(d.get("location", "")).startswith("playlist:")):
                    return d
    if v.channel_name:
        for d in yt:
            if d.get("kind") == "youtube" and _norm(d.get("name")) and _norm(d.get("name")) == _norm(v.channel_name):
                return d
    if v.group.startswith("Playlist: "):
        for d in yt:
            if str(d.get("location", "")).startswith("playlist:") and d.get("name") == v.group:
                return d
    return None


def why_not_owned(v: "Video") -> str:
    """The exact reason shown when a video is not covered by any channel in the list."""
    who = v.channel_name or v.channel_id or "an unknown channel"
    return f"'{who}' is not in your channels list."


def source_for_video(v: "Video", note: str) -> dict:
    """vv23: a channel entry built from a video, to add its channel in one click (the caller asks the owner first)."""
    if v.channel_id:
        loc = f"https://www.youtube.com/channel/{v.channel_id}"
    else:
        raise ValueError("This video does not say which channel it belongs to; paste the channel link instead.")
    return {"name": v.channel_name or v.channel_id, "kind": "youtube", "location": loc,
            "licensed": True, "license_note": note, "enabled": True}


def parse_playlists(info: dict) -> list:
    """(playlist id, title) for each playlist on a channel's Playlists tab."""
    out = []
    for e in (info or {}).get("entries") or []:
        pid = (e or {}).get("id") or ""
        if pid.startswith(("PL", "OL", "UU", "LL", "FL")):
            out.append((pid, e.get("title") or pid))
    return out


def _flat(url: str, **extra):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True,
            "ignoreerrors": True, "socket_timeout": 30}
    opts.update(extra)
    with yt_dlp.YoutubeDL(opts) as y:
        return y.extract_info(url, download=False)


def list_all(src: Source, log=print) -> list:
    """Every video on a channel, grouped the way the channel is: Videos, Live, Shorts and each of its
    playlists; or every video of a single playlist. Reads the lists only (no downloads)."""
    if src.kind != "youtube":
        return list_videos(src, 1000)
    loc = src.location
    if loc.startswith("playlist:"):
        name = src.name or "Playlist"
        vids = parse_flat(_flat(_playlist_url(loc)), f"Playlist: {name}")
        log(f"playlist {name}: {len(vids)} videos")
        for v in vids:
            v.src_name = src.name
        return vids
    cid = _channel_id(loc)
    base = f"https://www.youtube.com/channel/{cid}" if cid else loc.rstrip("/")
    out, seen = [], set()
    for tab, label in (("videos", "Videos"), ("streams", "Live"), ("shorts", "Shorts")):
        try:
            vids = parse_flat(_flat(f"{base}/{tab}"), label)
        except Exception as e:
            log(f"{label}: not available ({str(e)[:80]})")
            continue
        vids = [v for v in vids if v.id not in seen]
        seen.update(v.id for v in vids)
        log(f"{label}: {len(vids)} videos")
        out += vids
    try:
        pls = parse_playlists(_flat(f"{base}/playlists"))
    except Exception as e:
        pls = []
        log(f"Playlists: not available ({str(e)[:80]})")
    for pid, title in pls:
        try:
            vids = parse_flat(_flat(f"https://www.youtube.com/playlist?list={pid}"), f"Playlist: {title}")
        except Exception as e:
            log(f"Playlist {title}: not available ({str(e)[:80]})")
            continue
        log(f"Playlist {title}: {len(vids)} videos")
        out += vids                                           # may repeat videos from Videos: each folder is complete
    for v in out:
        v.src_name = src.name
    return out


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
                st = e.find("m:group/m:community/m:statistics", NS)
                try:
                    views = int(st.get("views")) if st is not None else None
                except (TypeError, ValueError):
                    views = None
                out.append(Video(vid, e.findtext("a:title", namespaces=NS) or vid, pub,
                                 url=f"https://www.youtube.com/watch?v={vid}", views=views))
            return out
        # handle / playlist URL: ask yt-dlp for the list only
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "playlistend": limit}) as y:
            info = y.extract_info(_playlist_url(src.location), download=False)
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


def list_recent(src: Source, limit: int = 50, log=print) -> list:
    """vv29: the channel's newest videos (Videos tab, no Shorts/Live), newest first, with dates and views where known.
    The channel's feed (15 newest, always dated, has views) is merged with the Videos tab (up to `limit`);
    posts the tab gives no date for are dated one by one (best effort)."""
    if src.kind != "youtube":
        return list_videos(src, limit)
    feed = []
    try:
        feed = list_videos(src, 15)
    except Exception as e:                                    # noqa: BLE001
        log(f"[{src.name}] feed not available ({str(e)[:80]})")
    byid = {v.id: v for v in feed}
    tab = []
    if not src.location.startswith("playlist:"):
        cid = _channel_id(src.location)
        base = f"https://www.youtube.com/channel/{cid}" if cid else src.location.rstrip("/")
        urls = []
        if cid.startswith("UC"):
            urls.append(f"https://www.youtube.com/playlist?list=UU{cid[2:]}")     # vv30: the channel's uploads list: every upload, newest first
        urls.append(f"{base}/videos")
        for u in urls:
            try:
                tab = parse_flat(_flat(u, playlistend=limit), "Videos")
            except Exception as e:                            # noqa: BLE001
                log(f"[{src.name}] list not available ({str(e)[:80]})")
                tab = []
            if tab:
                break
        log(f"[{src.name}] feed gave {len(feed)} videos, the channel list gave {len(tab)}")
    out = list(feed)
    for v in tab:
        if v.id in byid:
            if byid[v.id].views is None and v.views is not None:
                byid[v.id].views = v.views
            if v.duration:
                byid[v.id].duration = v.duration
            continue
        byid[v.id] = v
        out.append(v)
    undated = [v for v in out if not v.dated or v.title == v.id or not v.duration][:40]     # vv30: also fill missing titles / lengths
    if undated:
        try:
            from concurrent.futures import ThreadPoolExecutor
            def one(v):
                try:
                    import yt_dlp
                    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "process": False,
                                           "socket_timeout": 20}) as y:
                        i = y.extract_info(v.url, download=False) or {}
                    if i.get("title") and v.title == v.id:
                        v.title = str(i["title"])
                    if isinstance(i.get("duration"), (int, float)) and not v.duration:
                        v.duration = float(i["duration"])
                    ud = str(i.get("upload_date") or "")
                    if re.fullmatch(r"\d{8}", ud):
                        v.published, v.dated = datetime.strptime(ud, "%Y%m%d").replace(tzinfo=timezone.utc), True
                    if isinstance(i.get("view_count"), (int, float)):
                        v.views = int(i["view_count"])
                except Exception:                              # noqa: BLE001
                    pass
            with ThreadPoolExecutor(6) as ex:
                list(ex.map(one, undated))
        except Exception:                                      # noqa: BLE001
            pass
    out.sort(key=lambda v: (v.dated, v.published), reverse=True)
    for v in out:
        v.src_name = src.name
    return out[:limit]


def fetch(v: Video, work_dir: str, max_height: int = 1080) -> str:
    """Bring the video into work_dir. Caller must already have passed rights.check()."""
    if v.path:
        return v.path
    os.makedirs(work_dir, exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "_", v.id)[:60]
    if "youtube.com" in v.url or "youtu.be" in v.url:
        import yt_dlp
        tpl = os.path.join(work_dir, safe + ".%(ext)s")
        from . import media
        opts = {"quiet": True, "outtmpl": tpl, "merge_output_format": "mp4",
                "ffmpeg_location": media.need("ffmpeg"),          # the app's bundled ffmpeg, no install needed
                "format": (f"bv*[height<={max_height}][vcodec^=avc1]+ba[acodec^=mp4a]/"
                           f"b[height<={max_height}][vcodec^=avc1]/"
                           f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b")}
        def _hook(d):
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if d.get("status") == "downloading" and tot:
                progress.set("downloading the source", min(99, int(d.get("downloaded_bytes", 0) * 100 / tot)))
        opts["progress_hooks"] = [_hook]
        progress.set("downloading the source", 0)
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
    pid = playlist_id(s)
    if pid:                                                   # a playlist link: scan that playlist directly
        try:
            title = (_flat(f"https://www.youtube.com/playlist?list={pid}", playlistend=1) or {}).get("title") or pid
        except Exception:
            title = pid
        return {"name": f"Playlist: {title}", "kind": "youtube", "location": f"playlist:{pid}"}
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
