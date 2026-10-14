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

If you paste a series page instead of a chapter page, it asks whether to download all chapters.

## If no images are found

Send the link you used to your developer. Sites sometimes change their layout and the program needs a small adjustment.
