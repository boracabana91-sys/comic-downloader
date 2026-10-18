# EBZ CNVRTR

Turns pictures, PDFs and comics into **CBZ** and **EPUB** files whose pages are fitted snugly to
your device's screen (Kobo, Kindle, PocketBook, Boox, reMarkable, iPad, Android tablet, phone, or a size you type).

The version number is shown in the window title and at the top right of the window.

## What you can drop in
- Pictures: JPG, PNG, WebP, GIF, BMP, TIFF, AVIF, HEIC (iPhone photos)
- PDF files (every page becomes a picture)
- CBZ / ZIP comic files (re-fitted for your device)
- Folders: the pictures in a folder make one book, named after the folder. Each PDF or CBZ inside is
  its own book, and sub-folders (Chapter 1, Chapter 2 ...) each become their own book.
- Pages go in name order, with 2 before 10.

## What you get
`Save to` folder → one folder per device → `Book name.cbz`, `Book name.epub`
(and `Book name.pdf` for Kindle and reMarkable, which cannot open CBZ/EPUB copied over a cable).

## How it fits pages (from Comic Series Downloader series-v5-test6)
- Every page is made at the exact screen size of the device, so the reader has nothing to zoom or crop.
- Webtoon strips: slices are joined, then cut only at empty gaps between panels; whole scenes are put
  on each screen, never zoomed in, on the strip's own background colour.
- Normal pages and photos: each one fitted whole on its own screen.
- New in EBZ CNVRTR: separate photos are never joined (two pictures are joined only when they are the
  same width and the picture carries on across the cut). Empty screens at the start or end are dropped.
- The log reports "N of N screens are clean" after each book.

## Code
- `version.py` the version number (change it for every update)
- `devices.py` the device list (add one line to add a device)
- `fitpage.py`, `pagecore.py` the proven engine, copied unchanged
- `converter.py` what was dropped → books → pages → files
- `ebz_app.py` the window
- `test_ebz.py`, `test_ebz_window.py` tests, run by the automatic build
- Build: `.github/workflows/build-ebz.yml`, releases are tagged `ebz-vNN`
