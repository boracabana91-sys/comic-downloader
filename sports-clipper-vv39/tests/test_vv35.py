"""vv35: a dropped connection is waited out and retried; a failed upload is saved and can be uploaded later without reclipping."""
import json
import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sportsclipper import uploader, store  # noqa: E402
import test_vv29 as t29  # noqa: E402

DNS = "Unable to find the server at youtube.googleapis.com"


class ServerNotFoundError(Exception):
    pass


class Retry(unittest.TestCase):
    def test_what_counts_as_a_network_error(self):
        for e in (ServerNotFoundError(DNS), socket.gaierror(8, "nodename nor servname provided"), TimeoutError("x"),
                  ConnectionResetError("reset"), RuntimeError("Network is unreachable")):
            self.assertTrue(uploader.is_network_error(e), repr(e))
        for e in (ValueError("bad title"), RuntimeError("quotaExceeded")):
            self.assertFalse(uploader.is_network_error(e), repr(e))

    def test_waits_then_succeeds(self):
        calls, waited = [], []
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise ServerNotFoundError(DNS)
            return "ok"
        self.assertEqual(uploader.net_retry(fn, lambda m: None, (30, 120, 300), waited.append), "ok")
        self.assertEqual(waited, [30, 120])

    def test_gives_up_with_a_plain_message(self):
        waited = []
        with self.assertRaises(uploader.NetworkDown) as cm:
            uploader.net_retry(lambda: (_ for _ in ()).throw(ServerNotFoundError(DNS)), lambda m: None, (1, 2), waited.append)
        self.assertEqual(waited, [1, 2])
        self.assertIn("Upload saved videos", str(cm.exception))

    def test_other_errors_are_not_retried(self):
        calls = []
        def fn():
            calls.append(1); raise ValueError("bad")
        with self.assertRaises(ValueError):
            uploader.net_retry(fn, lambda m: None, (1,), lambda s: None)
        self.assertEqual(len(calls), 1)


class Saved(unittest.TestCase):
    def test_a_failed_upload_waits_and_is_not_overwritten_by_error(self):
        db = store.Store(os.path.join(tempfile.mkdtemp(), "s.sqlite"))
        db.set("A", "v1", "t", "upload_failed", json.dumps({"file": "/x.mp4"}))
        db.set("A", "v1", "t", "error", "boom")
        self.assertEqual(db.status("A", "v1"), "upload_failed")
        self.assertTrue(db.seen("A", "v1"))                      # 24/7 does not reclip it
        self.assertEqual([r[1] for r in db.pending_uploads()], ["v1"])

    def test_upload_saved_uploads_without_reclipping(self):
        pl = t29.make_pl()
        f = os.path.join(tempfile.mkdtemp(), "v.mp4"); open(f, "wb").write(b"x")
        pl.db.set("A", "v1", "Game", "upload_failed", json.dumps({"file": f, "meta": {"title": "T", "description": "D", "tags": []},
                                                                  "publish_at": None, "thumb": None}))
        with mock.patch.object(uploader, "upload_youtube", return_value="yt123") as up:
            ok, left = pl.upload_saved()
        self.assertEqual((ok, left), (1, 0))
        self.assertEqual(up.call_args[0][1], f)
        self.assertEqual(pl.db.status("A", "v1"), "done")

    def test_still_offline_keeps_it_waiting(self):
        pl = t29.make_pl()
        f = os.path.join(tempfile.mkdtemp(), "v.mp4"); open(f, "wb").write(b"x")
        pl.db.set("A", "v1", "Game", "upload_failed", json.dumps({"file": f, "meta": {"title": "T", "description": "D", "tags": []}}))
        with mock.patch.object(uploader, "upload_youtube", side_effect=uploader.NetworkDown("offline")):
            ok, left = pl.upload_saved()
        self.assertEqual((ok, left), (0, 1))

    def test_waiting_upload_is_shown_in_the_scan_list(self):
        pl = t29.make_pl()
        pl.db.set("A", "id0", "x", "upload_failed", "{}")
        new, _h, old = pl.scan_view(t29.SRC, 5, vids=[t29.vid(0), t29.vid(1)])
        self.assertEqual([v.id for v in new], ["id1"])
        self.assertEqual([(v.id, v.state) for v in old], [("id0", "upload waiting")])


if __name__ == "__main__":
    unittest.main()
