# How I (Anne) update Cattyfied with Claude Code

1. Start a Claude Code session with the **comic-downloader** repository selected, and ask Claude to work on the **cattyfied** branch.
2. Say what you want changed in plain words, for example: "make the pause before the punch line 2.5 seconds by default".
3. Claude makes the change, runs the tests, and saves it to GitHub.
4. GitHub's Mac robot builds a new installer automatically (about 10–15 minutes).
5. To download it: on github.com open **comic-downloader** → **Actions** → the newest green ✅ run → at the bottom, **Cattyfied-installers**. Inside are **Cattyfied-Apple-Silicon.dmg** (Macs with an "M" chip) and **Cattyfied-Intel.dmg** (older Intel Macs).
   Not sure which Mac you have? Apple menu  → About This Mac: "Chip: Apple M…" = Apple Silicon, "Processor: Intel…" = Intel.
   Faster option (if the owner approves publishing): Claude pushes a tag named `cattyfied-vX.Y.Z` (never plain `vX`: those belong to the comic downloader). The build then appears at https://github.com/boracabana91-sys/comic-downloader/releases as a fast, permanent download.

The code lives in the **cattyfied** branch of the comic-downloader repository (choose that branch on GitHub).

Later (Phase 7) you'll be able to say "make an update pack" and drag the file onto Cattyfied instead.
