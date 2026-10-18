"""EBZ CNVRBINE (was EBZ CNVRTR) - the window.

Two tabs:
  Convert - drop pictures, PDFs, CBZ, EPUB files or folders; each becomes its own book,
            fitted snugly to every ticked device.
  Combine - drop several books (EPUB, CBZ, PDF, folders); they are joined into one book,
            optionally fitted to the ticked devices as well.
Devices, file types, cover and the output folder are shared by both tabs."""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import converter  # noqa: E402
import coverart  # noqa: E402
import devices  # noqa: E402
import pagecore  # noqa: E402
import updater  # noqa: E402
import version  # noqa: E402

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".ebz_cnvrtr.json")   # kept: settings carry over
_GEO = re.compile(r"^(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?$")
CONVERT_TEXT = "Drop pictures, PDFs, CBZ, EPUB files or folders here\nor click to choose files"
COMBINE_TEXT = "Drop the books to join here (EPUB, CBZ, PDF or folders)\nor click to choose files"
COVER_TEXT = "Drop your cover\npicture here\n(or click to choose)"
PICK_TYPES = [("Pictures, PDF, CBZ and EPUB", " ".join("*" + e for e in converter.ALL_EXT)),
              ("All files", "*")]
COVER_TYPES = [("Pictures", "*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff *.heic")]


def load_settings(path=None):
    try:
        with open(path or SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data, path=None):
    try:
        with open(path or SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def fit_geometry(saved, screen_w, screen_h, default=(820, 920), minimum=(700, 560)):
    """Copied from Comic Series Downloader: the remembered size if it still fits this screen."""
    max_h = max(minimum[1], screen_h - 90)
    m = _GEO.match(saved or "")
    if not m:
        return f"{min(default[0], screen_w)}x{min(default[1], max_h)}"
    w = min(max(int(m.group(1)), minimum[0]), screen_w)
    h = min(max(int(m.group(2)), minimum[1]), max_h)
    if m.group(3) is not None:
        x, y = int(m.group(3)), int(m.group(4))
        if -w + 120 < x < screen_w - 120 and 0 <= y < screen_h - 120:
            return f"{w}x{h}{x:+d}{y:+d}"
    return f"{w}x{h}"


def default_out_dir():
    desk = os.path.join(os.path.expanduser("~"), "Desktop")
    return os.path.join(desk if os.path.isdir(desk) else os.path.expanduser("~"), "EBZ CNVRBINE")


def open_in_finder(path):
    os.makedirs(path, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # noqa
    else:
        subprocess.Popen(["xdg-open", path])


def looks_like_update(path):
    """The program's own download (EBZ-CNVRBINE-03-Mac.zip, ...-Windows.exe or the app)."""
    n = re.split(r"[\\/]", path.rstrip("/\\"))[-1].lower().replace(" ", "-")
    return n.startswith(("ebz-cnvrbine", "ebz-cnvrtr")) and n.endswith((".zip", ".exe", ".app"))


class DropBox:
    """A dashed box you can drop files on or click."""

    def __init__(self, parent, text, on_click, bg=None, height=90, font=("Helvetica", 13), width=None):
        self.text = text
        self.font = font
        self.hot = False
        self.c = tk.Canvas(parent, height=height, highlightthickness=0, cursor="hand2",
                           **({"bg": bg} if bg else {}), **({"width": width} if width else {}))
        self.c.bind("<Configure>", lambda e: self.draw())
        self.c.bind("<Button-1>", lambda e: on_click())

    def draw(self):
        c = self.c
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        color = "#2a7de1" if self.hot else "#8a8a8a"
        c.create_rectangle(3, 3, w - 3, h - 3, outline=color, width=2, dash=(8, 5),
                           fill="#e8f1fc" if self.hot else "")
        c.create_text(w // 2, h // 2, text=self.text, fill="#333", justify="center",
                      font=self.font)

    def set_hot(self, on):
        self.hot = on
        self.draw()


class BookList:
    """A list of books with its own drop box and buttons (one per tab)."""

    def __init__(self, app, parent, drop_text, ordered=False):
        self.app = app
        self.books = []
        self.frame = ttk.Frame(parent)
        self.zone = DropBox(self.frame, drop_text, self.add_files, app.bgc)
        self.zone.c.pack(fill="x", pady=(10, 4))
        brow = ttk.Frame(self.frame)
        brow.pack(fill="x")
        ttk.Button(brow, text="Add files...", command=self.add_files).pack(side="left")
        ttk.Button(brow, text="Add a folder...", command=self.add_folder).pack(side="left", padx=8)
        self.count = tk.StringVar()
        ttk.Label(self.frame, textvariable=self.count, font=("Helvetica", 12, "bold")).pack(
            anchor="w", pady=(10, 0))
        lrow = ttk.Frame(self.frame)
        lrow.pack(fill="x", pady=(4, 0))
        self.lb = tk.Listbox(lrow, selectmode="extended", height=5, exportselection=False)
        sb = ttk.Scrollbar(lrow, command=self.lb.yview)
        self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="x", expand=True)
        sb.pack(side="left", fill="y")
        rrow = ttk.Frame(self.frame)
        rrow.pack(fill="x", pady=(4, 0))
        if ordered:
            ttk.Button(rrow, text="Move up", command=lambda: self.move(-1)).pack(side="left")
            ttk.Button(rrow, text="Move down", command=lambda: self.move(1)).pack(side="left", padx=(6, 0))
            ttk.Button(rrow, text="Sort 1, 2, 3...", command=self.sort).pack(side="left", padx=(6, 12))
        ttk.Button(rrow, text="Remove selected", command=self.remove_selected).pack(side="left")
        ttk.Button(rrow, text="Clear all", command=self.clear).pack(side="left", padx=6)
        self.on_change = None
        self.update()

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Choose pictures, PDF, CBZ or EPUB files",
                                            filetypes=PICK_TYPES)
        if paths:
            self.add_paths(list(paths))

    def add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder")
        if d:
            self.add_paths([d])

    def add_paths(self, paths):
        books, skipped = converter.collect(paths)
        known = {(b.kind, tuple(b.items)) for b in self.books}
        new = [b for b in books if (b.kind, tuple(b.items)) not in known]
        self.books.extend(new)
        if new:
            self.sort_books()   # Chapter 1, 2, 3 ... 10 by default, whatever order they were dropped in
        self.update()
        say = self.app.say
        if new:
            say(f"Added {len(new)} book{'s' if len(new) != 1 else ''}.")
        if skipped:
            say(f"Skipped {len(skipped)} item(s) that are not pictures, PDF, CBZ, EPUB or folders: "
                + ", ".join(os.path.basename(s) for s in skipped[:4]) + (" ..." if len(skipped) > 4 else ""))
        if not new and not skipped:
            say("Nothing new to add (nothing usable found, or already in the list).")
        return new

    def update(self):
        sel = set(self.lb.curselection())
        self.lb.delete(0, "end")
        for i, b in enumerate(self.books):
            self.lb.insert("end", f"{i + 1}.  {b.describe()}")
            if i in sel:
                self.lb.selection_set(i)
        n = len(self.books)
        self.count.set(f"Books: {n}" if n else "Books: none yet - drop something above")
        if self.on_change:
            self.on_change()

    def move(self, step):
        sel = list(self.lb.curselection())
        if not sel:
            return
        order = sel if step < 0 else list(reversed(sel))
        for i in order:
            j = i + step
            if 0 <= j < len(self.books) and j not in sel:
                self.books[i], self.books[j] = self.books[j], self.books[i]
                sel[sel.index(i)] = j
        self.lb.selection_clear(0, "end")
        self.update()
        for i in sel:
            self.lb.selection_set(i)
        self.lb.see(sel[0])

    def sort_books(self):
        self.books.sort(key=lambda b: converter.natural_key(b.name))

    def sort(self):
        self.sort_books()
        self.update()

    def remove_selected(self):
        for i in reversed(self.lb.curselection()):
            del self.books[i]
        self.lb.selection_clear(0, "end")
        self.update()

    def clear(self):
        self.books = []
        self.update()


class App:
    def __init__(self, root, dnd=False, settings_path=None):
        self.root = root
        self.settings_path = settings_path
        st = self.settings = load_settings(settings_path)
        root.title(version.full_name())
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(fit_geometry(st.get("geometry"), sw, sh))
        root.minsize(700, 560)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Configure>", self._on_configure)
        self._save_job = None
        self._wraps = []
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        self.last_folder = None
        self.cover_path = None
        self._photo = None
        px = 14
        try:
            self.bgc = ttk.Style().lookup("TFrame", "background") or None
        except Exception:
            self.bgc = None

        # ----- header with the version -----
        head = ttk.Frame(root)
        head.pack(fill="x", padx=px, pady=(12, 0))
        self.title_label = ttk.Label(head, text=version.full_name(), font=("Helvetica", 20, "bold"))
        self.title_label.pack(side="left")
        upd = ttk.Frame(head)
        upd.pack(side="right")
        self.upd_zone = DropBox(upd, "Drop an update here", self.choose_update, self.bgc, height=34,
                                font=("Helvetica", 10), width=150)
        self.upd_zone.c.pack(side="left")
        vcol = ttk.Frame(upd)
        vcol.pack(side="left", padx=(8, 0))
        self.version_label = ttk.Label(vcol, text=f"Version {version.VERSION}", foreground="#666")
        self.version_label.pack(anchor="e")
        get = ttk.Label(vcol, text="Get updates", foreground="#1a5fb4", cursor="hand2")
        get.pack(anchor="e")
        get.bind("<Button-1>", lambda e: self.get_updates())
        ttk.Label(root, text="Turn pictures, PDFs and comics into CBZ and EPUB files that fit "
                  "your device - or join several books into one.", foreground="#555", wraplength=760,
                  justify="left").pack(anchor="w", padx=px)

        # ----- bottom part first, so the buttons, output folder and log are never cut off -----
        self.bottom = ttk.Frame(root)
        self.bottom.pack(side="bottom", fill="x")
        orow = ttk.Frame(self.bottom)
        orow.pack(fill="x", padx=px, pady=(8, 0))
        ttk.Label(orow, text="Your files are saved in:", font=("Helvetica", 12, "bold")).pack(side="left")
        self.out = tk.StringVar(value=st.get("out_dir") or default_out_dir())
        self.out_label = ttk.Label(self.bottom, textvariable=self.out, foreground="#1a5fb4",
                                   cursor="hand2", wraplength=760, justify="left")
        self.out_label.pack(anchor="w", padx=px)
        self.out_label.bind("<Button-1>", lambda e: self.open_folder())
        orow2 = ttk.Frame(self.bottom)
        orow2.pack(fill="x", padx=px, pady=(4, 0))
        ttk.Button(orow2, text="Change output folder...", command=self.choose_out).pack(side="left")
        ttk.Button(orow2, text="Open output folder", command=self.open_folder).pack(side="left", padx=8)
        self.btn_last = ttk.Button(orow2, text="Open the folder just made", command=self.open_last,
                                   state="disabled")
        self.btn_last.pack(side="left")
        ttk.Separator(self.bottom).pack(fill="x", padx=px, pady=8)
        btns = ttk.Frame(self.bottom)
        btns.pack(fill="x", padx=px)
        self.btn_go = ttk.Button(btns, text="Convert", command=self.start)
        self.btn_go.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=8)
        self.bar = ttk.Progressbar(self.bottom, mode="determinate", maximum=1000)
        self.bar.pack(fill="x", padx=px, pady=(8, 2))
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self.bottom, textvariable=self.status).pack(anchor="w", padx=px)
        self.log = tk.Text(self.bottom, height=5, state="disabled", wrap="word")
        self.log.pack(fill="x", padx=px, pady=(6, 14))

        # ----- the middle scrolls (same way as Comic Series Downloader) -----
        canvas = tk.Canvas(root, highlightthickness=0, borderwidth=0,
                           **({"bg": self.bgc} if self.bgc else {}))
        vsb = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        main = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=main, anchor="nw")
        main.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))

        def wheel(e):
            if isinstance(e.widget, (tk.Listbox, tk.Text)):
                return
            canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        root.bind_all("<MouseWheel>", wheel)
        self.canvas = canvas
        self.main = main

        # ----- the two tabs -----
        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill="x", padx=px, pady=(10, 0))
        t1 = ttk.Frame(self.tabs, padding=10)
        t2 = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(t1, text="   Convert   ")
        self.tabs.add(t2, text="   Combine   ")
        ttk.Label(t1, text="Each folder, PDF, CBZ or EPUB becomes its own book, fitted to every "
                  "device you tick below.", foreground="#555", wraplength=700,
                  justify="left").pack(anchor="w")
        self.conv = BookList(self, t1, CONVERT_TEXT)
        self.conv.frame.pack(fill="x")
        ttk.Label(t2, text="The books are joined into ONE book, in the order of the list: Chapter 1, 2, 3... "
                  "(change it with Move up / Move down). EPUBs from other programs are opened, fitted and joined "
                  "automatically. Your original files are never changed.", foreground="#555",
                  wraplength=700, justify="left").pack(anchor="w")
        self.comb = BookList(self, t2, COMBINE_TEXT, ordered=True)
        self.comb.frame.pack(fill="x")
        nrow = ttk.Frame(t2)
        nrow.pack(fill="x", pady=(10, 0))
        ttk.Label(nrow, text="Name of the joined book:").pack(side="left")
        self.cname = tk.StringVar()
        self.cname_entry = ttk.Entry(nrow, textvariable=self.cname)
        self.cname_entry.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(nrow, text="Auto name", command=self.auto_name).pack(side="left")
        self.cname_auto = True
        self.cname_entry.bind("<Key>", lambda e: setattr(self, "cname_auto", False))
        self.comb.on_change = self._comb_changed
        self.cfit = tk.BooleanVar(value=st.get("combine_fit", True))
        ttk.Checkbutton(t2, text="Also fit the pages for my devices (ticked below)",
                        variable=self.cfit, command=self._fit_note).pack(anchor="w", pady=(8, 0))
        self.cfit_note = tk.StringVar()
        ttk.Label(t2, textvariable=self.cfit_note, foreground="#555", wraplength=700,
                  justify="left").pack(anchor="w")
        self._fit_note()
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())

        # ----- devices -----
        self.dev_count = tk.StringVar()
        ttk.Label(main, textvariable=self.dev_count, font=("Helvetica", 12, "bold")).pack(
            anchor="w", padx=px, pady=(14, 0))
        ttk.Label(main, text="Click a device to tick or untick it. Each one gets its own folder.",
                  foreground="#555").pack(anchor="w", padx=px)
        drow = ttk.Frame(main)
        drow.pack(fill="x", padx=px, pady=(4, 0))
        self.dev_lb = tk.Listbox(drow, selectmode="multiple", height=8, exportselection=False)
        dsb = ttk.Scrollbar(drow, command=self.dev_lb.yview)
        self.dev_lb.config(yscrollcommand=dsb.set)
        self.dev_lb.pack(side="left", fill="x", expand=True)
        dsb.pack(side="left", fill="y")
        for k in devices.DEVICE_KEYS:
            self.dev_lb.insert("end", devices.label_with_size(k))
        saved = [k for k in st.get("devices", ["kobo_clara"]) if k in devices.DEVICES]
        for k in saved or ["kobo_clara"]:
            self.dev_lb.selection_set(devices.DEVICE_KEYS.index(k))
        self.dev_lb.bind("<<ListboxSelect>>", lambda e: self.update_devices())
        c = st.get("custom", {})
        self.crow = ttk.Frame(main)
        self.crow.pack(fill="x", padx=px, pady=(4, 0))
        ttk.Label(self.crow, text="Custom size:").pack(side="left")
        self.cw = tk.StringVar(value=str(c.get("width", 1072)))
        self.ch = tk.StringVar(value=str(c.get("height", 1448)))
        self.cgray = tk.BooleanVar(value=bool(c.get("gray", False)))
        self.cw_box = ttk.Entry(self.crow, textvariable=self.cw, width=6)
        self.cw_box.pack(side="left", padx=(6, 2))
        ttk.Label(self.crow, text="wide x").pack(side="left")
        self.ch_box = ttk.Entry(self.crow, textvariable=self.ch, width=6)
        self.ch_box.pack(side="left", padx=(6, 2))
        ttk.Label(self.crow, text="tall (pixels)").pack(side="left")
        self.cg_box = ttk.Checkbutton(self.crow, text="Black and white", variable=self.cgray)
        self.cg_box.pack(side="left", padx=(12, 0))

        # ----- file types -----
        ttk.Label(main, text="Files to make", font=("Helvetica", 12, "bold")).pack(
            anchor="w", padx=px, pady=(14, 0))
        frow = ttk.Frame(main)
        frow.pack(fill="x", padx=px)
        fm = st.get("formats", [".cbz", ".epub"])
        self.fmt = {e: tk.BooleanVar(value=e in fm) for e in converter.FORMATS}
        for e in converter.FORMATS:
            ttk.Checkbutton(frow, text=e[1:].upper(), variable=self.fmt[e]).pack(side="left", padx=(0, 14))
        ttk.Label(main, text="Kindle and reMarkable always get a PDF too, because they cannot open "
                  "CBZ or EPUB files copied over a cable.", foreground="#555",
                  wraplength=700, justify="left").pack(anchor="w", padx=px)

        # ----- cover -----
        cv = st.get("cover", {})
        ttk.Label(main, text="Cover", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=px, pady=(14, 0))
        crow = ttk.Frame(main)
        crow.pack(fill="x", padx=px, pady=(4, 12))
        self.cover_zone = tk.Label(crow, text=COVER_TEXT, relief="groove", borderwidth=2, width=18,
                                   height=7, cursor="hand2", justify="center")
        self.cover_zone.pack(side="left", anchor="n")
        self.cover_zone.bind("<Button-1>", lambda e: self.choose_cover())
        side = ttk.Frame(crow)
        side.pack(side="left", padx=12, anchor="n", fill="x", expand=True)
        self.cover_mode = tk.StringVar(value=cv.get("mode", "none"))
        mrow = ttk.Frame(side)
        mrow.pack(anchor="w")
        for label, key in coverart.COVER_MODES.items():
            ttk.Radiobutton(mrow, text=label, value=key, variable=self.cover_mode,
                            command=self.update_cover).pack(side="left", padx=(0, 10))
        b2 = ttk.Frame(side)
        b2.pack(anchor="w", pady=(4, 0))
        ttk.Button(b2, text="Choose cover picture...", command=self.choose_cover).pack(side="left")
        ttk.Button(b2, text="Clear cover", command=self.clear_cover).pack(side="left", padx=6)
        self.badge = tk.BooleanVar(value=cv.get("number", True))
        ttk.Checkbutton(side, text="Put the chapter number on the cover",
                        variable=self.badge, command=self.update_cover).pack(anchor="w", pady=(6, 0))
        ttk.Label(side, text="Taken from the book's name: 'Chapter 12' gives #12, a joined book "
                  "gives #1-6.", foreground="#555", wraplength=520, justify="left").pack(anchor="w")
        orow3 = ttk.Frame(side)
        orow3.pack(anchor="w", pady=(4, 0))
        self.corner = tk.StringVar(value=self._label_of(coverart.CORNERS, cv.get("corner", "ur")))
        self.bsize = tk.StringVar(value=self._label_of(coverart.SIZES, cv.get("size", 0.07)))
        self.bstyle = tk.StringVar(value=self._label_of(coverart.STYLES, cv.get("style", "dark")))
        for lab, var, opts, wd in (("Corner", self.corner, coverart.CORNERS, 12),
                                   ("Size", self.bsize, coverart.SIZES, 8),
                                   ("Look", self.bstyle, coverart.STYLES, 22)):
            ttk.Label(orow3, text=lab + ":").pack(side="left")
            cb = ttk.Combobox(orow3, textvariable=var, values=list(opts), state="readonly", width=wd)
            cb.pack(side="left", padx=(4, 12))
            cb.bind("<<ComboboxSelected>>", lambda e: self.update_cover())
        self.cover_note = tk.StringVar()
        ttk.Label(side, textvariable=self.cover_note, foreground="#555", wraplength=520,
                  justify="left").pack(anchor="w", pady=(6, 0))
        if cv.get("path") and os.path.isfile(cv["path"]):
            self.set_cover(cv["path"], quiet=True)
        if st.get("tab") == 1:
            self.tabs.select(1)

        # ----- drag and drop: each tab's box, the cover box and the whole window -----
        self.drop_on = False
        if dnd:
            try:
                from tkinterdnd2 import DND_FILES
                lists = (self.conv, self.comb)
                targets = [root, canvas, main, self.tabs, self.log, self.dev_lb]
                for bl in lists:
                    targets += [bl.zone.c, bl.lb, bl.frame]
                for w in targets:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self.on_drop)
                    w.dnd_bind("<<DropEnter>>", lambda e: self._hot(True))
                    w.dnd_bind("<<DropLeave>>", lambda e: self._hot(False))
                self.cover_zone.drop_target_register(DND_FILES)
                self.cover_zone.dnd_bind("<<Drop>>", self.on_cover_drop)
                self.upd_zone.c.drop_target_register(DND_FILES)
                self.upd_zone.c.dnd_bind("<<Drop>>", self.on_update_drop)
                self.upd_zone.c.dnd_bind("<<DropEnter>>", lambda e: self.upd_zone.set_hot(True))
                self.upd_zone.c.dnd_bind("<<DropLeave>>", lambda e: self.upd_zone.set_hot(False))
                self.drop_on = True
            except Exception:
                pass
        if not self.drop_on:
            self.say("Drag and drop is not available on this computer. Use Add files or Add a folder.")
        self.update_devices()
        self.update_cover()
        self._tab_changed()
        self._collect_wraps(root)
        self._updating = False
        root.bind("<Destroy>", self._on_destroy, add="+")
        self._pump_job = root.after(100, self.pump)

    # ----- small helpers -----
    @staticmethod
    def _label_of(opts, value):
        for k, v in opts.items():
            if v == value:
                return k
        return next(iter(opts))

    def current(self):
        """The book list of the tab that is showing."""
        return self.comb if self.tabs.index("current") == 1 else self.conv

    def combining(self):
        return self.tabs.index("current") == 1

    def _tab_changed(self):
        self.btn_go.config(text="Combine into one book" if self.combining() else "Convert")

    def _hot(self, on):
        self.current().zone.set_hot(on)

    def _comb_changed(self):
        if self.cname_auto:
            self.auto_name()

    def auto_name(self):
        self.cname_auto = True
        self.cname.set(converter.combined_name([b.name for b in self.comb.books])
                       if self.comb.books else "")

    def _fit_note(self):
        if self.cfit.get():
            self.cfit_note.set("One joined book per ticked device, fitted to its screen, saved in "
                               "that device's folder.")
        else:
            self.cfit_note.set("One joined book with the pages kept exactly as they are, saved in "
                               "the 'Combined' folder.")

    # ----- dropping -----
    def on_drop(self, event):
        self._hot(False)
        items = list(self.root.tk.splitlist(event.data or ""))
        upd = [p for p in items if looks_like_update(p)]
        if upd:   # the new program dropped in the wrong box: it is still an update
            self.start_update(upd[0])
            items = [p for p in items if p not in upd]
            if not items:
                return getattr(event, "action", None)
        self.current().add_paths(items)
        return getattr(event, "action", None)

    def on_cover_drop(self, event):
        items = list(self.root.tk.splitlist(event.data or ""))
        if items:
            self.set_cover(items[0])
        return getattr(event, "action", None)

    # ----- text that wraps to the window's width -----
    def _collect_wraps(self, w):
        for c in w.winfo_children():
            if isinstance(c, ttk.Label):
                try:
                    wl = int(str(c.cget("wraplength")) or 0)
                except ValueError:
                    wl = 0
                if wl > 0:
                    self._wraps.append((c, 760 - wl))   # how much narrower than the window it was
            self._collect_wraps(c)

    def _rewrap(self, width):
        for lab, offset in self._wraps:
            try:
                lab.config(wraplength=max(220, width - 60 - offset))
            except tk.TclError:
                pass

    # ----- updating the program -----
    def get_updates(self):
        import webbrowser
        webbrowser.open(updater.RELEASES)
        self.say("Download the newest EBZ-CNVRBINE file for your computer, then drop it on the "
                 "'Drop an update here' box at the top right.")

    def choose_update(self):
        path = filedialog.askopenfilename(
            title="Choose the downloaded update (Mac: the .zip, Windows: the .exe)",
            filetypes=[("Program update", "*.zip *.exe *.app"), ("All files", "*")])
        if path:
            self.start_update(path)

    def on_update_drop(self, event):
        self.upd_zone.set_hot(False)
        items = list(self.root.tk.splitlist(event.data or ""))
        if items:
            self.start_update(items[0])
        return getattr(event, "action", None)

    def start_update(self, path):
        if self._updating:
            return
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno(version.full_name(), "The program is still working.\n\n"
                                       "Stop what it is doing and update now? Files already "
                                       "finished are kept.", parent=self.root):
                return
            self.on_stop()
        self._updating = True
        self.q.put(("status", "Getting the update ready..."))
        self._wait_then_update(path)

    def _wait_then_update(self, path):
        if self.worker is not None and self.worker.is_alive():   # the stop takes effect after a page
            self.root.after(200, lambda: self._wait_then_update(path))
            return
        self.btn_go.config(state="disabled")
        self.say(f"Checking the update: {os.path.basename(path.rstrip('/'))}")

        def check():
            import tempfile
            try:
                info = updater.prepare(path, tempfile.mkdtemp(prefix="ebz_update_"))
                self.q.put(("update_ready", info))
            except updater.UpdateError as e:
                self.q.put(("update_failed", str(e)))
            except Exception as e:
                self.q.put(("update_failed", f"something went wrong ({e})."))
        threading.Thread(target=check, daemon=True).start()

    def _update_ready(self, info):
        have = version.VERSION
        new = f"{info['name']} {info['version']}"
        if info["newer"]:
            msg = f"Install {new}?\n\nYou have version {have}. The program will close and open the new version."
        else:
            msg = (f"The file you dropped is {new}, and you already have version {have}.\n\n"
                   "Install it anyway?")
        if not messagebox.askyesno(version.full_name(), msg, parent=self.root):
            self._update_done("Update cancelled.")
            return
        try:
            dest = updater.install(info["kind"], info["current"], info["candidate"])
        except updater.UpdateError as e:
            self._update_done(f"The update could not be installed: {e}")
            return
        self.say(f"Installed {new}. Opening it...")
        self.save_all()
        try:
            updater.launch(info["kind"], dest)
        except Exception as e:
            self._update_done(f"{new} is installed but could not be opened ({e}). Open it yourself.")
            return
        self.root.after(800, self.on_close)

    def _update_done(self, msg):
        self._updating = False
        self.say(msg)
        self.status.set(msg if len(msg) < 90 else "See the message below.")
        self.btn_go.config(state="normal")

    # ----- cover -----
    def choose_cover(self):
        path = filedialog.askopenfilename(title="Choose your cover picture", filetypes=COVER_TYPES)
        if path:
            self.set_cover(path)

    def set_cover(self, path, quiet=False):
        try:
            pagecore.load_cover(path)
        except Exception:
            if not quiet:
                self.say("That is not a picture I can use as a cover. Choose a JPG, PNG or WebP picture.")
            return
        self.cover_path = path
        self.cover_mode.set("picture")
        self.update_cover()

    def clear_cover(self):
        self.cover_path = None
        if self.cover_mode.get() == "picture":
            self.cover_mode.set("none")
        self.update_cover()

    def cover_options(self):
        return {"mode": self.cover_mode.get(), "path": self.cover_path, "number": self.badge.get(),
                "corner": coverart.CORNERS[self.corner.get()], "size": coverart.SIZES[self.bsize.get()],
                "style": coverart.STYLES[self.bstyle.get()]}

    def update_cover(self):
        """The cover box shows your picture with an example number, exactly as it will look."""
        o = self.cover_options()
        if o["mode"] == "picture" and not self.cover_path:
            self.cover_note.set("Choose or drop a cover picture (until then no cover is added).")
        elif o["mode"] == "picture":
            self.cover_note.set(f"Cover: {os.path.basename(self.cover_path)} - page 1 of every book.")
        elif o["mode"] == "first":
            self.cover_note.set("Each book's own first page is used as its cover"
                                + (", with its number on it." if o["number"] else "."))
        else:
            self.cover_note.set("No cover page is added.")
        if self.cover_path:
            try:
                import tempfile
                from PIL import ImageTk
                src = self.cover_path
                if o["number"]:
                    tmp = os.path.join(tempfile.gettempdir(), "ebz_cover_preview.png")
                    src = coverart.stamp_cover(src, "#12", tmp, o["corner"], o["size"], o["style"])
                im = pagecore.load_cover(src)
                im.thumbnail((130, 170))
                self._photo = ImageTk.PhotoImage(im)
                self.cover_zone.config(image=self._photo, text="", width=self._photo.width(),
                                       height=self._photo.height())
                return
            except Exception:
                pass
        self._photo = None
        self.cover_zone.config(image="", text=COVER_TEXT, width=18, height=7)

    # ----- devices -----
    def device_keys(self):
        return [devices.DEVICE_KEYS[i] for i in self.dev_lb.curselection()]

    def update_devices(self):
        keys = self.device_keys()
        top = self.dev_lb.yview()[0]
        for i, k in enumerate(devices.DEVICE_KEYS):   # a tick mark, not just a highlight
            text = ("✓  " if k in keys else "     ") + devices.label_with_size(k)
            if self.dev_lb.get(i) != text:
                self.dev_lb.delete(i)
                self.dev_lb.insert(i, text)
                if k in keys:
                    self.dev_lb.selection_set(i)
        self.dev_lb.yview_moveto(top)
        self.dev_count.set(f"Devices: {len(keys)} ticked" if keys else "Devices: tick at least one")
        state = "normal" if "custom" in keys else "disabled"
        for w in (self.cw_box, self.ch_box, self.cg_box):
            w.config(state=state)

    def custom_info(self):
        """The custom size, or None when the boxes do not hold sensible numbers."""
        try:
            w, h = int(self.cw.get()), int(self.ch.get())
        except ValueError:
            return None
        if not (300 <= w <= 5000 and 300 <= h <= 8000):
            return None
        return {"width": w, "height": h, "gray": self.cgray.get()}

    def formats(self):
        return tuple(e for e, v in self.fmt.items() if v.get())

    # ----- remembering settings and window size -----
    def _on_configure(self, event):
        if event.widget is not self.root:
            return
        self._rewrap(event.width)
        lines = 2 if event.height < 700 else 5   # a short window keeps more room for the options
        if int(self.log.cget("height")) != lines:
            self.log.config(height=lines)
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self.save_all)

    def save_all(self):
        self._save_job = None
        try:
            data = load_settings(self.settings_path)
            data["geometry"] = self.root.geometry()
            data["devices"] = self.device_keys()
            data["formats"] = list(self.formats())
            data["out_dir"] = self.out.get()
            data["combine_fit"] = self.cfit.get()
            data["tab"] = self.tabs.index("current")
            data["cover"] = self.cover_options()
            ci = self.custom_info()
            if ci:
                data["custom"] = ci
            save_settings(data, self.settings_path)
        except Exception:
            pass

    def on_close(self):
        self.save_all()
        self.stop.set()
        self.root.destroy()

    # ----- output folder -----
    def choose_out(self):
        d = filedialog.askdirectory(title="Where should your files be saved?",
                                    initialdir=self.out.get() or os.path.expanduser("~"))
        if d:
            self.out.set(d)
            self.save_all()
            self.say(f"Your files will now be saved in: {d}")

    def open_folder(self):
        try:
            open_in_finder(self.out.get())
        except Exception as e:
            self.say(f"Could not open the folder: {e}")

    def open_last(self):
        try:
            open_in_finder(self.last_folder or self.out.get())
        except Exception as e:
            self.say(f"Could not open the folder: {e}")

    # ----- log and progress (the worker thread talks through the queue) -----
    def say(self, msg):
        self.q.put(("log", msg))

    def progress(self, frac, text):
        self.q.put(("progress", (frac, text)))

    def pump(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.log.config(state="normal")
                    self.log.insert("end", val + "\n")
                    self.log.see("end")
                    self.log.config(state="disabled")
                elif kind == "progress":
                    self.bar["value"] = int(val[0] * 1000)
                    self.status.set(val[1])
                elif kind == "status":
                    self.status.set(val)
                elif kind == "last":
                    self.last_folder = val
                    self.btn_last.config(state="normal" if val else "disabled")
                elif kind == "done":
                    if not self._updating:
                        self.btn_go.config(state="normal")
                    self.btn_stop.config(state="disabled")
                elif kind == "update_ready":
                    self._update_ready(val)
                elif kind == "update_failed":
                    self._update_done(f"The update could not be used: {val}")
        except queue.Empty:
            pass
        try:
            self._pump_job = self.root.after(100, self.pump)
        except tk.TclError:
            pass

    def _on_destroy(self, event):
        if event.widget is self.root and getattr(self, "_pump_job", None):
            try:
                self.root.after_cancel(self._pump_job)
            except tk.TclError:
                pass

    # ----- converting and combining -----
    def on_stop(self):
        self.stop.set()
        self.q.put(("status", "Stopping after this page..."))

    def start(self):
        combining = self.combining()
        books = self.current().books
        keys = self.device_keys()
        need_devices = not combining or self.cfit.get()
        custom = None
        if need_devices and "custom" in keys:
            custom = self.custom_info()
            if not custom:
                self.say("Type a custom size in pixels first (for example 1072 wide x 1448 tall).")
                return
        if not books:
            self.say("Drop some books into the box first.")
            return
        if combining and len(books) < 2:
            self.say("Add at least two books to join.")
            return
        if need_devices and not keys:
            self.say("Tick at least one device.")
            return
        if not self.formats():
            self.say("Tick at least one file type: CBZ, EPUB or PDF.")
            return
        if self.cover_mode.get() == "picture" and not self.cover_path:
            self.say("Choose a cover picture first, or pick 'No cover'.")
            return
        out = self.out.get().strip() or default_out_dir()
        self.save_all()
        self.stop.clear()
        self.btn_go.config(state="disabled")
        self.btn_stop.config(state="normal")
        copy = [converter.Book(b.name, b.kind, list(b.items)) for b in books]
        job = dict(books=copy, keys=keys if need_devices else [], formats=self.formats(), out=out,
                   custom=custom, cover=self.cover_options(), combining=combining,
                   fit=self.cfit.get(), name=self.cname.get().strip())
        self.worker = threading.Thread(target=self.run, args=(job,), daemon=True)
        self.worker.start()

    def run(self, job):
        try:
            if job["combining"]:
                self.say(f"Joining {len(job['books'])} books into one...")
                res = converter.combine(job["books"], job["name"], job["fit"], job["keys"], job["formats"],
                                        job["out"], job["custom"], self.progress, self.say, self.stop,
                                        job["cover"])
            else:
                self.say(f"Making {len(job['books'])} book(s) for {len(job['keys'])} device(s)...")
                res = converter.convert(job["books"], job["keys"], job["formats"], job["out"],
                                        job["custom"], self.progress, self.say, self.stop, job["cover"])
            if res:
                folders = []
                for r in res:
                    if r["folder"] not in folders:
                        folders.append(r["folder"])
                total = sum(r["screens"] for r in res)
                bad = sum(r["bad"] for r in res)
                self.say(f"Done: {len(res)} set(s) of files. Snug-fit check: "
                         + converter.clean_note(total, bad) + ".")
                for f in folders:
                    self.say(f"Your files are in: {f}")
                kinds = {}
                for r in res:
                    kinds.setdefault(r["kind"], r["folder"])
                for kind, folder in kinds.items():
                    if kind != "combined":
                        self.say("Next - " + devices.next_steps(kind, os.path.basename(folder)))
                self.q.put(("last", folders[0] if len(folders) == 1 else job["out"]))
                self.q.put(("status", "Done."))
            else:
                self.q.put(("status", "Nothing was made - see the messages above."))
        except pagecore.Stopped:
            self.q.put(("status", "Stopped."))
            self.say("Stopped. Files already finished are kept.")
        except ValueError as e:
            self.q.put(("status", "Check the settings."))
            self.say(str(e))
        except Exception as e:
            self.q.put(("status", "Something went wrong."))
            self.say(f"Error: {e}")
        finally:
            self.q.put(("done", None))


def make_root():
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk(), True
    except Exception:
        return tk.Tk(), False


def selftest(path):
    """Used by the build: proves the packaged app can convert pictures, a PDF, a CBZ and an
    EPUB, combine books, draw SVG pages, and open its window with drag and drop."""
    try:
        converter.selftest()
        import bookfiles
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            svg = os.path.join(d, "p.svg")
            with open(svg, "w") as f:
                f.write('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400">'
                        '<rect x="10" y="10" width="200" height="300" fill="red"/>'
                        '<text x="20" y="380" font-size="30">Hello</text></svg>')
            bookfiles._draw_svg(svg, os.path.join(d, "p.png"), 600)
        root, dnd = make_root()
        root.withdraw()
        App(root, dnd, os.path.join(os.path.dirname(os.path.abspath(path)), "selftest_settings.json"))
        root.update()
        root.destroy()
        if not dnd:
            raise RuntimeError("drag and drop is missing from this app")
        result = "OK"
    except Exception as e:
        result = f"FAIL {e}"
    with open(path, "w") as f:
        f.write(result)
    sys.exit(0 if result == "OK" else 1)


def _arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


if __name__ == "__main__":
    if "--version-file" in sys.argv:   # asked by the updater: "which program and version are you?"
        with open(_arg("--version-file"), "w", encoding="utf-8") as f:
            f.write(f"{version.APP_NAME}\n{version.VERSION}\n")
        sys.exit(0)
    if "--apply-update" in sys.argv:   # used by the build to test updating, end to end
        try:
            new, info = updater.apply(_arg("--apply-update"), launch_after="--no-launch" not in sys.argv)
            result = f"OK {info['name']} {info['version']} -> {new}"
        except Exception as e:
            result = f"FAIL {e}"
        if _arg("--result"):
            with open(_arg("--result"), "w", encoding="utf-8") as f:
                f.write(result)
        sys.exit(0 if result.startswith("OK") else 1)
    if "--selftest" in sys.argv:
        selftest(sys.argv[sys.argv.index("--selftest") + 1])
    if getattr(sys, "frozen", False):
        updater.cleanup_old()
    r, has_dnd = make_root()
    App(r, has_dnd)
    r.mainloop()
