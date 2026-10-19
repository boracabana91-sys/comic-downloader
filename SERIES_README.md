# Comic Series GOKU Downloader (separate app)

(Called Comic Series Downloader up to series-v5-test9.)

A second app next to **Comic Downloader**. Both can be installed at the same time; they do not touch each other.
Comic Downloader = one chapter link. **Comic Series GOKU Downloader = a page that lists many chapters, done automatically.**

## How to use (click by click)
1. Open the app.
2. Copy the link of the page that lists all the chapters. Click **Paste**, then **Find chapters**.
3. The chapters appear in a list, all ticked. Click **Select none**, then Shift-click to tick a range, or leave all ticked. **Only new ones** ticks chapters not downloaded yet.
4. Click **Choose folder** (default: Downloads/Comic Series).
5. Choose **Send to** (your e-reader), the EPUB question, promo hiding and cover, exactly like Comic Downloader.
6. Click **Download selected chapters** and leave it. It does every chapter in order and shows progress.

## What it does for you
- Each chapter: download, hide promo, add cover, make your gadget's file (and EPUB if Yes). Same engine as Comic Downloader v11.
- One folder per chapter: `<Series name>/Chapter 012/`. Pick the layout with the **Folder layout** toggle (a picture of the folders updates as you click):
  - **Sample 1:** the pictures (webp) and ONE file for the gadget (.cbz/.pdf) plus ONE .epub (if Yes), all loose inside the chapter folder.
  - **Sample 2:** the pictures in a `Pages` folder, and the gadget/EPUB files split into parts of N pages, inside the chapter folder.
- One bad chapter never stops the rest. Problem chapters are tried once more at the end and listed in the log.
- **Stop** any time. Press Download again and finished chapters are skipped. Come back later when new chapters appear and use **Only new ones**.
- If you change gadget, EPUB, pages per folder, cover or promo words, finished chapters are made again for the new settings. "Make finished chapters again" forces it.

## Chapter number on the cover
When you choose a cover picture, each chapter gets its own copy with the chapter number (like #52) in the upper right. It becomes page 1 of that chapter's files and the chapter folder's thumbnail. Untick "Put the chapter number on each chapter's cover" to use the plain cover.

## Page fit (TEST in series-v5-test)
- **New snug fit (test):** like Kindle Comic Converter books. Each screen shows whole scenes, shrunk to fit with a thin frame in the strip's own background colour. Nothing is zoomed in, and a scene is never cut in half. Only a single scene taller than about two screens is split, at its quietest row, so it stays readable.
- **Previous (v4):** exactly the pages from series-v4.
The program remembers your choice. Switching makes finished chapters again the next time you download them.
To go fully back: Releases → **series-v4** → download that app again. The GitHub tag `series-v4-stable` marks the code.

## Original / Source site bar (since series-v6-test2)
Directly under the link box a bar shows **Original / Source site: <website>** and an **Open site** button, so you can always check the source yourself.
- Paste a **comix.to** link and press Find chapters: comix.to only copies chapters and blocks programs, so the program takes the series name from the link and looks for it on the translation group's own site (now: timelesstoons.org). If found, the link box switches to that site and the bar shows it. If not found, the log says so and asks you to paste the group's own link.
- If some chapters are **locked with coins**, the log says which ones (e.g. "chapter 9 to 14"), that they are on the same site, and what to do: Open site, then later press Find chapters again and **New + out-of-date**. The program never pays or unlocks anything for you.

## Window size
Drag the window edges to resize it. The Download buttons and the log stay at the bottom. The program remembers the size and position you left it at.

## Mac "blocked app" fix
Terminal: type `xattr -cr ` (with a space), drag the app into the window, press Enter.

## Chapter finder
- **luacomic.org:** it asks the website for the full chapter list (all pages, 30 at a time) using the series number in the page.
- **timelesstoons.org** (since series-v6-test1): paste the series page, e.g. `https://timelesstoons.org/series/bloodshed-goddess-biography/`. Chapter numbers (also half chapters like 13.5) come from the words on each link, because the links themselves are only codes. Chapters with a lock (paid with coins) are left out; the log says how many. Pictures come from `cdn.meowing.org` and keep their true type (WebP, AVIF, JPG). Tick "Convert WebP to JPG" to get JPG.
- **Other sites:** it reads the chapter links in the page.
- **Sites behind a "Just a moment..." (Cloudflare) check, such as comix.to, do not work.** The program does not get past that check. Use the translation group's own site instead (comix.to copies chapters from them).

## Not yet tested on a real site
The chapter finder was written from the real luacomic.org data you sent, but was tested here on a practice website, because the build computer cannot reach luacomic.org. If "No chapters found" appears, send the link to your developer.
