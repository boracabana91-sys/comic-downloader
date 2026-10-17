"""vv36: every clip ends at the final score; already-uploaded videos ask first; a video deleted from YouTube counts as new."""
import os
import queue
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sportsclipper import analyze, pipeline, store, uploader  # noqa: E402
import test_vv29 as t29  # noqa: E402


class Ending(unittest.TestCase):
    def test_a_clip_that_stops_early_gets_the_finish_added(self):
        final, added = analyze.ensure_ending([[26.0, 300.0], [500.0, 640.0]], 1000.0, True)
        self.assertEqual(final[-1], [988.0, 1000.0]); self.assertAlmostEqual(added, 12.0)

    def test_already_ending_at_the_finish_is_untouched(self):
        final, added = analyze.ensure_ending([[26.0, 300.0], [900.0, 999.5]], 1000.0, True)
        self.assertEqual(added, 0.0); self.assertEqual(final[-1][1], 1000.0)

    def test_close_to_the_end_extends_the_last_piece(self):
        final, added = analyze.ensure_ending([[26.0, 990.0]], 1000.0, True)
        self.assertEqual(final, [[26.0, 1000.0]]); self.assertAlmostEqual(added, 10.0)

    def test_end_unknown_adds_nothing(self):
        segs = [[26.0, 300.0]]
        self.assertEqual(analyze.ensure_ending(segs, 1000.0, False), (segs, 0.0))
        self.assertEqual(analyze.ensure_ending([], 1000.0, True), ([], 0.0))

    def test_plan_uses_it_in_both_modes(self):
        src = open(analyze.__file__).read()
        self.assertEqual(src.count("ensure_ending(final, end_s, end_known)"), 3)


class Deleted(unittest.TestCase):
    def test_video_exists(self):
        class Req:
            def __init__(self, items): self.items = items
            def execute(self): return {"items": self.items}
        class Vids:
            def __init__(self, items): self.items = items
            def list(self, **k): return Req(self.items)
        class YT:
            def __init__(self, items): self.items = items
            def videos(self): return Vids(self.items)
        self.assertTrue(uploader.video_exists({}, "abcdefghijk", service=YT([{"id": "x"}])))
        self.assertFalse(uploader.video_exists({}, "abcdefghijk", service=YT([])))
        self.assertIsNone(uploader.video_exists({}, "", service=YT([])))

    def test_unreachable_youtube_is_unknown_not_deleted(self):
        with mock.patch.object(uploader, "youtube_service", side_effect=RuntimeError("offline")):
            self.assertIsNone(uploader.video_exists({}, "abcdefghijk"))

    def test_store_detail_and_forget(self):
        db = store.Store(os.path.join(tempfile.mkdtemp(), "s.sqlite"))
        db.set("A", "v1", "t", "done", "yt123")
        self.assertEqual(db.detail("A", "v1"), "yt123")
        db.forget("A", "v1"); self.assertEqual(db.status("A", "v1"), "")


class Gate(unittest.TestCase):
    def run_gate(self, status, exists):
        db = store.Store(os.path.join(tempfile.mkdtemp(), "state.sqlite"))
        if status:
            db.set("A", "id0", "t", status, "yt123")
        with mock.patch.object(uploader, "video_exists", return_value=exists):
            fresh, dups = pipeline.split_already_done(db, {}, [(t29.SRC, t29.vid(0))], lambda m: None)
        return len(fresh), len(dups), db.status("A", "id0")

    def test_new_video_goes_straight_through(self):
        self.assertEqual(self.run_gate("", None), (1, 0, ""))

    def test_uploaded_video_asks(self):
        self.assertEqual(self.run_gate("done", True), (0, 1, "done"))

    def test_video_deleted_from_youtube_counts_as_new(self):
        self.assertEqual(self.run_gate("done", False), (1, 0, ""))

    def test_cannot_check_youtube_still_asks(self):
        self.assertEqual(self.run_gate("done", None), (0, 1, "done"))

    def test_saved_waiting_upload_asks_too(self):
        self.assertEqual(self.run_gate("upload_failed", None), (0, 1, "upload_failed"))


if __name__ == "__main__":
    unittest.main()
