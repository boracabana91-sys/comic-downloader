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

## vv18: the jump-ball start works on any scoreboard layout; more Giannis photos (new in this version)
- **Start at the jump ball** no longer depends on the app being able to read the scoreboard clock. When the clock cannot be read (a different broadcast layout), the app now finds the **score bug** (the small score box that appears once the game starts, wherever it sits on screen). The jump ball is the wide-camera shot just before the bug appears; the clip starts 3 seconds before the tip (setting `tip_lead_s`). The log says which method was used (`from the scoreboard clock` or `from the score bug`).
- Tested on a Nets at Heat preseason video (clock not readable): the clip now starts at the wide shot of the opening tip instead of the lineups and bench shots before it.
- Limits: it needs the score bug to appear within the first 30 minutes and to stay on screen; if no bug is found, you get a warning in the log and the clip is not shortened.
- **Giannis:** Giannis Antetokounmpo now has 4 photos and 3 close-ups (Bucks 2021 and the 2022 All-Star game, marked old team). Wikimedia Commons has no free photo of him with the Heat, in Greece's jersey or from the 2025-26 season, so a Heat photo of your own can be dropped into `~/SportsClipper/players/` (see vv15).

## vv17: reclip one video from its link
- The **Search** box over the video list now takes a **link to one video** as well as a playlist link. Paste it (`youtube.com/watch?v=...`, `youtu.be/...`, a Short or a live link) and press **Enter** (or **Scan all videos**): only that video is read, it is selected for you, and **Reclip selected video** reclips it.
- A video link that also carries `&list=...` is treated as that one video, not the whole playlist. For the playlist, paste the playlist link.
- The permission rule is unchanged: a video is only reclipped if its channel is in your list with the permission box ticked; otherwise you get the usual message.

## vv16: head-and-neck close-ups
- Every photo that shows a clear face now also has a **close-up** (head, neck and shoulders) cut from the same picture. It is offered in the **Photo** drop-down after the full-body photos, marked **(close-up)**, so when the whole body does not look good you can pick the head shot. A close-up of an old-team photo is also marked **(old team)**.
- The first photo of each player (the default) is unchanged. Close-ups were checked by eye; the ones that came out badly (two people, a ball over the face) were left out.
- Your own photos work the same way: name a picture `head1.png`, `head2.png` ... in the player's folder to make it a close-up option.

## vv15: old-jersey photos as extra options
- Photos that show a player in an **older team's jersey** are now offered too, marked **(old team)** in the Photo drop-down. They are never the default: if a team's first star only has old-team photos, the other star becomes the default (the first star is still in the Player drop-down).
- Players that had no photo before now have some, even if not perfect (Kyrie Irving, Paolo Banchero, Jaren Jackson Jr., Giannis in a Bucks jersey). Trey Murphy III has no free photo at all, so NOP offers only Zion Williamson.
- Replace any of them with your own photo by dropping it in `~/SportsClipper/players/<Team - ACR - Player>/`.

## vv14: start at the jump ball, 3 photos per star, rosters re-checked
- **Start at the jump ball:** a new tick, **Start at the jump ball**, next to the length options. When it is ticked, the video begins a few seconds before the opening tip and everything before it (long intros, warm-ups, pre-game talk) is cut. Leave it unticked for Playoff games where the pre-game is worth keeping. It reads the scoreboard clock: if the clock cannot be read, the video simply starts from the beginning as before.
- **3 photos for every team star** (also the 2nd star). Next to the **Player** drop-down there is now a **Photo** drop-down (Photo 1, 2, 3); the preview redraws at once and your choice is remembered per player (`photo_choice`). Photos are free-licence pictures with the background removed, hand-picked, and the author credits are in `players/CREDITS.txt`. Some players have fewer than 3 because no clear free photo of them exists (the list only offers photos that exist).
- **Rosters re-checked** against the summer 2026 trades and signings (for example Giannis Antetokounmpo is now with Miami). The first star of each team is the default; the second star is in the drop-down.
- **Your own photos still win:** a picture dropped into `~/SportsClipper/players/<Team - ACR - Player>/` (cutout.png, cutout2.png, cutout3.png) replaces the built-in one.
- **Photo limits:** free photos of a player often show an older team. Giannis, for example, only has Bucks photos so far; drop in your own Heat photo to replace it.

## vv13: cleaner thumbnail, font styles, no post-game interview, YouTube thumbnail check
- **Thumbnail:** the final score is gone. The **date sits in the middle, under "VS"**; the bottom band keeps the video length. Everything else is as in vv12.
- **Font style:** a **Font style** drop-down next to the preview (Impact, Anton, Bebas Neue, Archivo Black, Fjalla One, Russo One, Bangers). The preview redraws at once and your choice is remembered (`thumb_font`). Fonts are free (SIL Open Font License) and come inside the app.
- **Post-game interview:** tick **Include post-game interview** to keep it. It is **off by default**: everything after the last play is cut, and the "reach the minimum length" top-up never pulls it back in. When the scoreboard clock cannot be read the app cannot see where the game ends, so it drops the last ~6 % (at most 3 min) and says so in the log. CLI: `clip FILE --interview`.
- **Player pictures:** the pictures were fetched again with stricter rules - a photo is rejected if the player touches the left/right/top edge of the photo (arm, hand or head cut off), and photos that name the player's *current* team score higher than ones that name an old team (for example Durant in OKC blue). Five players have **no usable free photo** on Wikimedia Commons at the moment (Giannis Antetokounmpo, Tyler Herro, Kyrie Irving, Paolo Banchero, Matas Buzelis): they are left out of the drop-downs rather than shown with a bad cut-out. Several players have only an old-team jersey photo available, so a neutral Team USA / All-Star / college top was used where it looked better (Durant is now in a Team USA top, not OKC blue). You can always put your own `cutout.png` in `~/SportsClipper/players/<Team - ACR - Player>/` - your folder wins.
- **Thumbnail on YouTube:** YouTube does **not** read a thumbnail from inside the video file; it needs a separate picture, which the app sends right after the upload (the YouTube Data API call `thumbnails.set`). YouTube only allows this on a **verified channel** (youtube.com/verify). The app now checks YouTube's answer, retries while the video is still processing, and if it still fails shows a **pop-up with the reason** and where the picture is saved, so it can be set by hand in YouTube Studio.
- **Optional extras (both off by default):** *Save the thumbnail inside the video file* (cover picture in Finder / QuickTime; YouTube ignores it) and *Show the thumbnail for 1 second at the start* of the video. The separate YouTube thumbnail is always sent either way.

## vv12: you choose the final length
Instead of a percentage, set **Final length: at least [8] min, at most [12] min** in the window (`min_minutes` / `max_minutes` in `config.json`).
- Over your maximum: whole stretches of play are dropped (dullest first, spread through the game) until it fits.
- Under your minimum: the most active stretches that were cut (crowd noise + motion) are put back, in game order, until the minimum is reached.
- If the scoreboard clock cannot be read on a video (different broadcast layout), the app says so in the log and chooses by motion and crowd sound
  instead, so the result is never a one-minute scrap. For better dead-time cuts set `clock_roi` to where the clock sits.
- A video shorter than your minimum is kept whole. The log shows how much live play was found and the final length.
- CLI: `clip FILE --min 8 --max 12`.

## vv11: two-star thumbnails with a player drop-down
The thumbnail shows the star player of each team, one on each side: **team acronym** on top, the player's **alias** under it
(surname when there is no well-known alias), the player cut out from the photo background, and the date / duration band below.

- **Nothing to download or run.** The player pictures (Wikimedia Commons, free licences) are inside the app. Photo credits: `players/CREDITS.txt`.
- **Instant preview.** In the window, the *Thumbnail preview* box reads the two teams from a game title or file name ("DEN vs LAC",
  "Denver Nuggets vs LA Clippers"). It fills itself when you click a video in the channel list or pick a test file, or you can type a title.
- **Drop-down per team.** Teams with two players show a drop-down (the first is the default, e.g. Nikola Jokic - THE JOKER, or Jamal Murray - MURRAY).
  Change it and the preview redraws. The choice is remembered per team (`player_choice` in `config.json`) and is used for the real thumbnail.
- **Your own picture** (wins over the bundled one): make a folder `~/SportsClipper/players/<Team - ACR - Player Name>` (for example
  `Dallas Mavericks - DAL - Kyrie Irving`) and put a transparent-background `cutout.png` in it. An `alias.txt` in the folder sets the name shown.
  Any extra folder you add for a team appears in that team's drop-down. A team with no picture uses the older photo-style thumbnail.
- No free-licence photo was usable for a few players (Kyrie Irving, Jaren Jackson Jr., Trey Murphy III, Stephon Castle, Mark Williams, De'Aaron Fox),
  so Dallas defaults to Cooper Flagg until you add a Kyrie picture as above.
- Who is listed: edit `PLAYERS` in `sportsclipper/roster.py`. Stars follow the 2026-27 preseason rankings (NBA 2K27 top 100, Yahoo, CBS).

## Developers: run from source
`pip install -r requirements.txt` then `python -m sportsclipper gui` (or `clip FILE`, `scan`, `run`). `install-launchd` makes the CLI start at login.

## Try it on a video file first (no upload)
```
python -m sportsclipper clip ~/Downloads/game.mp4
```
Outputs go to `~/SportsClipper/output/manual/`. Use `--min 8 --max 12` to set the finished length in minutes.

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
| `min_minutes`, `max_minutes` | the finished clip is between these lengths (default 8 to 12) |
| `clock_roi` | where the game clock digits are, as fractions of the frame `[x,y,w,h]` - change this for other broadcasts |
| `min_dead_s` | clock frozen longer than this is cut |
| `resolutions`, `allow_upscale` | export ladder; sizes above the source height are skipped unless `allow_upscale` |
| `ai` | titles/descriptions with `claude-haiku-5-5` (set `ANTHROPIC_API_KEY`) |
| `cloudinary` | optional backup of the best render |

## Tests
`python3 -m unittest discover -s tests`

## Quality and resolutions
- Every size you tick is produced. A size above your source's height (for example 1080p from a 720p video) is **upscaled** and its file name says `_upscaled`. It looks sharper than a plain stretch but cannot add detail the source never had. Real 1080p needs a 1080p source.
- On a Mac, encoding uses Apple's hardware encoder (VideoToolbox) with a bitrate per size. If it is not available, that size is redone with the software encoder (libx264) automatically. To always use the software encoder, set `"encoder": "libx264"` in config.json.
- The upload size (1080p) is made first and uploaded; the other sizes are made afterwards, several at once. The activity log shows how long each step took.
- The source frame rate is kept exactly (29.97 stays 29.97).
- Downloads prefer the H.264 version of a video, which the Mac decodes in hardware, and analysis uses hardware decoding too. 4K is off by default: a 720p or 1080p source upscaled to 4K takes much longer and adds no detail (tick 4K if you really want it).

## Scan all videos
Click a channel, then **Scan all videos**. The whole channel is listed (not just the latest 15), grouped like the channel: Videos, Live, Shorts, and each playlist as its own folder. Use the Search box to filter by title, open a folder, click a video and press **Reclip selected video**. Paste a playlist link in the add box to add just that playlist, or paste it in the **Search** box and press Enter to scan just that playlist without adding it. A video can only be reclipped if its own channel is in your list with the permission box ticked. Only channels with the permission box ticked can be reclipped.

## Highlights tick
Dead time is cut first: the intro before tip-off, timeouts, free-throw stretches and the post-game interview. If the video is still longer than your maximum minutes, whole chunks of play (12-45 s) are dropped, spread evenly through the game, the way the reference reclip does it. Never dropped: the tip-off, the last 2 minutes, and the loudest crowd moments. Play stays in game order at normal speed.

## Thumbnail (automatic)
After each render the app picks the clearest **solo close-up** from the video (one prominent face, sharp, not a crowd shot), keeps the scoreboard out of the frame, and adds the team names stacked on the left, the date band, and the duration badge. Grey smoke and haze are re-graded to ember red. It is uploaded to YouTube with the video. The "Auto thumbnail" tick turns it off.

Limits: it can't tell which player is the "best"; it picks the clearest close-up. Choosing by stats needs a stats source, which is a future step.
