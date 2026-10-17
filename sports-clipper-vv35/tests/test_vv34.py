"""vv34: YouTube's 'The page needs to be reloaded' is retried like the bot check."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportsclipper import sources  # noqa: E402

RELOAD = "ERROR: [youtube] KcLfEwwzAw4: The page needs to be reloaded."


class Reload(unittest.TestCase):
    def setUp(self):
        sources._WORKING.clear(); sources.SETTINGS.update({"browser": "auto", "cookies": ""})

    def test_it_counts_as_a_block(self):
        self.assertTrue(sources.is_bot_block(RELOAD))
        self.assertFalse(sources.is_bot_block("HTTP Error 404"))

    def test_second_plain_try_can_succeed(self):
        calls = []
        def run(extra):
            calls.append(extra)
            if len(calls) == 1:
                raise RuntimeError(RELOAD)
            return "ok"
        self.assertEqual(sources.with_auth(run), "ok")
        self.assertEqual(len(calls), 2); self.assertEqual(calls[1], {})

    def test_it_moves_on_to_a_browser_login(self):
        seen = []
        def run(extra):
            seen.append(extra)
            if "cookiesfrombrowser" in extra:
                return "ok"
            raise RuntimeError(RELOAD)
        self.assertEqual(sources.with_auth(run), "ok")
        self.assertEqual(seen[-1]["cookiesfrombrowser"], ("chrome",))

    def test_still_failing_says_to_wait_and_retry(self):
        with self.assertRaises(RuntimeError) as cm:
            sources.with_auth(lambda e: (_ for _ in ()).throw(RuntimeError(RELOAD)))
        self.assertIn("wait a minute", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
