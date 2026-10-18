# EBZ CNVRBINE (was EBZ CNVRTR)

Turns pictures, PDFs and comics into **CBZ** and **EPUB** files whose pages are fitted snugly to
your device's screen (Kobo, Kindle, PocketBook, Boox, reMarkable, iPad, Android tablet, phone, or a size you type),
and joins several books into one.

The version number is shown in the window title and at the top right of the window.

## Updating
1. Click **Get updates** (top right) and download the newest `EBZ-CNVRBINE-NN-Mac.zip` or `-Windows.exe`.
2. Drop it on the small **Drop an update here** box (or anywhere in the window).
3. If the program is busy, it asks to stop first (finished files are kept).
4. It checks the file really is EBZ CNVRBINE and which version it is, asks you, then swaps itself and reopens.
   Mac: the old app goes to the Trash. Windows: the old file is removed the next time the program starts.
Your settings (devices, output folder, cover) are kept.

## Two tabs
- **Convert**: each folder, PDF, CBZ or EPUB you drop becomes its own book, fitted to every ticked device.
- **Combine**: the books you drop are joined into ONE book in the order of the list (Move up / Move down /
  Sort 1, 2, 3). The list is put in chapter order (1, 2, 3 ... 10) by default. The name is made for you ("Series Chapter 001-006") and can be changed.
  - "Also fit the pages for my devices" ticked: one joined book per ticked device, in that device's folder.
  - Unticked: the pages are kept exactly as they are, in the `Combined` folder.
  - The joined EPUB has a contents list with one entry per original book.
  - Your original files are never changed or deleted.

## What you can drop in
- Pictures: JPG, PNG, WebP, GIF, BMP, TIFF, AVIF, HEIC (iPhone photos)
- PDF files (every page becomes a picture)
- CBZ / ZIP comic files
- EPUB files from **any** program: the program opens the EPUB, takes its pages out in reading order
  (pictures, pages drawn as SVG, pictures stored inside the pages), fits them and rebuilds a clean EPUB.
  - Refused with a plain message: text books (novels, magazines - their words would be lost),
    copy-protected (DRM) books from shops, and damaged files.
- Folders: the pictures in a folder make one book, named after the folder. Each PDF, CBZ or EPUB inside is
  its own book, and sub-folders (Chapter 1, Chapter 2 ...) each become their own book.
- Pages go in name order, with 2 before 10.

## Cover
- No cover / My cover picture (drop it on the cover box) / Each book's first page.
- Chapter number on the cover, taken from the book's name ("Chapter 12" gives #12, a joined book gives #1-6),
  with a choice of corner, size and dark or white numbers. The cover box shows how it will look.

## Where the files go
The bottom of the window always shows the output folder, with **Change output folder**, **Open output folder**
and **Open the folder just made**. Inside it: one folder per device → `Book name.cbz`, `Book name.epub`
(and `Book name.pdf` for Kindle and reMarkable, which cannot open CBZ/EPUB copied over a cable).

## How it fits pages (from Comic Series Downloader series-v5-test6)
- Every page is made at the exact screen size of the device, so the reader has nothing to zoom or crop.
- Webtoon strips: slices are joined, then cut only at empty gaps between panels; whole scenes are put
  on each screen, never zoomed in, on the strip's own background colour.
- Normal pages and photos: each one fitted whole on its own screen.
- Separate photos are never joined (two pictures are joined only when they are the same width and the
  picture carries on across the cut). Empty screens at the start or end are dropped.
- Pages already made for exactly this screen (an EPUB made by EBZ CNVRTR for the same device) are kept as they are.
- The log reports "N of N strip screens are clean" for webtoon strips.

## Code
- `version.py` the version number (change it for every update)
- `devices.py` the device list (add one line to add a device)
- `fitpage.py`, `pagecore.py` the proven engine, copied unchanged
- `converter.py` what was dropped → books → pages → files; combining
- `bookfiles.py` reading EPUBs from any program; writing CBZ, EPUB (with contents) and PDF
- `coverart.py` cover and chapter number
- `ebz_app.py` the window
- `updater.py` updating by dropping the new download
- `test_ebz.py`, `test_v02.py`, `test_updater.py`, `test_ebz_window.py` tests, run by the automatic build
- Build: `.github/workflows/build-ebz.yml`, releases are tagged `ebz-vNN`
