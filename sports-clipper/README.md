# Sports Clipper

Watches the sources you have permission to use, cuts out the dead time (timeouts, free-throw stretches, no-scoreboard shots,
low-interest plays), renders every resolution in one pass, and uploads to your YouTube channel 5-10 minutes after the source posts.

Clips stay in game order at normal speed. Audio is only trimmed in sync and re-encoded - never re-mixed or changed.

## Rights gate (important)
A source is only processed if it is ticked **licensed** AND has a note saying where the permission comes from. Anything else is skipped
before a single byte is downloaded. There is no blur / recrop / logo-hiding step: copyright matching works on the footage itself,
so hiding logos would not make unlicensed footage safe - use licensed, own, or permissioned sources.

## Get the program (Mac) - same way as Comic Downloader
1. On the GitHub page of this project click **Releases** (right side), then the newest **Sports Clipper** release. Under **Assets** download `SportsClipper-Mac.zip`.
2. Double-click `SportsClipper-Mac.zip` in Downloads. A file named **SportsClipper** appears.
3. Open **Terminal** (`Command + Space`, type `Terminal`, Enter). Type `xattr -cr ` (with a space at the end, do NOT press Enter yet), drag **SportsClipper** from Downloads into the Terminal window, then press **Enter**. Nothing visible happens, which is normal.
4. Close Terminal and double-click **SportsClipper**. If the Mac still refuses: right-click it, choose **Open**, then **Open**.
5. **Add a channel.** Paste the channel's YouTube link (for example `https://www.youtube.com/@ChannelName`) and press **Add channel**. The name and channel ID fill in by themselves. Tick the box saying you own the channel or have permission to use its videos first. Choose the scan schedule and the minutes after the source posts, then **Save settings**.
5b. **Check setup.** Press **Check setup**. Every line says OK or FAIL with the reason, so you can see what works.
6. Press **Test on a video file...** first and pick any video. Results are saved in `SportsClipper/output/manual` inside your home folder.
7. For auto-upload: in Google Cloud Console create a project, enable *YouTube Data API v3*, create an *OAuth client ID* (type *Desktop app*) and download the json file. In the program tick **Upload to our channel**, choose that file, **Save settings**. The first upload opens a browser page where you approve once.
8. Press **Start 24/7** and leave the program open. Keep the Mac plugged in with sleep turned off (System Settings > Battery > Options).

Nothing else to install - ffmpeg is built into the app, and no password is needed.

**AI titles (Claude Haiku 5.5, optional):** this is the default. Without a key the app uses plain titles. To use it, open `~/SportsClipper/config.json` and put your Anthropic API key in `"api_key"` under `"ai"`, then Save settings. The key is separate from a Claude chat subscription.

## Developers: run from source
`pip install -r requirements.txt` then `python -m sportsclipper gui` (or `clip FILE`, `scan`, `run`). `install-launchd` makes the CLI start at login.

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

## Quality and resolutions
- Every size you tick is produced. A size above your source's height (for example 1080p from a 720p video) is **upscaled** and its file name says `_upscaled`. It looks sharper than a plain stretch but cannot add detail the source never had. Real 1080p needs a 1080p source.
- Encoding uses the software encoder (libx264) with a quality setting per size, which keeps more detail than the Mac's hardware encoder. It is slower: expect several minutes per video.

## Thumbnail (automatic)
After each render the app picks the clearest **solo close-up** from the video (one prominent face, sharp, not a crowd shot), keeps the scoreboard out of the frame, and adds the team names stacked on the left, the date band, and the duration badge. Grey smoke and haze are re-graded to ember red. It is uploaded to YouTube with the video. The "Auto thumbnail" tick turns it off.

Limits: it can't tell which player is the "best"; it picks the clearest close-up. Choosing by stats needs a stats source, which is a future step.
