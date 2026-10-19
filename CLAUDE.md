# Rules for working on this repo (Comic Downloader / Comic Series GOKU Downloader)

The user is not a coder. Keep replies fast, efficient and cordial.

## Do
- Give click-by-click steps.
- Say what is unverified.
- Keep it at $0.
- Send a sample first when asked.
- Ask before big changes.
- Measure results on real or test data before claiming a fix; ask for real files or photos when a problem can't be reproduced.
- Test on the real sites when the network allows (it is wide open now); say exactly what was and wasn't verified.
- End EVERY reply with the AI level and effort to use next (Sonnet 5.5 high for small fixes and site-reading; Opus 5.5 high for page-layout problems).
- Keep the revert paths: `Previous (v4)` in the window, the `series-v4` release, `v11` for the original Comic Downloader.

## Usage warning (the user asked for this)
Every message makes the model re-read the whole conversation, so long chats eat the user's weekly usage.
- When the conversation reaches about 95% by the token counter, START that reply with "⚠️ 95% - open a new chat" and then write a short handoff summary in the same style as the one the user gives at the start of a chat: what the program does, what works, what is unverified, next steps, do's and don'ts, latest build, and this usage-warning rule itself.
- Warn earlier, and say so plainly, if the chat gets heavy sooner (big logs, big file output).
- The counter only measures the conversation; the real weekly usage is in the Claude app under Settings -> Usage.

## Don't
- Don't change the old Comic Downloader (`core.py` engine is shared; keep it unchanged).
- Don't guess a fix from one number without data.
- Don't bypass blocked sites. comix.to blocks programs (403): the program never reads it, it redirects to the original source sites instead (en-thunderscans.com, madarascans.net, timelesstoons.org, plus sites the user pasted once).
- No vague "it should work" answers.
- Mac blocked-app fix: type `xattr -cr ` (with a space), drag the app into Terminal, press Enter.

## Project notes
- Branch `goku-v6`, version in `SERIES_VERSION`; builds: Actions -> "Build Comic Series GOKU Downloader" (workflow_dispatch on the branch) -> release `series-v<version>`.
- Key files: `series.py` (chapter finding, source lookup `KNOWN_SOURCES`, layouts), `series_app.py` (window), `fitpage.py` (snug fit), `core.py` (old engine). Tests: `test_series.py`, `test_fitpage.py`, `test_core.py`, `test_series_window.py`.
- Add a new source site: one line in `KNOWN_SOURCES`, after checking its real series page and a chapter with the program's own functions.
