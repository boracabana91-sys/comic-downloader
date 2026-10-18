"""vv25: YT Preview before the download (pending description), one-button YouTube connect, private by default."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import config, metadata, post, rules, uploader  # noqa: E402

TITLE = "Oklahoma City Thunder vs Houston Rockets FULL GAME HIGHLIGHTS | October 15, 2026"


def cfg():
    c = config.load(os.path.join(tempfile.mkdtemp(), "none.json"))
    return c


class PreviewBeforeDownload(unittest.TestCase):
    def setUp(self):
        self.c = cfg()
        self.pp = post.preview_post(self.c, TITLE, datetime(2026, 10, 15, tzinfo=timezone.utc), "A")

    def test_title_file_and_tags_are_filled_in(self):
        m = self.pp["meta"]
        self.assertIn("Thunder", m["title"]); self.assertIn("Rockets", m["title"])
        self.assertTrue(self.pp["stem"] and len(m["tags"]) >= 8)

    def test_description_is_pending_but_still_follows_the_rules(self):
        d = self.pp["meta"]["description"]
        self.assertTrue(d.startswith(metadata.DISCLAIMER))
        self.assertIn(post.PENDING_LINE, d)
        f = self.pp["stem"] + "_1080p.mp4"
        self.assertEqual(rules.failed(rules.check(self.pp["meta"], f, self.pp["teams"], TITLE, self.c, pending=True)), [])

    def test_needs_no_network_or_ai(self):
        with mock.patch.object(metadata, "_ask", side_effect=AssertionError("no AI before the download")), \
             mock.patch.object(post.captions, "fetch", side_effect=AssertionError("no captions before the download")):
            post.preview_post(self.c, TITLE, None, "A")


class Privacy(unittest.TestCase):
    def test_new_installs_are_private(self):
        self.assertEqual(config.DEFAULTS["upload"]["privacy"], "private")

    def test_an_old_public_setting_becomes_private_once(self):
        p = os.path.join(tempfile.mkdtemp(), "c.json")
        json.dump({"config_version": 11, "upload": {"privacy": "public"}}, open(p, "w"))
        self.assertEqual(config.load(p)["upload"]["privacy"], "private")
        json.dump({"config_version": 11, "vv25_privacy": True, "upload": {"privacy": "unlisted"}}, open(p, "w"))
        self.assertEqual(config.load(p)["upload"]["privacy"], "unlisted")        # the window's choice is kept


class Connect(unittest.TestCase):
    def test_no_login_means_not_connected(self):
        c = cfg(); c["upload"]["token"] = os.path.join(tempfile.mkdtemp(), "t.json")
        self.assertFalse(uploader.is_connected(c))

    def test_key_file_found_in_the_apps_folder(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "client_secret.json"), "w") as f:
            f.write("{}")
        c = cfg(); c["upload"]["client_secret"] = ""
        with mock.patch.object(config, "HOME", d):
            self.assertTrue(uploader.key_file(c).endswith("client_secret.json"))
        c["upload"]["client_secret"] = ""
        with mock.patch.object(config, "HOME", tempfile.mkdtemp()):
            self.assertEqual(uploader.key_file(c), "")

    def test_connect_without_a_key_file_says_so(self):
        c = cfg(); c["upload"]["client_secret"] = ""
        with mock.patch.object(config, "HOME", tempfile.mkdtemp()), self.assertRaises(RuntimeError):
            uploader.connect(c)

    def test_disconnect_removes_the_saved_login(self):
        c = cfg(); c["upload"]["token"] = os.path.join(tempfile.mkdtemp(), "t.json")
        open(c["upload"]["token"], "w").write("{}")
        uploader.disconnect(c)
        self.assertFalse(os.path.exists(c["upload"]["token"]))


if __name__ == "__main__":
    unittest.main()
