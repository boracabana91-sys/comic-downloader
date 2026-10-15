# Sports Clipper

Watches the sources you have permission to use, cuts out the dead time (timeouts, free-throw stretches, no-scoreboard shots,
low-interest plays), renders every resolution in one pass, and uploads to your YouTube channel 5-10 minutes after the source posts.

Clips stay in game order at normal speed. Audio is only trimmed in sync and re-encoded - never re-mixed or changed.

## Rights gate (important)
A source is only processed if it is ticked **licensed** AND has a note saying where the permission comes from. Anything else is skipped
before a single byte is downloaded. There is no blur / recrop / logo-hiding step: copyright matching works on the footage itself,
so hiding logos would not make unlicensed footage safe - use licensed, own, or permissioned sources.

## Install on Mac - step by step
1. **Get the files.** Download `sports-clipper-v0.1.zip` (or on GitHub: branch `sports-clipper` > Code > Download ZIP, then use the `sports-clipper` folder inside). Double-click the zip. Move the `sports-clipper` folder to your Documents folder.
2. **Install Homebrew** (skip if you already have it). Open https://brew.sh, copy the one line it shows, open **Terminal** (`Command + Space`, type `Terminal`, Enter), paste it, press Enter, and follow what it says. This takes a few minutes.
3. **Allow the installer to run.** In Terminal type `xattr -cr ` (with a space at the end, do NOT press Enter yet), drag the `sports-clipper` folder from Documents into the Terminal window, then press Enter. Nothing visible happens, which is normal.
4. **Run the installer.** Double-click `install-mac.command` inside the folder. If the Mac refuses, right-click it, choose **Open**, then **Open**. Wait until it says **DONE** (a few minutes).
5. **Open the program.** Double-click `Open Sports Clipper.command`. The window opens.
6. **Add a source.** Type a name, choose the type (youtube / folder / link), paste the channel ID (starts with UC) or pick a folder. Tick the permission box and write where the permission comes from. Press **Add source**.
7. **Pick your settings.** Scan schedule, minutes after the source posts (5 to 10), sizes, and Save settings.
8. **Try it before going live.** Press **Test on a video file...**, choose any video. The result is saved in `~/SportsClipper/output/manual` (a folder named SportsClipper in your home folder).
9. **Connect YouTube** (needed only for auto-upload). In Google Cloud Console: create a project, enable *YouTube Data API v3*, create an *OAuth client ID* of type *Desktop app*, download the json file. In the program tick **Upload to our channel**, choose that json file, Save settings. The first upload opens a browser page where you approve once.
10. **Run 24/7.** In the program press **Start 24/7**. For it to survive restarts, open Terminal in the folder and run `.venv/bin/python -m sportsclipper install-launchd`, then paste the `launchctl load ...` line it prints. In System Settings > Battery > Options turn on preventing automatic sleep, and keep the Mac plugged in.

Optional: titles written by Claude Haiku 5.5 need an API key: in Terminal run `launchctl setenv ANTHROPIC_API_KEY your-key` and tick the box in the program.


## Try it on a video file first (no upload)
```
python -m sportsclipper clip ~/Downloads/game.mp4
```
Outputs go to `~/SportsClipper/output/manual/`. Use `--ratio 0.6` to change how much is kept.

## Run 24/7
1. Open the window (`python -m sportsclipper gui`), add sources, choose scan schedule, press **Save settings**.
2. For YouTube upload: create an OAuth "Desktop app" client in Google Cloud Console (YouTube Data API v3 enabled),
   download `client_secret.json`, pick it in the window. The first upload opens a browser to approve once.
3. `python -m sportsclipper install-launchd` then run the `launchctl load ...` line it prints. It starts at login and restarts if it stops.
4. Keep the Mac awake: System Settings > Battery > Options > prevent automatic sleeping (or run `caffeinate -s`).

## Settings (`~/SportsClipper/config.json`)
| key | meaning |
|---|---|
| `schedule` | `{"mode":"interval","hours":2}` or `{"mode":"times","times":["09:00","21:00"]}` |
| `publish_delay_min` | `[5,10]` minutes after the source's publish time (uses YouTube's scheduled publish) |
| `target_ratio` | share of the source to keep (0.59 matched the sample) |
| `clock_roi` | where the game clock digits are, as fractions of the frame `[x,y,w,h]` - change this for other broadcasts |
| `min_dead_s` | clock frozen longer than this is cut |
| `resolutions`, `allow_upscale` | export ladder; sizes above the source height are skipped unless `allow_upscale` |
| `ai` | titles/descriptions with `claude-haiku-5-5` (set `ANTHROPIC_API_KEY`) |
| `cloudinary` | optional backup of the best render |

## Tests
`python3 -m unittest discover -s tests`
