"""YouTube upload (official Data API v3, OAuth) and optional Cloudinary backup."""
from __future__ import annotations
import os


def youtube_service(cfg: dict):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    up = cfg["upload"]
    creds = None
    if os.path.exists(up["token"]):
        creds = Credentials.from_authorized_user_file(up["token"], scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(up["client_secret"], scopes).run_local_server(port=0)
        os.makedirs(os.path.dirname(up["token"]), exist_ok=True)
        with open(up["token"], "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_youtube(cfg: dict, path: str, meta: dict, publish_at_iso: str | None, log=print) -> str:
    from googleapiclient.http import MediaFileUpload
    yt = youtube_service(cfg)
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
        st, resp = req.next_chunk()
        if st:
            log(f"upload {int(st.progress() * 100)}%")
    return resp["id"]


def backup_cloudinary(cfg: dict, path: str, log=print) -> str:
    import cloudinary
    import cloudinary.uploader
    c = cfg["cloudinary"]
    cloudinary.config(cloud_name=c["cloud_name"], api_key=c["api_key"], api_secret=c["api_secret"], secure=True)
    r = cloudinary.uploader.upload_large(path, resource_type="video", folder="sportsclipper")
    return r["secure_url"]


def set_thumbnail(cfg: dict, video_id: str, path: str) -> None:
    from googleapiclient.http import MediaFileUpload
    youtube_service(cfg).thumbnails().set(
        videoId=video_id, media_body=MediaFileUpload(path, mimetype="image/jpeg")).execute()
