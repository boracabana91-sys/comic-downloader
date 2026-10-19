"""Comic Series GOKU Downloader - paste the link of a page that lists many chapters;
it downloads every chapter you tick, one after the other, as your chosen file type."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import cleaner
import core
import covers
import series

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


class SeriesApp:
    def __init__(self, root, dnd=False, settings_path=None):
        self.root = root
        self.settings_path = settings_path
        root.title("Comic Series GOKU Downloader")
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        saved = series.load_settings(settings_path).get("geometry")
        root.geometry(series.fit_geometry(saved, sw, sh))   # the size you left it at last time
        root.minsize(700, 560)
        self._save_job = None
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Configure>", self._on_configure)
        self.cover_path = None
        self._photo = None
        self.chapters = []          # urls, oldest first
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        pad = {"padx": 14, "pady": 4}

        head = ttk.Frame(root)
        head.pack(fill="x")
        ttk.Label(head, text="Comic Series GOKU Downloader",
                  font=("Helvetica", 18, "bold")).pack(side="left", padx=14, pady=(14, 0))
        self.btn_update = ttk.Button(head, text="Update websites...", command=lambda: self.show_my_sites(editable=True))
        self.btn_update.pack(side="right", padx=14, pady=(14, 0))
        ttk.Label(root, text="Paste the link of the page that lists the chapters, press "
                  "Find chapters, then Download.", foreground="#555").pack(anchor="w", padx=14)

        # buttons, progress and log are packed first at the bottom, so they never get cut off
        self.bottom = ttk.Frame(root)
        self.bottom.pack(side="bottom", fill="x")

        # everything in the middle scrolls, so a short window never hides any option
        win = root
        try:
            bgc = ttk.Style().lookup("TFrame", "background") or None
        except Exception:
            bgc = None
        canvas = tk.Canvas(win, highlightthickness=0, borderwidth=0, **({"bg": bgc} if bgc else {}))
        vsb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        main = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=main, anchor="nw")
        main.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))

        def wheel(e):
            if isinstance(e.widget, (tk.Listbox, tk.Text)):
                return   # those scroll themselves
            canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        win.bind_all("<MouseWheel>", wheel)
        self.canvas = canvas
        root = main

        ttk.Label(root, text="Series link (the page with all the chapters) - or just type a series NAME").pack(anchor="w", **pad)
        row = ttk.Frame(root)
        row.pack(fill="x", padx=14)
        self.url = tk.StringVar()
        self.url_entry = ttk.Entry(row, textvariable=self.url)
        self.url_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Paste", command=self.paste).pack(side="left", padx=(8, 0))
        self.btn_find = ttk.Button(row, text="Find chapters", command=self.find)
        self.btn_find.pack(side="left", padx=(8, 0))

        # directly below the link box: where the chapters really come from, so you can check it yourself
        srcrow = ttk.Frame(root)
        srcrow.pack(fill="x", padx=14, pady=(4, 0))
        ttk.Label(srcrow, text="Original / Source site:", font=("Helvetica", 10, "bold")).pack(side="left")
        self.source = tk.StringVar(value="-")
        self.source_url = ""        # the page that "Open site" shows
        ttk.Label(srcrow, textvariable=self.source, foreground="#0a5").pack(side="left", padx=(6, 0))
        self.btn_source = ttk.Button(srcrow, text="Open site", command=self.open_source)
        self.btn_source.pack(side="right")
        self.url.trace_add("write", self.update_source)

        mrow = ttk.Frame(root)
        mrow.pack(fill="x", padx=14, pady=(4, 0))
        self.btn_myseries = ttk.Button(mrow, text="My series...", command=self.show_my_series)
        self.btn_myseries.pack(side="left")
        self.btn_mysites = ttk.Button(mrow, text="My sites...", command=self.show_my_sites)
        self.btn_mysites.pack(side="left", padx=6)
        ttk.Label(mrow, text="Type a name (e.g. the beginning after the end) and press Find chapters "
                  "to search all sites.", foreground="#555").pack(side="left", padx=6)
        self.alternates = []        # the same series on other sites: the backup when a chapter fails
        self.auto_new = False
        self.dialog = self.my_lb = self.sites_lb = self.choose_lb = None
        self.site_roots = []

        nrow = ttk.Frame(root)
        nrow.pack(fill="x", padx=14, pady=(6, 0))
        ttk.Label(nrow, text="Series name:").pack(side="left")
        self.sname = tk.StringVar()
        ttk.Entry(nrow, textvariable=self.sname).pack(side="left", fill="x", expand=True, padx=6)

        self.count = tk.StringVar(value="No chapters yet.")
        ttk.Label(root, textvariable=self.count).pack(anchor="w", padx=14, pady=(8, 0))
        lrow = ttk.Frame(root)
        lrow.pack(fill="both", padx=14, pady=(2, 0), expand=True)
        self.lb = tk.Listbox(lrow, selectmode="extended", height=8, exportselection=False)
        sb = ttk.Scrollbar(lrow, command=self.lb.yview)
        self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.lb.bind("<<ListboxSelect>>", lambda e: self.update_count())
        srow = ttk.Frame(root)
        srow.pack(fill="x", padx=14, pady=(4, 0))
        ttk.Button(srow, text="Select all", command=self.sel_all).pack(side="left")
        ttk.Button(srow, text="Select none", command=self.sel_none).pack(side="left", padx=6)
        ttk.Button(srow, text="New + out-of-date", command=self.sel_new).pack(side="left")
        ttk.Label(srow, text="  (click a chapter; Shift-click for a range; Cmd/Ctrl-click to add)",
                  foreground="#555").pack(side="left")

        ttk.Label(root, text="Save to folder").pack(anchor="w", **pad)
        row2 = ttk.Frame(root)
        row2.pack(fill="x", padx=14)
        self.folder = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads", "Comic Series"))
        self.folder_entry = ttk.Entry(row2, textvariable=self.folder)
        self.folder_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Choose folder", command=self.choose).pack(side="left", padx=(8, 0))

        send = ttk.Frame(root)
        send.pack(fill="x", padx=14, pady=(8, 0))
        ttk.Label(send, text="Send to:").pack(side="left")
        self.device_labels = [core.DEVICES[k]["label"] for k in core.DEVICE_KEYS]
        self.device = tk.StringVar(value=self.device_labels[0])
        box = ttk.Combobox(send, textvariable=self.device, values=self.device_labels,
                           state="readonly", width=58)
        box.pack(side="left", padx=6)
        if not core.HAS_PIL:
            box.config(state="disabled")
        box.bind("<<ComboboxSelected>>", lambda e: self.update_custom())

        ep = ttk.Frame(root)
        ep.pack(fill="x", padx=14, pady=(6, 0))
        ttk.Label(ep, text="Do you want an additional EPUB file?").pack(side="left")
        self.epub = tk.StringVar(value="No")
        ebox = ttk.Combobox(ep, textvariable=self.epub, values=["No", "Yes"],
                            state="readonly", width=5)
        ebox.pack(side="left", padx=6)
        if not core.HAS_PIL:
            ebox.config(state="disabled")
        ebox.bind("<<ComboboxSelected>>", self.update_preview)
        ttk.Label(ep, text="Pages per part:").pack(side="left", padx=(16, 0))
        self.size = tk.IntVar(value=5)
        self.size_spin = ttk.Spinbox(ep, from_=1, to=50, width=4, textvariable=self.size)
        self.size_spin.pack(side="left", padx=6)

        lay = ttk.Frame(root)
        lay.pack(fill="x", padx=14, pady=(8, 0))
        ttk.Label(lay, text="Folder layout:").pack(side="left")
        self.layout = tk.StringVar(value="one")
        ttk.Radiobutton(lay, text="Sample 1: one file per chapter", value="one",
                        variable=self.layout, command=self.update_preview).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(lay, text="Sample 2: files in parts of N pages", value="parts",
                        variable=self.layout, command=self.update_preview).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(lay, text="Layout C: EPUBs, CBZs and pictures each in one folder", value="central",
                        variable=self.layout, command=self.update_preview).pack(side="left", padx=(8, 0))
        fitrow = ttk.Frame(root)
        fitrow.pack(fill="x", padx=14, pady=(6, 0))
        ttk.Label(fitrow, text="Page fit:").pack(side="left")
        self.fit = tk.StringVar(value="new")   # snug fit every time the program opens
        ttk.Radiobutton(fitrow, text="Snug fit: whole scenes, not zoomed (checked after every chapter)",
                        value="new", variable=self.fit).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(fitrow, text="Previous (v4) - backup", value="old",
                        variable=self.fit).pack(side="left", padx=(8, 0))
        self.preview = tk.Label(root, justify="left", anchor="w", font=("Menlo", 11),
                                relief="groove", borderwidth=1, padx=8, pady=4)
        self.preview.pack(fill="x", padx=14, pady=(4, 0))

        self.custom_row = ttk.Frame(root)
        ttk.Label(self.custom_row, text="Screen width").pack(side="left")
        self.c_w = tk.StringVar(value="1072")
        ttk.Spinbox(self.custom_row, from_=300, to=4000, width=6,
                    textvariable=self.c_w).pack(side="left", padx=(4, 10))
        ttk.Label(self.custom_row, text="height").pack(side="left")
        self.c_h = tk.StringVar(value="1448")
        ttk.Spinbox(self.custom_row, from_=400, to=5000, width=6,
                    textvariable=self.c_h).pack(side="left", padx=(4, 10))
        ttk.Label(self.custom_row, text="pixels   File type").pack(side="left")
        self.c_ext = tk.StringVar(value=".pdf")
        ttk.Combobox(self.custom_row, textvariable=self.c_ext, values=[".pdf", ".cbz"],
                     state="readonly", width=5).pack(side="left", padx=(4, 10))
        self.c_gray = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.custom_row, text="Black and white",
                        variable=self.c_gray).pack(side="left")

        hide_row = ttk.Frame(root)
        self.hide_row = hide_row
        hide_row.pack(fill="x", padx=14, pady=(6, 0))
        self.hide = tk.BooleanVar(value=True)
        self.hide_box = ttk.Checkbutton(hide_row, text="Hide Lua / translated / website promo. "
                                        "Also hide:", variable=self.hide)
        self.hide_box.pack(side="left")
        self.words = tk.StringVar(value="")
        ttk.Entry(hide_row, textvariable=self.words, width=22).pack(side="left", padx=6)
        if not cleaner.ocr_available():
            self.hide.set(False)
            self.hide_box.config(state="disabled")

        opt2 = ttk.Frame(root)
        opt2.pack(fill="x", padx=14, pady=(6, 0))
        self.convert = tk.BooleanVar(value=False)
        if core.HAS_PIL:
            ttk.Checkbutton(opt2, text="Convert WebP to JPG",
                            variable=self.convert).pack(side="left")
        self.redo = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt2, text="Make finished chapters again",
                        variable=self.redo).pack(side="left", padx=18)

        cover_row = ttk.Frame(root)
        cover_row.pack(fill="x", padx=14, pady=(8, 0))
        self.zone = tk.Label(cover_row, text="Drop your cover picture here\n(or click to choose)",
                             relief="groove", borderwidth=2, width=30, height=5,
                             cursor="hand2", justify="center")
        self.zone.pack(side="left")
        self.zone.bind("<Button-1>", lambda e: self.choose_cover())
        side = ttk.Frame(cover_row)
        side.pack(side="left", padx=12)
        ttk.Button(side, text="Choose cover", command=self.choose_cover).pack(anchor="w")
        ttk.Button(side, text="Clear cover", command=self.clear_cover).pack(anchor="w", pady=(4, 0))
        self.cover_note = tk.StringVar(value="No cover picture chosen.")
        ttk.Label(side, textvariable=self.cover_note, foreground="#555",
                  wraplength=380).pack(anchor="w", pady=(4, 0))
        self.badge = tk.BooleanVar(value=True)
        ttk.Checkbutton(side, text="Put the chapter number on each chapter's cover",
                        variable=self.badge).pack(anchor="w", pady=(4, 0))
        ttk.Label(root, text="Tip: you can drop a series link (or a .url / .webloc shortcut), a folder "
                  "or a cover picture anywhere in this window.", foreground="#555").pack(
            anchor="w", padx=14, pady=(6, 0))
        self.drop_on = False
        if dnd:
            try:
                from tkinterdnd2 import DND_FILES, DND_TEXT
                for w in (self.root, self.canvas, self.url_entry, self.folder_entry, self.lb, self.zone):
                    w.drop_target_register(DND_FILES, DND_TEXT)
                    w.dnd_bind("<<Drop>>", self.on_drop)
                    w.dnd_bind("<<DropEnter>>", lambda e: self.zone.config(relief="solid"))
                    w.dnd_bind("<<DropLeave>>", lambda e: self.zone.config(relief="groove"))
                self.drop_on = True
            except Exception:
                pass

        btns = ttk.Frame(self.bottom)
        btns.pack(fill="x", padx=14, pady=8)
        self.btns = btns
        self.btn_go = ttk.Button(btns, text="Download selected chapters", command=self.start)
        self.btn_go.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=8)
        ttk.Button(btns, text="Open folder", command=self.open_folder).pack(side="left")

        self.bar = ttk.Progressbar(self.bottom, mode="determinate")
        self.bar.pack(fill="x", padx=14, pady=(2, 2))
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self.bottom, textvariable=self.status).pack(anchor="w", padx=14)
        self.log = tk.Text(self.bottom, height=7, state="disabled", wrap="word")
        self.log.pack(fill="x", padx=14, pady=(6, 14))
        self.size.trace_add("write", self.update_preview)
        self.sname.trace_add("write", self.update_preview)
        self.update_preview()
        root.after(100, self.pump)

    # ----- remembering the window size and position -----
    def _on_configure(self, event):
        if event.widget is not self.root:
            return
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self.save_geometry)

    def save_geometry(self):
        self._save_job = None
        try:
            data = series.load_settings(self.settings_path)
            data["geometry"] = self.root.geometry()
            series.save_settings(data, self.settings_path)
        except Exception:
            pass

    def on_close(self):
        self.save_geometry()
        self.root.destroy()

    # ----- helpers -----
    def paste(self):
        try:
            self.url.set(self.root.clipboard_get().strip())
        except tk.TclError:
            pass

    def update_source(self, *_):
        link = self.url.get().strip()
        self.source.set(series.source_label(link))
        self.source_url = link if series.site_name(link) else ""

    def open_source(self):
        if self.source_url:
            webbrowser.open(self.source_url)

    def choose(self):
        d = filedialog.askdirectory(initialdir=self.folder.get() or os.path.expanduser("~"))
        if d:
            self.folder.set(d)

    def device_key(self):
        try:
            return core.DEVICE_KEYS[self.device_labels.index(self.device.get())]
        except ValueError:
            return "images"

    def choose_cover(self):
        path = filedialog.askopenfilename(
            title="Choose your cover picture",
            filetypes=[("Pictures", "*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff")])
        if path:
            self.set_cover(path)

    def on_drop(self, event):
        self.zone.config(relief="groove")
        data = event.data or ""
        items = list(self.root.tk.splitlist(data)) if "{" in data or os.path.exists(data) else [data]
        kind, val = series.classify_drop(items)
        if kind == "cover":
            self.set_cover(val)
        elif kind == "folder":
            self.folder.set(val)
            self.cover_note_hint(f"Saving to: {val}")
        elif kind == "link":
            self.url.set(val)
            self.find()
        else:
            self.cover_note.set("I could not use what you dropped. Drop a series link, a folder "
                                "or a JPG, PNG or WebP cover picture.")
        return event.action

    def cover_note_hint(self, text):
        if self.cover_path is None:
            self.cover_note.set(text)

    def set_cover(self, path):
        if not covers.is_cover_file(path):
            self.cover_note.set("That is not a picture I can use. Choose a JPG, PNG or WebP picture.")
            return
        try:
            from PIL import ImageTk
            im = covers.load_cover(path)
            im.thumbnail((120, 120))
            self._photo = ImageTk.PhotoImage(im)
            self.zone.config(image=self._photo, text="", width=self._photo.width(),
                             height=self._photo.height())
        except Exception:
            pass
        self.cover_path = path
        self.cover_note.set(f"Cover: {os.path.basename(path)}\nUsed for every chapter until you "
                            "press Clear cover.")

    def clear_cover(self):
        self.cover_path = None
        self._photo = None
        self.zone.config(image="", text="Drop your cover picture here\n(or click to choose)",
                         width=30, height=4)
        self.cover_note.set("No cover picture chosen.")

    def update_preview(self, *_):
        key = self.device_key()
        ext = ""
        if key not in ("images",):
            try:
                ext = core.resolve_device(key, self.custom_info() if key == "custom" else None)["ext"]
            except Exception:
                ext = core.DEVICES.get(key, {}).get("ext", "")
        try:
            size = max(1, int(self.size.get()))
        except Exception:
            size = 5
        name = core.clean_title(self.sname.get(), "") or "Series name"
        lay = self.layout.get()
        self.size_spin.config(state="disabled" if lay in series.PAGES_IN_FOLDER else "normal")
        self.preview.config(text=series.layout_preview(lay, name, ext, self.epub.get() == "Yes", size))

    def update_custom(self):
        self.update_preview()
        if self.device_key() == "custom":
            self.custom_row.pack(fill="x", padx=14, pady=(6, 0), before=self.hide_row)
        else:
            self.custom_row.pack_forget()

    def custom_info(self):
        try:
            w, h = int(self.c_w.get()), int(self.c_h.get())
        except ValueError:
            return None
        if not (300 <= w <= 4000 and 400 <= h <= 5000):
            return None
        return {"width": w, "height": h, "ext": self.c_ext.get(), "gray": self.c_gray.get()}

    def open_folder(self):
        d = self.folder.get()
        name = core.clean_title(self.sname.get(), "")
        if name and os.path.isdir(os.path.join(d, name)):
            d = os.path.join(d, name)
        os.makedirs(d, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.Popen(["open", d])
        elif sys.platform.startswith("win"):
            os.startfile(d)  # noqa
        else:
            subprocess.Popen(["xdg-open", d])

    # ----- chapter list -----
    def show_chapters(self, title, urls):
        self.chapters = list(urls)
        if title and not self.sname.get().strip():
            clean = core.clean_title(series.clean_series_name(title), "Series")
            raw = core.clean_title(title, "Series")
            out = self.folder.get()
            old = raw != clean and os.path.isdir(os.path.join(out, raw)) \
                and not os.path.isdir(os.path.join(out, clean))
            self.sname.set(raw if old else clean)   # folders made by older builds keep their name
        names = series.chapter_names("", urls)
        self.lb.delete(0, "end")
        for n in names:
            self.lb.insert("end", n.replace(" - ", "", 1))
        self.sel_all()

    def update_count(self):
        n = len(self.lb.curselection())
        self.count.set(f"{len(self.chapters)} chapters found. {n} ticked for download."
                       if self.chapters else "No chapters yet.")

    def sel_all(self):
        self.lb.selection_set(0, "end")
        self.update_count()

    def sel_none(self):
        self.lb.selection_clear(0, "end")
        self.update_count()

    def sel_new(self):
        state = series.load_state(os.path.join(self.folder.get(),
                                               core.clean_title(self.sname.get(), "Series")))
        self.lb.selection_clear(0, "end")
        have = {series.chapter_number(u) for u, rec in state["done"].items() if series.is_current(rec)}
        for i, u in enumerate(self.chapters):
            n = series.chapter_number(u)
            if (n is None and u not in state["done"]) or (n is not None and n not in have):
                self.lb.selection_set(i)
        self.update_count()

    def say(self, msg):
        self.q.put(("log", msg))

    def pump(self):
        try:
            while True:
                kind, a, b = (self.q.get_nowait() + (None, None))[:3]
                if kind == "log":
                    self.log.config(state="normal")
                    self.log.insert("end", a + "\n")
                    self.log.see("end")
                    self.log.config(state="disabled")
                elif kind == "progress":
                    self.bar["maximum"] = max(b, 1)
                    self.bar["value"] = a
                elif kind == "status":
                    self.status.set(a)
                elif kind == "chapters":
                    self.show_chapters(a, b)
                    if self.auto_new:           # opened from 'My series': tick only what is new
                        self.auto_new = False
                        self.sel_new()
                elif kind == "choose":
                    self.choose_dialog(a)
                elif kind == "mys":
                    self._fill_row(self.my_lb, a, b)
                elif kind == "sitesreopen":
                    self.show_my_sites(a, editable=True)
                elif kind == "sites":
                    for i, text in enumerate(a):
                        self._fill_row(self.sites_lb, i, text)
                elif kind == "url":
                    self.url.set(a)     # the original source's link replaces a copy site's link
                elif kind == "found_done":
                    self.btn_find.config(state="normal")
                elif kind == "done":
                    self.btn_go.config(state="normal")
                    self.btn_stop.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def progress(self, done, total, text):
        self.q.put(("progress", done, total))
        self.q.put(("status", text))

    # ----- actions -----
    def find(self, keep_alternates=False):
        link = self.url.get().strip()
        if not link:
            messagebox.showinfo("Link or name needed", "Paste the link of a series, or type a series "
                                "name such as: the beginning after the end")
            return
        if not keep_alternates:
            self.alternates = []
        self.btn_find.config(state="disabled")
        self.sname.set("")
        if not link.lower().startswith("http"):
            self.say(f"Searching all sites for '{link}'...")
            threading.Thread(target=self._search, args=(link,), daemon=True).start()
            return
        self.say("Reading the page...")
        threading.Thread(target=self._find, args=(link,), daemon=True).start()

    def _search(self, name):
        try:
            known = series.load_settings(self.settings_path).get("sources") or []
            found = series.search_name(name, known=known, say=self.say)
            if not found:
                self.say("Nothing found on the sites this program knows. Try fewer words, or paste a "
                         "link from a site that has it (the program remembers that site).")
                self.q.put(("status", "Nothing found."))
                self.q.put(("found_done", None))
                return
            self.say(f"Found {len(found)} option(s).")
            self.q.put(("choose", found))
        except Exception as e:
            self.say(f"Error: {e}")
            self.q.put(("found_done", None))

    def choose_dialog(self, found):
        """'Where do you want to get it?': the list of series found, one per line."""
        self.btn_find.config(state="normal")
        if len(found) == 1:
            self.use_option(found, found[0])
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Where do you want to get it?")
        dlg.transient(self.root)
        ttk.Label(dlg, text="Pick one, then press 'Use this one' (or double-click it). The same series "
                  "on other sites is kept as a backup if a chapter fails.", wraplength=640
                  ).pack(anchor="w", padx=12, pady=(10, 4))
        lb = tk.Listbox(dlg, width=100, height=min(14, len(found)), exportselection=False)
        lb.pack(fill="both", expand=True, padx=12)
        for r in found:
            lb.insert("end", series.option_label(r))
        lb.selection_set(0)

        def go(*_):
            sel = lb.curselection()
            if sel:
                dlg.destroy()
                self.use_option(found, found[sel[0]])
        lb.bind("<Double-Button-1>", go)
        row = ttk.Frame(dlg)
        row.pack(fill="x", padx=12, pady=10)
        ttk.Button(row, text="Use this one", command=go).pack(side="left")
        ttk.Button(row, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)
        self.dialog, self.choose_lb = dlg, lb

    def use_option(self, found, pick):
        self.alternates = [r["url"] for r in found
                           if r is not pick and series.same_series(r["title"], pick["title"])]
        self.url.set(pick["url"])
        self.find(keep_alternates=True)

    def _backups(self, link, name):
        """After a series is found: look up the same series on the other sites (the backups)."""
        try:
            known = series.load_settings(self.settings_path).get("sources") or []
            self.alternates = series.find_alternates(name, link, known=known)
            if self.alternates:
                sites = ", ".join(series.site_name(u) for u in self.alternates)
                self.say(f"Backup sites ready if a chapter fails: {sites}.")
        except Exception:
            pass

    @staticmethod
    def _fill_row(lb, i, text):
        try:
            if lb is not None and lb.winfo_exists() and i < lb.size():
                sel = lb.curselection()
                lb.delete(i)
                lb.insert(i, text)
                for k in sel:
                    lb.selection_set(k)
        except Exception:
            pass

    def _popup(self, title, lines, note):
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        ttk.Label(dlg, text=note, wraplength=560).pack(anchor="w", padx=12, pady=(10, 4))
        lb = tk.Listbox(dlg, width=84, height=min(14, max(4, len(lines))), exportselection=False)
        lb.pack(fill="both", expand=True, padx=12)
        for text in lines:
            lb.insert("end", text)
        self.dialog = dlg
        return dlg, lb

    def show_my_series(self):
        items = series.load_settings(self.settings_path).get("series") or []
        if not items:
            messagebox.showinfo("My series", "Nothing here yet. Every series you download is "
                                "remembered here, so you can check it for new chapters in one click.")
            return
        dlg, lb = self._popup("My series", [f"{i['title']}   -   checking..." for i in items],
                              "Your series. Pick one and press 'Open and tick the new chapters'.")
        self.my_lb = lb
        lb.selection_set(0)
        out = self.folder.get()

        def check():
            for idx, item in enumerate(items):
                try:
                    n, _fresh = series.new_chapters(item["url"], item["title"], out)
                    text = f"{item['title']}   -   {n} new chapter(s)" if n else f"{item['title']}   -   up to date"
                except Exception:
                    text = f"{item['title']}   -   could not check (site not answering)"
                self.q.put(("mys", idx, text))
        threading.Thread(target=check, daemon=True).start()

        def go(*_):
            sel = lb.curselection()
            if sel:
                dlg.destroy()
                self.url.set(items[sel[0]]["url"])
                self.auto_new = True
                self.find()
        lb.bind("<Double-Button-1>", go)
        row = ttk.Frame(dlg)
        row.pack(fill="x", padx=12, pady=10)
        ttk.Button(row, text="Open and tick the new chapters", command=go).pack(side="left")
        ttk.Button(row, text="Close", command=dlg.destroy).pack(side="left", padx=8)

    def show_my_sites(self, note="", editable=False):
        """'My sites': the sites searched, a dot for each. With editable=True ('Update websites') there is also
        a bar to add a new site and a button to remove the ones you added."""
        if self.dialog is not None:
            try:
                self.dialog.destroy()
            except Exception:
                pass
        known = series.load_settings(self.settings_path).get("sources") or []
        roots = list(series.KNOWN_SOURCES) + [k for k in known if k not in series.KNOWN_SOURCES]
        dlg, lb = self._popup("Update websites" if editable else "My sites", [f"...   {series.site_name(r)}   -   checking..." for r in roots],
                              "Websites this program searches. A full dot means it answers today."
                              + (" To add another site, paste its link below and press 'Add website'." if editable else ""))
        self.sites_lb = lb
        self.site_roots = roots

        def check():
            mark = {"ok": "\u25cf", "moved": "\u25d0", "down": "\u25cb"}
            rows = []
            for st in series.site_status(roots):
                how = {"ok": "answers", "moved": f"maybe moved to {st['now']}", "down": "not answering"}[st["state"]]
                rows.append(f"{mark[st['state']]}   {st['site']}   -   {how}")
            self.q.put(("sites", rows))
        threading.Thread(target=check, daemon=True).start()

        if not editable:
            ttk.Button(dlg, text="Close", command=dlg.destroy).pack(padx=12, pady=10)
            return
        msg = tk.StringVar(value=note)
        ttk.Label(dlg, textvariable=msg, wraplength=560, foreground="#0a5").pack(anchor="w", padx=12, pady=(6, 0))
        row = ttk.Frame(dlg)
        row.pack(fill="x", padx=12, pady=(8, 0))
        new = tk.StringVar()
        entry = ttk.Entry(row, textvariable=new)
        entry.pack(side="left", fill="x", expand=True)
        btn = ttk.Button(row, text="Add website")
        btn.pack(side="left", padx=(8, 0))

        def add(*_):
            link = new.get().strip()
            if not link:
                return
            btn.config(state="disabled")
            msg.set("Checking the site...")

            def work():
                try:
                    root, text, ok = series.add_site(link, known=series.load_settings(self.settings_path).get("sources") or [])
                    if ok:
                        data = series.load_settings(self.settings_path)
                        data["sources"] = (data.get("sources") or []) + [root]
                        series.save_settings(data, self.settings_path)
                except Exception as e:
                    text = f"Could not add it: {e}"
                self.q.put(("sitesreopen", text))
            threading.Thread(target=work, daemon=True).start()
        btn.config(command=add)
        entry.bind("<Return>", add)

        def remove():
            sel = lb.curselection()
            if not sel or sel[0] < len(series.KNOWN_SOURCES):
                msg.set("Pick a site you added yourself (the built-in ones cannot be removed).")
                return
            gone = self.site_roots[sel[0]]
            data = series.load_settings(self.settings_path)
            data["sources"] = [k for k in (data.get("sources") or []) if k != gone]
            series.save_settings(data, self.settings_path)
            self.show_my_sites(f"Removed {series.site_name(gone)}.", editable=True)
        brow = ttk.Frame(dlg)
        brow.pack(fill="x", padx=12, pady=10)
        ttk.Button(brow, text="Remove selected", command=remove).pack(side="left")
        ttk.Button(brow, text="Close", command=dlg.destroy).pack(side="left", padx=8)

    def _find(self, link):
        try:
            if series.is_aggregator(link):
                # a copy site (comix.to) blocks programs: go to the group's own site instead
                copy_site = series.site_name(link)
                self.say(f"{copy_site} only copies chapters and does not let programs in. "
                         "Looking for the original source site...")
                known = series.load_settings(self.settings_path).get("sources") or []
                orig = series.find_source(link, say=self.say, known=known)
                if not orig:
                    self.say("The original source of this series was not found on the sites this "
                             "program knows. The lines above show what was tried. Do this ONCE: "
                             "open the series on any site that has it, copy that link and paste it "
                             "here instead. The program then remembers that site, and the next "
                             f"{copy_site} link of a series on it is found automatically. "
                             "Or send this log to your developer to add the site.")
                    self.q.put(("status", "Original source not found."))
                    return
                self.say(f"Found it on {orig['site']} as '{orig['title'].split(' ~')[0][:60]}'. "
                         f"Using {orig['url']}")
                link = orig["url"]
                self.q.put(("url", link))
            try:
                info = series.inspect_series(link)
            except Exception:
                # the site may have moved to another address ending (.com -> .net): look for it there
                moved = None if series.is_aggregator(link) else series.find_moved(link, say=self.say)
                if not moved:
                    raise
                self.say(f"The site has moved. Using {moved}")
                link = moved
                self.q.put(("url", link))
                info = series.inspect_series(link)
            if info["chapters"]:
                root = series.remember_site(link, series.load_settings(self.settings_path).get("sources") or [])
                if root:
                    data = series.load_settings(self.settings_path)
                    data["sources"] = (data.get("sources") or []) + [root]
                    series.save_settings(data, self.settings_path)
                    self.say(f"Remembered {series.site_name(root)}: copy-site links are now also "
                             "looked up there automatically.")
            if not info["chapters"]:
                self.say("No chapter links found on that page. Make sure it is the page that "
                         "lists the chapters, then try again. If it keeps happening, send the "
                         "link to your developer.")
                self.q.put(("status", "No chapters found."))
            else:
                self.q.put(("chapters", info["title"], info["chapters"]))
                if not self.alternates:
                    threading.Thread(target=self._backups, args=(link, series.clean_series_name(info["title"])),
                                     daemon=True).start()
                self.say(f"Found {len(info['chapters'])} chapters of '{info['title']}'. "
                         "Tick the ones you want, choose your gadget, then press Download.")
                tot = info.get("total")
                site = series.site_name(link)
                shut = info.get("locked") or []
                if shut:
                    self.say(f"Not an error: {len(info['chapters'])} chapters are free to download. "
                             f"{len(shut)} more (chapter {series.chapter_range(shut)}) are on {site} "
                             "but locked behind its coins, so this program cannot download them.")
                    self.say("To continue the series: press 'Open site' above to read or unlock "
                             f"them on {site}. When they become free, press Find chapters again "
                             "and then 'New + out-of-date'.")
                    other = series.find_original(link, skip_site=site, name=info["title"])
                    if other:
                        self.say(f"The same series is also on {other['site']}: {other['url']}. "
                                 "Paste that link to try its chapters.")
                elif tot and tot != len(info["chapters"]):
                    self.say(f"Note: the website says it has {tot} chapters but only "
                             f"{len(info['chapters'])} can be downloaded (some may be paid or "
                             "locked).")
                self.q.put(("status", "Ready."))
        except Exception as e:
            msg = str(e)
            if "HTTP Error 403" in msg or "HTTP Error 401" in msg:
                msg += " (the website refused the program; send this message to your developer)"
            elif "urlopen error" in msg:
                msg += " (check your internet connection and the link)"
            self.say(f"Error: {msg}")
        finally:
            self.q.put(("found_done", None))

    def on_stop(self):
        self.stop.set()
        self.status.set("Stopping...")

    def start(self):
        picked = [self.chapters[i] for i in self.lb.curselection()]
        if not picked:
            messagebox.showinfo("No chapters ticked", "Press Find chapters first, then tick the "
                                "chapters you want.")
            return
        try:
            size = max(1, int(self.size.get()))
        except Exception:
            size = 5
        custom = None
        if self.device_key() == "custom":
            custom = self.custom_info()
            if custom is None:
                messagebox.showinfo("Screen size needed",
                                    "Please type your screen width (300 to 4000) and height "
                                    "(400 to 5000) in pixels.")
                return
        cover = self.cover_path if self.cover_path and os.path.isfile(self.cover_path) else None
        opts = {"fit": self.fit.get(), "badge": self.badge.get(), "layout": self.layout.get(), "size": size, "convert": self.convert.get(), "device": self.device_key(),
                "custom": custom, "epub": self.epub.get() == "Yes", "cover": cover,
                "words": cleaner.all_words(self.words.get()) if self.hide.get() else [],
                "redo": self.redo.get(), "all_urls": self.chapters, "alternates": list(self.alternates)}
        name = core.clean_title(self.sname.get(), "Series")
        try:
            data = series.load_settings(self.settings_path)
            data["series"] = series.remember_series(data.get("series"), self.url.get().strip(), name)
            series.save_settings(data, self.settings_path)
        except Exception:
            pass
        self.stop.clear()
        self.btn_go.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.bar["value"] = 0
        self.worker = threading.Thread(target=self.run, args=(name, picked, opts), daemon=True)
        self.worker.start()

    def run(self, name, picked, opts):
        try:
            os.makedirs(self.folder.get(), exist_ok=True)
            self.say(f"Starting {len(picked)} chapter(s) of '{name}'...")
            res = series.run_series(name, picked, self.folder.get(), opts, self.progress,
                                    self.stop, self.say)
            self.say("")
            self.say(f"FINISHED. Made {len(res['done'])} chapter(s), skipped "
                     f"{len(res['skipped'])} already finished, {len(res['failed'])} with problems.")
            for n, why in res["failed"]:
                self.say(f"  Not finished: {n} ({why}). Press Download again to retry it.")
            self.q.put(("status", f"All done. Saved in {res['dir']}"))
            device = opts["device"]
            if res["done"] and device != "images":
                self.say(core.resolve_device(device, opts["custom"])["next"])
                if opts["epub"]:
                    self.say(core.epub_note(device))
            elif res["done"] and opts["epub"]:
                self.say(core.resolve_device("epub_only")["next"])
        except core.Stopped:
            self.q.put(("status", "Stopped."))
            self.say("Stopped. Press Download again to continue where it left off; finished "
                     "chapters are skipped.")
        except Exception as e:
            self.q.put(("status", "Something went wrong."))
            self.say(f"Error: {e}")
        finally:
            self.q.put(("done", None))


def selftest(path):
    """Used by the build: proves the packaged app can open https pages, read text, load the window."""
    try:
        core.fetch_text("https://github.com")
        core.selftest_device()
        if cleaner.ocr_available():
            cleaner.selftest()
        else:
            raise RuntimeError("the text reader is missing from this app")
        root, dnd = make_root()
        root.withdraw()
        root.destroy()
        if not dnd:
            raise RuntimeError("drag and drop is missing from this app")
        result = "OK"
    except Exception as e:
        result = f"FAIL {e}"
    with open(path, "w") as f:
        f.write(result)
    sys.exit(0 if result == "OK" else 1)


def make_root():
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk(), True
    except Exception:
        return tk.Tk(), False


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(sys.argv[sys.argv.index("--selftest") + 1])
    r, has_dnd = make_root()
    SeriesApp(r, has_dnd)
    r.mainloop()
