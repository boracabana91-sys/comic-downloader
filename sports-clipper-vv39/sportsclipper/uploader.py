"""YouTube upload (official Data API v3, OAuth) and optional Cloudinary backup."""
from __future__ import annotations
import os


SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


def key_file(cfg: dict) -> str:
    """vv25: the Google key file: the one chosen once, else one saved in the app's folder, else one built into the app."""
    from . import config
    for p in (cfg["upload"].get("client_secret", ""), os.path.join(config.HOME, "client_secret.json"),
              os.path.join(os.path.dirname(__file__), "client_secret.json")):
        if p and os.path.isfile(p):
            return p
    return ""


def _creds(cfg: dict):
    """The saved login, refreshed when it is old; None if there is none (or Google no longer accepts it)."""
    tok = cfg["upload"]["token"]
    if not os.path.exists(tok):
        return None
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(tok)       # the scopes it was saved with
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(tok, "w") as f:
                    f.write(creds.to_json())
            else:
                return None
        return creds
    except Exception:                                            # noqa: BLE001 - expired or revoked: sign in again
        return None


def is_connected(cfg: dict) -> bool:
    return _creds(cfg) is not None


def channel_name(cfg: dict) -> str:
    """The signed-in channel's name, '' when it cannot be read (older logins have no read permission)."""
    from googleapiclient.discovery import build
    creds = _creds(cfg)
    if not creds:
        return ""
    try:
        r = build("youtube", "v3", credentials=creds, cache_discovery=False).channels().list(part="snippet", mine=True).execute()
        return (r.get("items") or [{}])[0].get("snippet", {}).get("title", "")
    except Exception:                                            # noqa: BLE001
        return ""


def connect(cfg: dict, log=print) -> str:
    """vv25: sign in once in the browser window. The login is saved and used for every upload after that."""
    kf = key_file(cfg)
    if not kf:
        raise RuntimeError("The Google key file (client_secret.json) is not set up yet.")
    from google_auth_oauthlib.flow import InstalledAppFlow
    log("a browser window opens: sign in with the channel's Google account and press Allow ...")
    creds = InstalledAppFlow.from_client_secrets_file(kf, SCOPES).run_local_server(port=0, prompt="consent")
    os.makedirs(os.path.dirname(cfg["upload"]["token"]), exist_ok=True)
    with open(cfg["upload"]["token"], "w") as f:
        f.write(creds.to_json())
    return channel_name(cfg)


def disconnect(cfg: dict) -> None:
    try:
        os.remove(cfg["upload"]["token"])
    except OSError:
        pass


def youtube_service(cfg: dict):
    from googleapiclient.discovery import build
    creds = _creds(cfg)
    if creds is None:
        connect(cfg)                                             # first upload without Connect: sign in now
        creds = _creds(cfg)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


NET_WAITS = (30, 120, 300)                      # vv35: seconds to wait before each retry when the connection drops


class NetworkDown(RuntimeError):
    """The connection to YouTube kept failing. str(e) says so in plain words."""


def is_network_error(e) -> bool:
    """True for a dropped / missing internet connection or a YouTube server hiccup (worth waiting and retrying)."""
    import socket
    if isinstance(e, (ConnectionError, TimeoutError, socket.timeout, socket.gaierror)):
        return True
    if type(e).__name__ in ("ServerNotFoundError", "ConnectTimeout", "ReadTimeout", "TransportError"):
        return True
    st = getattr(getattr(e, "resp", None), "status", None)
    if isinstance(st, int) and st in (500, 502, 503, 504):
        return True
    t = str(e).lower()
    return any(k in t for k in ("unable to find the server", "name or service not known", "nodename nor servname",
                                "network is unreachable", "timed out", "connection reset", "connection aborted",
                                "broken pipe", "temporary failure in name resolution", "no route to host",
                                "internet connection appears to be offline", "failed to establish"))


def net_retry(fn, log=print, waits=NET_WAITS, sleep=None, what="the upload"):
    """Call fn(); when the internet drops, wait and try again (the upload carries on where it stopped)."""
    import time
    sleep = sleep or time.sleep
    for i in range(len(waits) + 1):
        try:
            return fn()
        except Exception as e:                                   # noqa: BLE001
            if not is_network_error(e):
                raise
            if i >= len(waits):
                raise NetworkDown("No internet connection to YouTube, so the video was not uploaded. "
                                  "Your finished video is saved: press 'Upload saved videos' when you are back online. "
                                  f"({str(e)[:100]})") from e
            log(f"(no connection to YouTube for {what}: {str(e)[:80]} - trying again in {waits[i]} s, attempt {i + 2} of {len(waits) + 1})")
            sleep(waits[i])


class UploadLimit(RuntimeError):
    """vv38: YouTube's daily upload limit for the channel is used up. Not an error in the app: the video waits and goes up later."""


def is_upload_limit(e) -> bool:
    t = str(e)
    return "uploadLimitExceeded" in t or "exceeded the number of videos" in t


RETRY_AFTER_H = 12


def upload_youtube(cfg: dict, path: str, meta: dict, publish_at_iso: str | None, log=print, waits=NET_WAITS, sleep=None) -> str:
    try:
        return _upload_youtube(cfg, path, meta, publish_at_iso, log, waits, sleep)
    except Exception as e:                                        # noqa: BLE001
        if is_upload_limit(e):
            raise UploadLimit("YouTube's daily upload limit for this channel is used up (it counts every video uploaded in the last "
                              "24 hours, deleted ones too). Your finished video is saved and will upload by itself later; verifying "
                              "the channel's phone number at youtube.com/verify raises the limit.") from e
        raise


def _upload_youtube(cfg: dict, path: str, meta: dict, publish_at_iso: str | None, log=print, waits=NET_WAITS, sleep=None) -> str:
    from googleapiclient.http import MediaFileUpload
    yt = net_retry(lambda: youtube_service(cfg), log, waits, sleep, "signing in")
    up = cfg["upload"]
    status = {"privacyStatus": up["privacy"], "selfDeclaredMadeForKids": False}
    if publish_at_iso:
        status.update({"privacyStatus": "private", "publishAt": publish_at_iso})
    body = {"snippet": {"title": meta["title"], "description": meta["description"],
                        "tags": meta["tags"], "categoryId": up["category_id"]},
            "status": status}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        st, resp = net_retry(req.next_chunk, log, waits, sleep)
        if st:
            log(f"upload {int(st.progress() * 100)}%")
    return resp["id"]


def video_exists(cfg: dict, youtube_id: str, service=None):
    """vv36: True / False when YouTube says the video is / is not on the channel (deleted); None when it cannot be checked."""
    if not youtube_id or len(youtube_id) < 6:
        return None
    try:
        yt = service or youtube_service(cfg)
        r = yt.videos().list(part="id", id=youtube_id).execute()
        return bool(r.get("items"))
    except Exception:                                          # noqa: BLE001
        return None


def backup_cloudinary(cfg: dict, path: str, log=print) -> str:
    import cloudinary
    import cloudinary.uploader
    c = cfg["cloudinary"]
    cloudinary.config(cloud_name=c["cloud_name"], api_key=c["api_key"], api_secret=c["api_secret"], secure=True)
    r = cloudinary.uploader.upload_large(path, resource_type="video", folder="sportsclipper")
    return r["secure_url"]


class ThumbnailError(RuntimeError):
    """The thumbnail could not be set on YouTube. str(e) is a plain-words reason for the window."""


def classify_thumbnail_error(status: int, text: str) -> tuple:
    """(worth_retrying, plain-words message) for a YouTube thumbnails.set failure."""
    t = (text or "").lower()
    if status == 403 and ("custom video thumbnails" in t or "forbidden" in t and "thumbnail" in t):
        return False, ("YouTube only lets verified channels set custom thumbnails. Verify the channel once at "
                       "youtube.com/verify (phone number), then reclip or upload the saved thumbnail by hand in YouTube Studio.")
    if status in (401, 403) and ("scope" in t or "insufficient" in t or "unauthorized" in t):
        return False, "Google did not give this app permission for thumbnails. Delete youtube_token.json in the SportsClipper folder and sign in again."
    if status == 403 and ("quota" in t or "ratelimit" in t):
        return False, "The YouTube daily quota is used up. The thumbnail can be set tomorrow, or by hand in YouTube Studio."
    if status == 400 and ("invalid" in t or "image" in t or "mediabody" in t):
        return False, "YouTube did not accept the picture (it must be a JPG/PNG under 2 MB)."
    if status in (404, 409, 429) or status >= 500 or status == 400:
        return True, f"YouTube was not ready yet (error {status})"
    return False, f"YouTube refused the thumbnail (error {status}): {(text or '')[:160].strip()}"


def set_thumbnail(cfg: dict, video_id: str, path: str, log=print, waits=(8, 20, 45), sleep=None, service=None) -> str:
    """Set the separate YouTube thumbnail (YouTube does not read one from inside the video file).
    Checks YouTube's reply, retries when the video is still being processed, and raises ThumbnailError with a
    clear reason when it cannot be done. Returns the thumbnail address YouTube reports."""
    import time
    sleep = sleep or time.sleep
    if not os.path.exists(path):
        raise ThumbnailError(f"the thumbnail file is missing: {path}")
    if os.path.getsize(path) > 2 * 1024 * 1024:
        raise ThumbnailError("the thumbnail is over YouTube's 2 MB limit")
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    yt = service or youtube_service(cfg)
    last = "no answer from YouTube"
    for attempt in range(len(waits) + 1):
        try:
            resp = yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(path, mimetype="image/jpeg")).execute()
            items = (resp or {}).get("items") or []
            if items:
                t = items[0]
                for k in ("maxres", "standard", "high", "medium", "default"):
                    if k in t and t[k].get("url"):
                        return t[k]["url"]
                return "ok"
            last = "YouTube answered but did not confirm the thumbnail"
            retry = True
        except HttpError as e:
            status = int(getattr(getattr(e, "resp", None), "status", 0) or 0)
            body = (getattr(e, "content", b"") or b"")
            body = body.decode("utf-8", "ignore") if isinstance(body, bytes) else str(body)
            retry, last = classify_thumbnail_error(status, body)
        except OSError as e:                                    # network dropped
            retry, last = True, f"network problem ({e})"
        if not retry or attempt >= len(waits):
            break
        log(f"thumbnail not set yet ({last}) - trying again in {waits[attempt]} s ...")
        sleep(waits[attempt])
    raise ThumbnailError(last)
