# Comic Downloader

Paste a chapter link, press Download. Images are saved in folders of 5 pages:

```
My Comic - Chapter 7 - Pages 1-5
My Comic - Chapter 7 - Pages 6-10
My Comic - Chapter 7 - Pages 11-12
```

Free. No account needed to use it.

## Get the program

1. On this page, click **Releases** (right side), then the newest one at the top.
2. Under **Assets**, download the file for your computer:
   - Windows: `ComicDownloader-Windows.exe`
   - Mac: `ComicDownloader-Mac.zip`

## Windows (first open)

1. Double-click `ComicDownloader-Windows.exe`.
2. If a blue "Windows protected your PC" box appears, click **More info**, then **Run anyway**.
3. This only happens the first time.

## Mac (first open) - follow these steps exactly

1. Double-click `ComicDownloader-Mac.zip` in your Downloads folder. A file named **ComicDownloader** appears next to it.
2. Open **Terminal**: press `Command + Space`, type `Terminal`, press Enter.
3. In the Terminal window, type this, **including the space at the end**, but do NOT press Enter yet:

   `xattr -cr `

4. Drag the **ComicDownloader** file from your Downloads folder into the Terminal window. Its location is typed in for you.
5. Press **Enter**. Nothing visible happens, which is normal.
6. Close Terminal and double-click **ComicDownloader**. Done. You will not need these steps again.

If the Mac still says it cannot be opened: right-click the app, choose **Open**, then click **Open**.

## Using it

1. Open the chapter page of the comic in your browser and copy its link.
2. Paste it in the **Chapter link** bar (or press **Paste**).
3. Press **Choose folder** to pick where to save (default: Downloads/Comics).
4. Press **Download**. Watch the progress bar. **Stop** pauses it, and pressing Download again continues where it stopped.

Options: **Pages per folder** (default 5) and **Convert WebP to JPG**.

## Hiding the promo words

**Hide Lua / translated / website promo** is ticked by default. After downloading, the program reads every page and finds promo text wherever it is: the website name, "Lua Scans", "translated / translating / transcribe", Discord, "official domain", "scam", "our website", "support us", "latest chapters" and similar.
- A promo block touching the top or bottom of a page is cut away down to where the comic picture starts. A page that is only promo is removed.
- A promo line in the middle of a page is painted over with the background color, or blurred if the background is busy.
- Story text and the Translator / Editor credit lines are not touched.

Type extra words in the **Also hide** box, separated by commas. Untick the box to skip this step and download faster.
Reading every page takes time (roughly 6 to 7 seconds for a very tall page), so a whole chapter takes a few minutes. The first run also loads the text reader, which takes a moment.

## Cover picture (thumbnail)

Drag a picture onto the **Drop your cover picture here** box (or click it, or press **Choose cover**). A small preview shows it. **Clear cover** removes it. If dragging from a web page doesn't work, save the picture to your Downloads folder first and drag the file.
The cover is used for every download until you clear it:
- It is saved as `cover.jpg` in each `Title - Pages ...` folder.
- On Mac and Windows, each of those folders shows your picture as its thumbnail. If it doesn't appear right away, close and reopen the folder.
- It becomes **page 1** of every Kobo `.cbz` and Kindle/other `.pdf` file, so the file opens on your cover.
- Your Kobo or Kindle decides which picture to show in its library. A Kobo normally uses page 1. Newer Kindles may show a plain cover for files you copied over yourself, whatever the file contains.

## Send to your e-reader or tablet

Pick your gadget in the **Send to** menu before pressing Download. The program also keeps the normal image folders.
Tall pages are cut into screen-sized pages at blank gaps, so the text stays readable. Any space around a page is filled with the page's own edge color, so no white bars appear.

**File type:** leave it on **Best for this gadget**, or choose **EPUB**, **PDF** or **CBZ** for any gadget. On a Kobo, EPUB is saved as `.kepub.epub` (Kobo's own kind, full-screen pictures). A Kindle cannot open EPUB files copied over with a USB cable, so the program offers PDF instead.
When it finishes, the window tells you what to do next, and **Open folder** opens the folder holding the files to drag.

| Gadget | File made | Folder |
|---|---|---|
| Kobo Clara, Libra, Sage, Forma, Elipsa | `.cbz` | For Kobo ... |
| Kindle (basic), Paperwhite (3 sizes), Colorsoft, Scribe | `.pdf` | For Kindle ... |
| PocketBook (6, 7, 7.8 inch) | `.pdf` | For PocketBook |
| Boox (6, 7, 10.3 inch) | `.pdf` | For Boox |
| reMarkable 2 | `.pdf` | For reMarkable |
| Tablet or phone | `.pdf` (color) | For Tablet or Phone |
| Custom size | `.pdf` or `.cbz` | For Custom Size |

Color gadgets (Kobo, Kindle Colorsoft, Boox, PocketBook, tablets) keep color. Kindle Paperwhite, Basic, Scribe and reMarkable get black and white pages.

**Custom size:** choose **Custom size**, type your screen width and height in pixels (from your gadget's specifications), choose `.pdf` or `.cbz`, and tick **Black and white** if the screen has no color.

### Kobo (drag and drop)
1. Plug the Kobo into the computer with its USB cable.
2. On the Kobo screen, tap **Connect**.
3. A drive named **KOBOeReader** appears. Drag the `.cbz` files from the "For Kobo ..." folder onto it.
4. Eject the drive (on Mac, click the small eject arrow next to it in Finder), then unplug.

### Kindle (drag and drop)
1. Plug the Kindle into the computer with its USB cable. A drive named **Kindle** appears.
2. Open the drive, then open its **documents** folder.
3. Drag the `.pdf` files from the "For Kindle ..." folder into **documents**.
4. Eject the drive, then unplug. The comics show up in your library.

### PocketBook (drag and drop)
1. Plug it in with its USB cable. If it asks, choose **Connect to PC**.
2. A drive appears. Drag the `.pdf` files into its main folder (or its **Books** folder).
3. Eject the drive, then unplug.

### Boox
Boox readers run Android, so copying works differently. On the Boox, look for its Wi-Fi file transfer (called BooxDrop on many models), open the web page it shows on your computer, and drag the `.pdf` files onto it. A USB cable also works; on a Mac you may need a free helper app such as OpenMTP.

### reMarkable 2
On the reMarkable turn on the **USB web interface** (Settings, then Storage). Plug it in with its USB cable, open `http://10.11.99.1` in your browser, and drag the `.pdf` files onto the page.

### Tablet or phone
Copy the `.pdf` files to the device (AirDrop, USB cable, or a cloud drive) and open them in any PDF reader or the Books app.

## If no images are found

Send the link you used to your developer. Sites sometimes change their layout and the program needs a small adjustment.
