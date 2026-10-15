# Comic Series Downloader (separate app)

A second app next to **Comic Downloader**. Both can be installed at the same time; they do not touch each other.
Comic Downloader = one chapter link. **Comic Series Downloader = a page that lists many chapters, done automatically.**

## How to use (click by click)
1. Open the app.
2. Copy the link of the page that lists all the chapters. Click **Paste**, then **Find chapters**.
3. The chapters appear in a list, all ticked. Click **Select none**, then Shift-click to tick a range, or leave all ticked. **Only new ones** ticks chapters not downloaded yet.
4. Click **Choose folder** (default: Downloads/Comic Series).
5. Choose **Send to** (your e-reader), the EPUB question, promo hiding and cover, exactly like Comic Downloader.
6. Click **Download selected chapters** and leave it. It does every chapter in order and shows progress.

## What it does for you
- Each chapter: download, hide promo, add cover, make your gadget's file (and EPUB if Yes). Same engine as Comic Downloader v11.
- Files go in `<Series name>/`: image folders `Series - Chapter 012 - Pages 1-5`, and all the e-reader files together in the gadget folder (e.g. `For Kobo Clara`).
- One bad chapter never stops the rest. Problem chapters are tried once more at the end and listed in the log.
- **Stop** any time. Press Download again and finished chapters are skipped. Come back later when new chapters appear and use **Only new ones**.
- If you change gadget, EPUB, pages per folder, cover or promo words, finished chapters are made again for the new settings. "Make finished chapters again" forces it.

## Mac "blocked app" fix
Terminal: type `xattr -cr ` (with a space), drag the app into the window, press Enter.

## Chapter finder
On luacomic.org it asks the website for the full chapter list (all pages, 30 at a time) using the series number in the page. Other sites: it reads the chapter links in the page.

## Not yet tested on a real site
The chapter finder was written from the real luacomic.org data you sent, but was tested here on a practice website, because the build computer cannot reach luacomic.org. If "No chapters found" appears, send the link to your developer.
