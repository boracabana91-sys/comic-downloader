# Sports Clipper

Watches the sources you have permission to use, cuts out the dead time (timeouts, free-throw stretches, no-scoreboard shots,
low-interest plays), renders every resolution in one pass, and uploads to your YouTube channel 5-10 minutes after the source posts.

Clips stay in game order at normal speed. Audio is only trimmed in sync and re-encoded - never re-mixed or changed.

## vv29 - scan lists show old posts too, view colours, nothing is repeated

- **Scan now / 24/7** list the channel's last ~50 game videos (Team vs Team ... Highlights; no Shorts, reels or clips), newest first, each with its **posted date**, **views** and **status**.
- **Green = the newest 5 not clipped yet** (these are the ones that get reclipped). **Red = held** by a hold word. **Yellow = 100k+ views.** **Black = older post.** Videos already clipped/uploaded say *uploaded*.
- **Scan now** takes the newest 5 not already uploaded (earlier "first scan" notes no longer hide them). **24/7** still only picks up new posts.
- A video already clipped/uploaded is **never repeated**: the 24/7 scan skips it, Reclip all highlighted skips it, and Reclip selected asks first.
- The log says what the scan found: how many were checked, left out (Shorts/clips/other titles), new, held, older.

## vv28 - hold words, 5 per scan, red/green scan list, one announcer line

- **Hold words:** type words (e.g. `Lakers, LA`) in the **Hold words** box. In *Scan now* or *24/7*, a title containing one is **held**: it is not downloaded or reclipped.
  Matching is by whole word, so `LA` does not catch `Atlanta`. Held titles are listed in **Held titles**; select one and press **Use this video** to put its link in Search, then reclip/upload it yourself (a single link is never held).
- **5 videos per scan** (changeable with *Videos per scan*); held titles do not use up the 5.
- **Scan results:** scanned videos appear in the video list - good ones in green, held ones in red.
- **Layout:** *Scan now* / *Start 24/7* / *Stop* sit right under *Scan all videos*; *When to scan* and the other settings moved to the bottom.
- **Description:** only the one best announcer line is quoted; garbled caption pieces (`>>`, broken ALL-CAPS, one-word crumbs) are cleaned or dropped.
- The red **copyright claim** button and the marked-source list are removed (old settings are cleaned up automatically).

## vv27 - drag-and-drop update, red claim button

- **Update without reinstalling:** download the new `SportsClipper-Mac.zip`, then drag it onto the **Drop the new SportsClipper-Mac.zip here** box in the window (or click the box and choose it).
  The app checks it is a Sports Clipper update, closes, swaps in the new version, keeps the old one as a backup in `~/SportsClipper/update/previous`, and opens again by itself.
  Your settings, channels, YouTube login and videos live in `~/SportsClipper` and are never touched.
- Works from the installed app in the Applications folder. If macOS runs the app from a protected copy (opened straight from Downloads), the box tells you to drag SportsClipper.app
  into Applications and open it from there first.
- The **This source got a copyright claim** button now has red bold text.

## vv26 - free hashtags, Gametime card cut, game ends at the final score, claim-risk sources wait for OK

- **Free mode (no key, always works):** description = fair-use text, the best commentator lines picked from the captions, the subscribe line, then lowercase hashtags:
  `#nbahighlights #nba #gametimehighlights #emberhoops` first, then the matchup's own (team nicknames, city+nickname, each team's star, matchup), max 15.
  The brand four live in `brand_hashtags` in config.json. The YT Preview shows the hashtags the moment you paste or highlight a video; the rules check that the four are there and lowercase.
- **'GAMETIME HIGHLIGHTS' stats card** (the dark box-score card, text on the left, right side empty) is found while analysing and cut, at the start or the end.
- **End of the game:** the clip ends 4 s after the last running-clock play (the final score), so no end credits. Overtime keeps the clock running again, so it stays in.
  (The app reads the clock and the score bug, not the score digits, so a tie is recognised by the clock starting again.)
- **Private means private:** uploads are only scheduled to go public at the source time when Privacy is Public; Private / Unlisted stay exactly that.
- **Claims:** YouTube's copyright (Content ID) claims are decided by YouTube after upload; the app cannot see them. After a video gets a claim, press **This source got a copyright claim**
  in the YT Preview: that source channel is added to `claim_risk_sources`, and its videos are never auto-uploaded again: they wait for **OK - post it**.

## vv25 - YT Preview on paste / highlight, one-button YouTube login, private by default

- Paste one video link in Search (it is read by itself) or highlight any video: the **YT Preview** fills at once - file name, title, tags and every rule.
  The description's announcer lines say "Pending" until the video is downloaded; then the preview refreshes with the real lines.
- Reclip with a pasted link reads the video first and then reclips it.
- **Connect YouTube**: press it, sign in once in the browser window, press Allow. The login is saved ("Connected: <channel>"); every upload after
  that (OK - post it, and the 24/7 auto-upload) uses it. Disconnect forgets it.
- **Privacy** drop-down (Private / Unlisted / Public) in the window. It starts on **Private**. Privacy is set by the app on each upload, not on the channel.

### The Google key file (one time only)
Google will not open a sign-in window unless the app carries a key file. You make it once:
1. Go to console.cloud.google.com and sign in with the channel's Google account. Create a project (any name, e.g. "Sports Clipper").
2. Menu > APIs & Services > Library > search **YouTube Data API v3** > **Enable**.
3. APIs & Services > **OAuth consent screen** (Google Auth Platform): choose **External**, fill the app name and your email, save. Under Audience add your own Google
   address as a **Test user**; then press **Publish app** (In production) so the login does not expire after 7 days. The "unverified app" notice is normal: Advanced > Go to app.
4. APIs & Services > **Credentials** > Create credentials > **OAuth client ID** > Application type **Desktop app** > Create > **Download JSON**.
5. In Sports Clipper press **Connect YouTube**. The first time it asks for that JSON file (choose it; it is copied into the app's folder, never asked again),
   then the browser sign-in opens.

## vv24 - YT Preview before the cut, and Best Clips

Order of every Reclip, Test and single-video link (upload on or off):
1. Download the best resolution.
2. Cut the game down (normal reclip, or **Best Clips** if ticked).
3. Read the announcers' captions and write the description (fair-use text, 2-3 commentator lines, hashtags).
4. **YT Preview fills here** - file name, title, description, tags and every rule - before any video is rendered.
5. Render the sizes and the thumbnail.
6. The rules are checked again on the finished file (a failure holds the video).
7. Upload: automatic on the 24/7 scan, or press **OK - post it** after a Test / manual Reclip.

**Best Clips** (tick in the main window, OFF by default): instead of the normal reclip, keep only the best moments - the loudest crowd and
commentator reactions (plus motion). Each is about 18 s (10 s before the peak, 8 s after), never through dead time, in game order, up to the
"at most" length. Untick it for the normal vv23 reclip.

## vv23 - Reclip no longer says "channel not in your list" for your own channels

- A video counts as yours when its channel id, the channel it was listed from, its channel name or a playlist you added is in your channels.
- A video from a channel that is not in your list asks once: "Is this your channel / do you have permission?" Yes adds the channel (permission note saved) and reclips.
- Adding a channel is the permission statement; the box starts ticked. The rights gate is unchanged: only channels in your list are reclipped.

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

## vv22: channel rules, YT Preview, OK - post it (new in this version)
- **What the 24/7 scan takes:** only videos whose title names two NBA teams and "highlights". Shorts, reels, clips, one-team posts and videos under 5 minutes are skipped (and remembered, never downloaded). It downloads the best resolution available and reclips from that.
- **File name:** `STAR vs STAR MMDDYY_1080p.mp4` (the star alias of team 1, then team 2, then the game date as month-day-year). The other sizes use the same name with `_720p`, `_480p`.
- **Title:** `Oklahoma City Thunder vs Houston Rockets - FULL GAME HIGHLIGHTS | October 15, 2026`. The SEO writer may swap FULL GAME for FLASHY or GREAT. If the source says playoffs the title says `PLAYOFF HIGHLIGHTS`. The thumbnail headline follows the title.
- **Description:** the fair-use text first, then commentator lines, a subscribe line and hashtags.
- **Checked before every upload:** title pattern, both teams, 100 characters, playoffs matching the source, fair-use text first, hashtags, 8+ tags, tag length, file name pattern, star aliases, file exists. If any rule fails the video is **held**: nothing uploads, the files stay on your drive and the activity log says which rule failed. Videos that pass upload by themselves.
- **YT Preview** (its own box, separate from the thumbnail preview): file name, title, description, tags and a green/red line per rule. **Test on a video file** fills it; **OK - post it** uploads that test video exactly as shown (only enabled when every rule passes).

## vv21: close-up thumbnails, three AI writers, commentator lines (new in this version)
- **Thumbnail:** two big faces (left and right), a dark centre column with gold stripes, the headline in a black box (FLASHY / GREAT / FULL GAME follows the title), a round team badge above and below (colour + letters, no trademarked logos) and the length bottom right.
- **Proportioned faces:** the app finds each face (a small face-finder model is built in), levels the eyes, sizes both faces to the same share of their panel and puts the eyes on the same line. A photo is not used when the player looks sideways, up or down, the head is tilted, the face is small or blurry, or it is cut by the edge. The next good photo of that player is used instead and the activity log says so. Your chosen photo is kept whenever it passes.
- **More front-facing close-ups:** a cloud search added up to 3 front-facing close-ups per player (Wikimedia Commons, free licences, credits in `players/CREDITS.txt`). Close-ups with an old team's jersey are offered in the Photo drop-down but are never the default.
- **Three AI writers** (set the key in `config.json`): one for the SEO title and FLASHY/GREAT choice, one for reach tags and hashtags (NBA fans, basketball nerds), one for the two teams' die-hard fans. Title: `Denver Nuggets VS Miami Heat - FLASHY HIGHLIGHTS - October 17, 2026`.
- **Description:** your fair-use paragraph first, then 2-3 lines a commentator said about great plays (from the video's captions, only real lines, never invented), then a short subscribe line and hashtags. No captions on the video = no commentator lines.
- Layout drop-down / tick: the older full-body layout is still available.

## vv20: scan only what you highlight, reclip the newest 3, auto wake-up
- **Highlight channels:** click (Cmd-click for several) in the channel list. Only highlighted channels are scanned, by Scan now and by Start 24/7. Nothing highlighted = nothing scanned.
- **Scan now** no longer starts work: it lists the newest 3 unprocessed videos of the highlighted channels, in **green**, already selected.
- **Reclip all highlighted** runs every selected video in the list one after another (reclip once, render the sizes, upload, thumbnail). A channel without the permission box ticked is skipped. Start 24/7 takes the newest 3 per scan on its own.
- **One upload per video:** the 1080p is uploaded; YouTube makes its own 720p/480p/360p from it. Your 720p and 480p renders stay on the drive. A video already uploaded is never done twice.
- **Failed upload:** a pop-up and the activity log say what failed and where the finished videos are; the files stay on the drive.
- **Set up auto wake-up (Mac):** asks for your Mac password in macOS's own box (nothing is stored) and makes the Mac wake daily 2 min before the first scan. While Start 24/7 runs the app keeps the Mac awake. Keep it plugged in.

## vv19: the clip ends at the final buzzer, starts at the jump ball by default
- **Fixed: the end of the game was cut off.** When the scoreboard clock could not be read, the app guessed that the last 6% of the video was the post-game interview and always cut it, even when it was real play (that is why the ending never changed with the maximum minutes). That guess is gone.
- **How the end is found now:** the app finds where the **score bug** disappears for good (the game is over) and cuts the post-game interview after that, with a few seconds to spare. If the bug stays on screen to the last second (as in a highlights video), nothing is cut. If the app can tell neither from the clock nor from the bug, **nothing** is cut at the end (the log says so) - it never guesses.
- **Start at the jump ball is now ticked by default** on a new install, and **Include post-game interview** stays unticked (the interview is cut). Both are ticks in the window: untick the first to keep the opening, tick the second to keep the interview. If you used an earlier version, your saved choice is kept.
- Checked on the Nets at Heat video in 360p and 480p: the clips now run to the last play.
- Limit: the score bug has to be on screen for more than half of the video (any full game or highlights video is).

## vv18: the jump-ball start works on any scoreboard layout; more Giannis photos
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
