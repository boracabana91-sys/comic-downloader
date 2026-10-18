"""Tiny SQLite log so a video is never processed twice."""
from __future__ import annotations
import os
import sqlite3
import time


class Store:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("""CREATE TABLE IF NOT EXISTS videos(
            source TEXT, video_id TEXT, title TEXT, status TEXT, detail TEXT, updated REAL,
            PRIMARY KEY(source, video_id))""")
        self.db.commit()

    def seen(self, source: str, vid: str) -> bool:
        r = self.db.execute("SELECT status FROM videos WHERE source=? AND video_id=?", (source, vid)).fetchone()
        return bool(r and r[0] in ("done", "skipped", "baseline", "upload_failed"))

    def set(self, source: str, vid: str, title: str, status: str, detail: str = "") -> None:
        if status == "error" and self.status(source, vid) == "upload_failed":
            return                                          # vv35: a saved, waiting upload stays waiting
        self.db.execute("INSERT OR REPLACE INTO videos VALUES(?,?,?,?,?,?)",
                        (source, vid, title, status, detail, time.time()))
        self.db.commit()

    def status(self, source: str, vid: str) -> str:
        r = self.db.execute("SELECT status FROM videos WHERE source=? AND video_id=?", (source, vid)).fetchone()
        return r[0] if r else ""

    def rename_source(self, old: str, new: str) -> int:
        """vv32: a channel was renamed: its done / held / baseline records follow it. Returns the rows moved."""
        if not new or old == new:
            return 0
        cur = self.db.execute("UPDATE OR REPLACE videos SET source=? WHERE source=?", (new, old))
        self.db.commit()
        return cur.rowcount

    def detail(self, source: str, vid: str) -> str:
        r = self.db.execute("SELECT detail FROM videos WHERE source=? AND video_id=?", (source, vid)).fetchone()
        return r[0] if r else ""

    def forget(self, source: str, vid: str) -> None:
        """vv36: drop a video's record (e.g. it was deleted from YouTube) so it counts as new again."""
        self.db.execute("DELETE FROM videos WHERE source=? AND video_id=?", (source, vid))
        self.db.commit()

    def pending_uploads(self):
        """vv35: finished videos whose upload failed: (source, video_id, title, detail_json), oldest first."""
        return self.db.execute("SELECT source,video_id,title,detail FROM videos WHERE status='upload_failed' ORDER BY updated").fetchall()

    def held(self):
        """vv28: videos held because the title has a hold word: (source, video_id, title, detail, updated), newest first."""
        return self.db.execute("SELECT source,video_id,title,detail,updated FROM videos WHERE status='hold' ORDER BY updated DESC").fetchall()

    def release(self, source: str, vid: str) -> None:
        self.db.execute("DELETE FROM videos WHERE source=? AND video_id=? AND status='hold'", (source, vid))
        self.db.commit()

    def is_held(self, source: str, vid: str) -> bool:
        r = self.db.execute("SELECT status FROM videos WHERE source=? AND video_id=?", (source, vid)).fetchone()
        return bool(r and r[0] == "hold")

    def rows(self, limit: int = 50):
        return self.db.execute(
            "SELECT source,video_id,title,status,detail,updated FROM videos ORDER BY updated DESC LIMIT ?",
            (limit,)).fetchall()
