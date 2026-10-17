"""vv20: scan only highlighted channels, newest 3, upload failure keeps files, Mac wake-up."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import config, pipeline, sources, wake  # noqa: E402


def vid(i):
    return sources.Video(f"id{i}", f"Nuggets vs Heat FULL GAME HIGHLIGHTS {i}", datetime(2026, 10, 17, 10 - i, tzinfo=timezone.utc))


def make(cfg_extra, logs):
    tmp = tempfile.mkdtemp()
    cfg = config.load(os.path.join(tmp, "none.json"))
    cfg["sources"] = [{"name": "A", "kind": "youtube", "location": "UCa", "licensed": True, "license_note": "mine", "enabled": True},
                      {"name": "B", "kind": "youtube", "location": "UCb", "licensed": True, "license_note": "mine", "enabled": True}]
    cfg.update(cfg_extra)
    with mock.patch.object(config, "HOME", tmp):
        pl = pipeline.Pipeline(cfg, logs.append)
    return pl


class Scan(unittest.TestCase):
    def test_only_highlighted_channels_are_scanned(self):
        logs = []
        pl = make({"scan_only": ["A"]}, logs)
        for i in range(5):
            pl.db.set("A", f"old{i}", "x", "baseline")
        pl.db.set("B", "z", "x", "baseline")
        seen = []
        with mock.patch.object(sources, "list_videos", side_effect=lambda s: seen.append(s.name) or []):
            pl.scan_once()
        self.assertEqual(seen, ["A"])

    def test_nothing_highlighted_scans_nothing(self):
        logs = []
        pl = make({"scan_only": []}, logs)
        with mock.patch.object(sources, "list_videos", side_effect=AssertionError("no")):
            self.assertEqual(pl.scan_once(), 0)
        self.assertTrue(any("nothing is highlighted" in m for m in logs))

    def test_takes_the_newest_five_only(self):
        logs = []
        pl = make({"scan_only": ["A", "B"]}, logs)
        pl.db.set("A", "base", "x", "baseline")
        pl.db.set("B", "base", "x", "baseline")
        done = []
        with mock.patch.object(sources, "list_videos", side_effect=lambda s: [vid(i) for i in range(6)]), \
             mock.patch.object(pl, "process", side_effect=lambda s, v, u=True, enforce=False: done.append((s.name, v.id)) or {}):
            n = pl.scan_once()
        self.assertEqual(n, 5)
        self.assertEqual(done, [("A", "id4"), ("A", "id3"), ("A", "id2"), ("A", "id1"), ("A", "id0")])    # newest five, oldest of them first

    def test_latest_new_skips_done_videos(self):
        pl = make({}, [])
        pl.db.set("A", "id0", "x", "done")
        src = pipeline.rights.Source.from_dict(pl.cfg["sources"][0])
        with mock.patch.object(sources, "list_videos", return_value=[vid(0), vid(1), vid(2), vid(3)]):
            got = pl.latest_new(src, 3)
        self.assertEqual([v.id for v in got], ["id1", "id2", "id3"])
        self.assertTrue(all(v.src_name == "A" for v in got))


class Wake(unittest.TestCase):
    def test_wake_two_minutes_before_first_scan(self):
        self.assertEqual(wake.wake_hhmm("09:00"), "08:58")
        self.assertEqual(wake.wake_hhmm("00:01"), "23:59")
        self.assertEqual(wake.first_scan_time({"mode": "times", "times": ["21:00", "09:00"]}), "09:00")

    def test_command_is_a_plain_pmset_repeat(self):
        self.assertEqual(wake.pmset_command("08:58"), "/usr/bin/pmset repeat wakeorpoweron MTWRFSU 08:58:00")

    def test_nothing_is_stored_on_the_machine(self):
        with open(wake.__file__) as f:
            src = f.read()
        self.assertNotIn("sudoers", src)

    def test_setup_is_a_noop_off_mac(self):
        logs = []
        with mock.patch.object(wake, "is_mac", return_value=False):
            self.assertFalse(wake.setup({"mode": "times", "times": ["09:00"]}, logs.append))


if __name__ == "__main__":
    unittest.main()
