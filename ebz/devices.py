"""Every device EBZ CNVRTR can fit pages to.

The sizes are the screen sizes in pixels (portrait). The e-reader sizes are the same ones
Comic Downloader uses (proven on your Kobo); tablet and phone sizes were added.
To add a device later, add one line to DEVICES - nothing else needs changing.

gray = True makes black-and-white pages (smaller files, same look on a grey screen).
kind decides which extra file the device needs and the copy-over steps."""

# key: (label shown in the window, (width, height), gray, output folder name, kind)
DEVICES = {
    # --- Kobo ---
    "kobo_clara": ("Kobo Clara - HD, 2E, BW, Colour", (1072, 1448), False, "Kobo Clara", "kobo"),
    "kobo_libra": ("Kobo Libra 2 / Libra Colour", (1264, 1680), False, "Kobo Libra", "kobo"),
    "kobo_sage": ("Kobo Sage / Forma", (1440, 1920), False, "Kobo Sage", "kobo"),
    "kobo_elipsa": ("Kobo Elipsa / Elipsa 2E", (1404, 1872), False, "Kobo Elipsa", "kobo"),
    # --- Kindle ---
    "kindle_basic": ("Kindle - basic 6 inch, 2022 or 2024", (1072, 1448), True, "Kindle Basic", "kindle"),
    "kindle_pw6": ("Kindle Paperwhite - 6 inch, 2015 to 2020", (1072, 1448), True,
                   "Kindle Paperwhite 6in", "kindle"),
    "kindle_pw68": ("Kindle Paperwhite - 6.8 inch, 2021", (1236, 1648), True,
                    "Kindle Paperwhite 6.8in", "kindle"),
    "kindle_pw7": ("Kindle Paperwhite - 7 inch, 2024", (1264, 1680), True,
                   "Kindle Paperwhite 7in", "kindle"),
    "kindle_color": ("Kindle Colorsoft - color", (1264, 1680), False, "Kindle Colorsoft", "kindle"),
    "kindle_scribe": ("Kindle Scribe - 10 inch", (1860, 2480), True, "Kindle Scribe", "kindle"),
    # --- PocketBook ---
    "pocketbook_6": ("PocketBook - 6 inch (Touch HD, Verse Pro)", (1072, 1448), False,
                     "PocketBook 6in", "pocketbook"),
    "pocketbook_7": ("PocketBook - 7 inch (Era)", (1264, 1680), False, "PocketBook 7in", "pocketbook"),
    "pocketbook_78": ("PocketBook - 7.8 inch (InkPad)", (1404, 1872), False,
                      "PocketBook 7.8in", "pocketbook"),
    # --- Boox ---
    "boox_6": ("Boox - 6 inch (Go 6)", (1072, 1448), False, "Boox 6in", "boox"),
    "boox_7": ("Boox - 7 inch (Page, Leaf)", (1264, 1680), False, "Boox 7in", "boox"),
    "boox_note": ("Boox - 10.3 inch (Note Air, Tab Ultra)", (1404, 1872), False,
                  "Boox Note Air", "boox"),
    "boox_103": ("Boox - 10.3 inch (Go 10.3)", (1860, 2480), False, "Boox Go 10.3", "boox"),
    # --- reMarkable ---
    "remarkable": ("reMarkable 2", (1404, 1872), True, "reMarkable 2", "remarkable"),
    # --- Tablets and phones ---
    "ipad_mini": ("iPad mini (6th and 7th gen)", (1488, 2266), False, "iPad mini", "tablet"),
    "ipad": ("iPad / iPad Air 11 inch", (1640, 2360), False, "iPad", "tablet"),
    "ipad_pro11": ("iPad Pro 11 inch (2024)", (1668, 2420), False, "iPad Pro 11in", "tablet"),
    "ipad_13": ("iPad Air 13 / iPad Pro 12.9 inch", (2048, 2732), False, "iPad 13in", "tablet"),
    "ipad_pro13": ("iPad Pro 13 inch (2024)", (2064, 2752), False, "iPad Pro 13in", "tablet"),
    "android_tablet": ("Android tablet (general)", (1600, 2400), False, "Android Tablet", "tablet"),
    "phone": ("Phone - iPhone or Android (general)", (1170, 2532), False, "Phone", "tablet"),
    # --- your own size ---
    "custom": ("Custom size - type your own", (1072, 1448), False, "Custom Size", "custom"),
}

DEVICE_KEYS = list(DEVICES)

# Some devices cannot open CBZ or EPUB copied over a cable, so they also get a PDF.
NEEDS_PDF = {"kindle", "remarkable"}


def info(key, custom=None):
    """Settings for one device as a dict. For 'custom', pass {'width','height','gray'}."""
    label, size, gray, folder, kind = DEVICES[key]
    if key == "custom":
        c = custom or {}
        size = (int(c.get("width", size[0])), int(c.get("height", size[1])))
        gray = bool(c.get("gray", gray))
        folder = f"Custom {size[0]}x{size[1]}"
    return {"key": key, "label": label, "size": size, "gray": gray, "folder": folder, "kind": kind}


def label_with_size(key):
    label, (w, h) = DEVICES[key][0], DEVICES[key][1]
    return label if key == "custom" else f"{label}   ({w} x {h})"


def next_steps(kind, folder):
    """Plain copy-over steps for the log."""
    f = f"the folder '{folder}'"
    if kind == "kobo":
        return (f"Kobo: plug it in with its USB cable, tap Connect, then drag the .cbz or .epub "
                f"files from {f} onto the drive named KOBOeReader. Eject it.")
    if kind == "kindle":
        return (f"Kindle: plug it in with its USB cable, open the drive named Kindle, open its "
                f"'documents' folder and drag the .pdf files from {f} into it. A Kindle cannot open "
                ".cbz or .epub files copied over a cable; those are for your other readers.")
    if kind == "pocketbook":
        return (f"PocketBook: plug it in with its USB cable (choose 'Connect to PC'), then drag the "
                f"files from {f} into its 'Books' folder. Eject it.")
    if kind == "boox":
        return (f"Boox: use its Wi-Fi file transfer (BooxDrop on many models) and drag the files "
                f"from {f} onto the page it shows. A USB cable also works; on a Mac you may need the "
                "free app OpenMTP.")
    if kind == "remarkable":
        return (f"reMarkable: turn on the USB web interface (Settings, then Storage), plug it in, "
                f"open http://10.11.99.1 in your browser and drag the .pdf or .epub files from {f} onto it.")
    if kind == "tablet":
        return (f"Tablet or phone: send the files from {f} with AirDrop, a USB cable or a cloud drive. "
                "Apple Books opens the .epub; a comic app (for example Panels or Chunky on iPad, "
                "or any CBZ reader on Android) opens the .cbz.")
    return (f"Copy the files from {f} onto your device the way it usually receives files.")
