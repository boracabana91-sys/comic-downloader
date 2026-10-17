"""vv33: YouTube 'sign in to confirm you're not a bot' -> retry other ways, then borrow a browser's login."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import sources  # noqa: E402

BOT = "ERROR: [youtube] 3G3KP7fClLU: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies"


class Auth(unittest.TestCase):
    def setUp(self):
        sources._WORKING.clear(); sources.SETTINGS.update({"browser": "auto", "cookies": ""})

    def test_blocked_requests_move_through_the_ways_until_one_works(self):
        seen = []
        def run(extra):
            seen.append(extra)
            if "cookiesfrombrowser" not in extra or extra["cookiesfrombrowser"] != ("safari",):
                raise RuntimeError(BOT)
            return "file.mp4"
        logs = []
        self.assertEqual(sources.with_auth(run, logs.append), "file.mp4")
        self.assertEqual(seen[0], {})                                              # plain first
        self.assertIn("extractor_args", seen[1])                                   # then other player types
        self.assertEqual([e.get("cookiesfrombrowser") for e in seen[2:]], [("chrome",), ("safari",)])
        self.assertEqual(sources._WORKING["name"], "safari login")
        self.assertTrue(any("safari login" in m for m in logs))

    def test_the_way_that_worked_goes_first_next_time(self):
        sources._WORKING["name"] = "safari login"
        self.assertEqual(sources.auth_attempts()[0][0], "safari login")

    def test_other_errors_are_not_retried(self):
        calls = []
        def run(extra):
            calls.append(extra); raise RuntimeError("HTTP Error 404: video removed")
        with self.assertRaises(RuntimeError):
            sources.with_auth(run)
        self.assertEqual(len(calls), 1)

    def test_all_ways_failing_gives_a_clear_message(self):
        with self.assertRaises(RuntimeError) as cm:
            sources.with_auth(lambda extra: (_ for _ in ()).throw(RuntimeError(BOT)))
        self.assertIn("Open YouTube in Chrome", str(cm.exception))

    def test_chosen_browser_and_cookie_file(self):
        sources.SETTINGS.update({"browser": "firefox", "cookies": __file__})
        names = [n for n, _ in sources.auth_attempts()]
        self.assertEqual(names, ["plain", "other player types", "cookies file", "firefox login"])
        sources.SETTINGS["browser"] = "none"
        self.assertEqual([n for n, _ in sources.auth_attempts()][-1], "cookies file")

    def test_configure_reads_the_settings(self):
        sources.configure({"youtube_browser": "Brave", "cookies_file": ""})
        self.assertEqual(sources.SETTINGS["browser"], "brave")

    def test_download_retries_with_a_browser_login(self):
        import types, tempfile
        used = []
        class Y:
            def __init__(self, opts): self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, url, download=True):
                used.append(dict(self.opts))
                if "cookiesfrombrowser" not in self.opts:
                    raise RuntimeError(BOT)
                return {"id": "x"}
            def prepare_filename(self, info): return "/tmp/x.webm"
        v = sources.Video("3G3KP7fClLU", "t", __import__("datetime").datetime.now(), url="https://www.youtube.com/watch?v=3G3KP7fClLU")
        with mock.patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=Y)}), \
             mock.patch("sportsclipper.media.need", return_value="ffmpeg"):
            out = sources.fetch(v, tempfile.mkdtemp())
        self.assertEqual(out, "/tmp/x.mp4")
        self.assertEqual(used[-1]["cookiesfrombrowser"], ("chrome",))


if __name__ == "__main__":
    unittest.main()
