"""Comic Series Downloader - paste the link of a page that lists many chapters;
it downloads every chapter you tick, one after the other, as your chosen file type."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
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
        root.title("Comic Series Downloader")
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

        ttk.Label(root, text="Comic Series Downloader",
                  font=("Helvetica", 18, "bold")).pack(anchor="w", padx=14, pady=(14, 0))
        ttk.Label(root, text="Paste the link of the page that lists the chapters, press "
                  "Find chapters, then Download.", foreground="#555").pack(anchor="w", padx=14)

        # buttons, progress and log are packed first at the bottom, so they never get cut off
        self.bottom = ttk.Frame(root)
        self.bottom.pack(side="bottom", fill="x")

        ttk.Label(root, text="Series link (the page with all the chapters)").pack(anchor="w", **pad)
        row = ttk.Frame(root)
        row.pack(fill="x", padx=14)
        self.url = tk.StringVar()
        ttk.Entry(row, textvariable=self.url).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Paste", command=self.paste).pack(side="left", padx=(8, 0))
        self.btn_find = ttk.Button(row, text="Find chapters", command=self.find)
        self.btn_find.pack(side="left", padx=(8, 0))

        nrow = ttk.Frame(root)
        nrow.pack(fill="x", padx=14, pady=(6, 0))
        ttk.Label(nrow, text="Series name:").pack(side="left")
        self.sname = tk.StringVar()
        ttk.Entry(nrow, textvariable=self.sname).pack(side="left", fill="x", expand=True, padx=6)

        self.count = tk.StringVar(value="No chapters yet.")
        ttk.Label(root, textvariable=self.count).pack(anchor="w", padx=14, pady=(8, 0))
        lrow = ttk.Frame(root)
        lrow.pack(fill="both", padx=14, pady=(2, 0), expand=True)
        self.lb = tk.Listbox(lrow, selectmode="extended", height=5, exportselection=False)
        sb = ttk.Scrollbar(lrow, command=self.lb.yview)
        self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.lb.bind("<<ListboxSelect>>", lambda e: self.update_count())
        srow = ttk.Frame(root)
        srow.pack(fill="x", padx=14, pady=(4, 0))
        ttk.Button(srow, text="Select all", command=self.sel_all).pack(side="left")
        ttk.Button(srow, text="Select none", command=self.sel_none).pack(side="left", padx=6)
        ttk.Button(srow, text="Only new ones", command=self.sel_new).pack(side="left")
        ttk.Label(srow, text="  (click a chapter; Shift-click for a range; Cmd/Ctrl-click to add)",
                  foreground="#555").pack(side="left")

        ttk.Label(root, text="Save to folder").pack(anchor="w", **pad)
        row2 = ttk.Frame(root)
        row2.pack(fill="x", padx=14)
        self.folder = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads", "Comic Series"))
        ttk.Entry(row2, textvariable=self.folder).pack(side="left", fill="x", expand=True)
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
                             relief="groove", borderwidth=2, width=30, height=4,
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
        if dnd:
            try:
                from tkinterdnd2 import DND_FILES
                self.zone.drop_target_register(DND_FILES)
                self.zone.dnd_bind("<<Drop>>", self.on_drop)
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
        for p in self.root.tk.splitlist(event.data):
            if covers.is_cover_file(p):
                self.set_cover(p)
                return
        self.cover_note.set("That is not a picture I can use. Drop a JPG, PNG or WebP picture.")

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
        self.size_spin.config(state="disabled" if lay == "one" else "normal")
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
            self.sname.set(title)
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
        for i, u in enumerate(self.chapters):
            if u not in state["done"]:
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
    def find(self):
        link = self.url.get().strip()
        if not link.lower().startswith("http"):
            messagebox.showinfo("Link needed", "Please paste the full link, starting with https://")
            return
        self.btn_find.config(state="disabled")
        self.sname.set("")
        self.say("Reading the page...")
        threading.Thread(target=self._find, args=(link,), daemon=True).start()

    def _find(self, link):
        try:
            info = series.inspect_series(link)
            if not info["chapters"]:
                self.say("No chapter links found on that page. Make sure it is the page that "
                         "lists the chapters, then try again. If it keeps happening, send the "
                         "link to your developer.")
                self.q.put(("status", "No chapters found."))
            else:
                self.q.put(("chapters", info["title"], info["chapters"]))
                self.say(f"Found {len(info['chapters'])} chapters of '{info['title']}'. "
                         "Tick the ones you want, choose your gadget, then press Download.")
                tot = info.get("total")
                if tot and tot != len(info["chapters"]):
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
        opts = {"badge": self.badge.get(), "layout": self.layout.get(), "size": size, "convert": self.convert.get(), "device": self.device_key(),
                "custom": custom, "epub": self.epub.get() == "Yes", "cover": cover,
                "words": cleaner.all_words(self.words.get()) if self.hide.get() else [],
                "redo": self.redo.get(), "all_urls": self.chapters}
        name = core.clean_title(self.sname.get(), "Series")
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
