"""EBZ CNVRTR - the window.

Drop pictures, PDFs, CBZ files or folders -> tick your devices -> Convert.
Every device gets its own folder of .cbz and .epub files (plus .pdf where it needs one),
with pages fitted snugly to that device's screen."""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import converter  # noqa: E402
import devices  # noqa: E402
import pagecore  # noqa: E402
import version  # noqa: E402

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".ebz_cnvrtr.json")
_GEO = re.compile(r"^(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?$")
DROP_TEXT = "Drop pictures, PDFs, CBZ files or folders here\nor click to choose files"
PICK_TYPES = [("Pictures, PDF and comics", " ".join("*" + e for e in converter.ALL_EXT)),
              ("All files", "*")]


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


def fit_geometry(saved, screen_w, screen_h, default=(780, 900), minimum=(680, 540)):
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
    return os.path.join(desk if os.path.isdir(desk) else os.path.expanduser("~"), "EBZ CNVRTR")


class App:
    def __init__(self, root, dnd=False, settings_path=None):
        self.root = root
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        root.title(version.full_name())
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(fit_geometry(self.settings.get("geometry"), sw, sh))
        root.minsize(680, 540)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Configure>", self._on_configure)
        self._save_job = None
        self.books = []
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        px = 14

        # ----- header with the version -----
        head = ttk.Frame(root)
        head.pack(fill="x", padx=px, pady=(12, 0))
        self.title_label = ttk.Label(head, text=version.full_name(), font=("Helvetica", 20, "bold"))
        self.title_label.pack(side="left")
        self.version_label = ttk.Label(head, text=f"Version {version.VERSION}", foreground="#666")
        self.version_label.pack(side="right", anchor="s")
        ttk.Label(root, text="Turn pictures, PDFs and comics into CBZ and EPUB files that fit "
                  "your device's screen.", foreground="#555").pack(anchor="w", padx=px)

        # ----- bottom part first, so the buttons and log are never cut off -----
        self.bottom = ttk.Frame(root)
        self.bottom.pack(side="bottom", fill="x")

        # ----- the middle scrolls (same way as Comic Series Downloader) -----
        try:
            bgc = ttk.Style().lookup("TFrame", "background") or None
        except Exception:
            bgc = None
        canvas = tk.Canvas(root, highlightthickness=0, borderwidth=0, **({"bg": bgc} if bgc else {}))
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

        # ----- drop box -----
        self.zone = tk.Canvas(main, height=120, highlightthickness=0, cursor="hand2",
                              **({"bg": bgc} if bgc else {}))
        self.zone.pack(fill="x", padx=px, pady=(12, 4))
        self.zone.bind("<Configure>", lambda e: self._draw_zone())
        self.zone.bind("<Button-1>", lambda e: self.add_files())
        self._zone_hot = False
        brow = ttk.Frame(main)
        brow.pack(fill="x", padx=px)
        ttk.Button(brow, text="Add files...", command=self.add_files).pack(side="left")
        ttk.Button(brow, text="Add a folder...", command=self.add_folder).pack(side="left", padx=8)

        # ----- books -----
        self.count = tk.StringVar(value="No books yet.")
        ttk.Label(main, textvariable=self.count, font=("Helvetica", 12, "bold")).pack(
            anchor="w", padx=px, pady=(12, 0))
        ttk.Label(main, text="Each folder, PDF or CBZ becomes one book. Loose pictures from one "
                  "folder become one book, in name order (2 before 10).", foreground="#555",
                  wraplength=640, justify="left").pack(anchor="w", padx=px)
        lrow = ttk.Frame(main)
        lrow.pack(fill="x", padx=px, pady=(4, 0))
        self.lb = tk.Listbox(lrow, selectmode="extended", height=6, exportselection=False)
        sb = ttk.Scrollbar(lrow, command=self.lb.yview)
        self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="x", expand=True)
        sb.pack(side="left", fill="y")
        rrow = ttk.Frame(main)
        rrow.pack(fill="x", padx=px, pady=(4, 0))
        ttk.Button(rrow, text="Remove selected", command=self.remove_selected).pack(side="left")
        ttk.Button(rrow, text="Clear all", command=self.clear_books).pack(side="left", padx=8)

        # ----- devices -----
        self.dev_count = tk.StringVar()
        ttk.Label(main, textvariable=self.dev_count, font=("Helvetica", 12, "bold")).pack(
            anchor="w", padx=px, pady=(14, 0))
        ttk.Label(main, text="Click a device to tick or untick it. Each one gets its own folder.",
                  foreground="#555").pack(anchor="w", padx=px)
        drow = ttk.Frame(main)
        drow.pack(fill="x", padx=px, pady=(4, 0))
        self.dev_lb = tk.Listbox(drow, selectmode="multiple", height=9, exportselection=False)
        dsb = ttk.Scrollbar(drow, command=self.dev_lb.yview)
        self.dev_lb.config(yscrollcommand=dsb.set)
        self.dev_lb.pack(side="left", fill="x", expand=True)
        dsb.pack(side="left", fill="y")
        for k in devices.DEVICE_KEYS:
            self.dev_lb.insert("end", devices.label_with_size(k))
        saved = [k for k in self.settings.get("devices", ["kobo_clara"]) if k in devices.DEVICES]
        for k in saved or ["kobo_clara"]:
            self.dev_lb.selection_set(devices.DEVICE_KEYS.index(k))
        self.dev_lb.bind("<<ListboxSelect>>", lambda e: self.update_devices())

        c = self.settings.get("custom", {})
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
        fm = self.settings.get("formats", [".cbz", ".epub"])
        self.fmt = {e: tk.BooleanVar(value=e in fm) for e in converter.FORMATS}
        for e in converter.FORMATS:
            ttk.Checkbutton(frow, text=e[1:].upper(), variable=self.fmt[e]).pack(side="left", padx=(0, 14))
        ttk.Label(main, text="Kindle and reMarkable always get a PDF too, because they cannot open "
                  "CBZ or EPUB files copied over a cable.", foreground="#555",
                  wraplength=640, justify="left").pack(anchor="w", padx=px)

        # ----- output folder -----
        ttk.Label(main, text="Save to", font=("Helvetica", 12, "bold")).pack(
            anchor="w", padx=px, pady=(14, 0))
        orow = ttk.Frame(main)
        orow.pack(fill="x", padx=px, pady=(0, 12))
        self.out = tk.StringVar(value=self.settings.get("out_dir") or default_out_dir())
        self.out_entry = ttk.Entry(orow, textvariable=self.out)
        self.out_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(orow, text="Choose...", command=self.choose_out).pack(side="left", padx=(8, 0))

        # ----- bottom: buttons, progress, log -----
        btns = ttk.Frame(self.bottom)
        btns.pack(fill="x", padx=px, pady=8)
        self.btn_go = ttk.Button(btns, text="Convert", command=self.start)
        self.btn_go.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=8)
        ttk.Button(btns, text="Open output folder", command=self.open_folder).pack(side="left")
        self.bar = ttk.Progressbar(self.bottom, mode="determinate", maximum=1000)
        self.bar.pack(fill="x", padx=px, pady=(2, 2))
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self.bottom, textvariable=self.status).pack(anchor="w", padx=px)
        self.log = tk.Text(self.bottom, height=7, state="disabled", wrap="word")
        self.log.pack(fill="x", padx=px, pady=(6, 14))

        # ----- drag and drop: the box and the whole window -----
        self.drop_on = False
        if dnd:
            try:
                from tkinterdnd2 import DND_FILES
                for w in (root, canvas, main, self.zone, self.lb, self.dev_lb, self.log):
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self.on_drop)
                    w.dnd_bind("<<DropEnter>>", lambda e: self._hot(True))
                    w.dnd_bind("<<DropLeave>>", lambda e: self._hot(False))
                self.drop_on = True
            except Exception:
                pass
        if not self.drop_on:
            self.say("Drag and drop is not available on this computer. Use Add files or Add a folder.")
        self.update_devices()
        self.update_books()
        root.after(100, self.pump)

    # ----- drop box drawing -----
    def _draw_zone(self):
        z = self.zone
        z.delete("all")
        w, h = z.winfo_width(), z.winfo_height()
        color = "#2a7de1" if self._zone_hot else "#8a8a8a"
        z.create_rectangle(3, 3, w - 3, h - 3, outline=color, width=2, dash=(8, 5),
                           fill="#e8f1fc" if self._zone_hot else "")
        z.create_text(w // 2, h // 2, text=DROP_TEXT, fill="#333", justify="center",
                      font=("Helvetica", 13))

    def _hot(self, on):
        self._zone_hot = on
        self._draw_zone()

    # ----- adding books -----
    def on_drop(self, event):
        self._hot(False)
        data = event.data or ""
        items = list(self.root.tk.splitlist(data))
        self.add_paths(items)
        return getattr(event, "action", None)

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Choose pictures, PDFs or CBZ files",
                                            filetypes=PICK_TYPES)
        if paths:
            self.add_paths(list(paths))

    def add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder of pictures")
        if d:
            self.add_paths([d])

    def add_paths(self, paths):
        books, skipped = converter.collect(paths)
        known = {(b.kind, tuple(b.items)) for b in self.books}
        new = [b for b in books if (b.kind, tuple(b.items)) not in known]
        self.books.extend(new)
        self.update_books()
        if new:
            self.say(f"Added {len(new)} book{'s' if len(new) != 1 else ''}.")
        if skipped:
            self.say(f"Skipped {len(skipped)} item(s) that are not pictures, PDF, CBZ or folders: "
                     + ", ".join(os.path.basename(s) for s in skipped[:4]) + (" ..." if len(skipped) > 4 else ""))
        if not new and not skipped:
            self.say("Nothing new to add (no pictures, PDF or CBZ found, or already in the list).")
        return new

    def update_books(self):
        self.lb.delete(0, "end")
        for b in self.books:
            self.lb.insert("end", b.describe())
        n = len(self.books)
        self.count.set(f"Books to make: {n}" if n else "Books to make: none yet - drop something above")

    def remove_selected(self):
        for i in reversed(self.lb.curselection()):
            del self.books[i]
        self.update_books()

    def clear_books(self):
        self.books = []
        self.update_books()

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
        d = filedialog.askdirectory(initialdir=self.out.get() or os.path.expanduser("~"))
        if d:
            self.out.set(d)

    def open_folder(self):
        d = self.out.get()
        os.makedirs(d, exist_ok=True)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", d])
            elif os.name == "nt":
                os.startfile(d)  # noqa
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            self.say(f"Could not open the folder: {e}")

    # ----- log and progress (worker thread talks through the queue) -----
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
                elif kind == "done":
                    self.btn_go.config(state="normal")
                    self.btn_stop.config(state="disabled")
        except queue.Empty:
            pass
        try:
            self.root.after(100, self.pump)
        except tk.TclError:
            pass

    # ----- converting -----
    def on_stop(self):
        self.stop.set()
        self.q.put(("status", "Stopping after this page..."))

    def start(self):
        keys = self.device_keys()
        custom = None
        if "custom" in keys:
            custom = self.custom_info()
            if not custom:
                self.say("Type a custom size in pixels first (for example 1072 wide x 1448 tall).")
                return
        if not self.books:
            self.say("Drop some pictures, PDFs, CBZ files or folders into the box first.")
            return
        if not keys:
            self.say("Tick at least one device.")
            return
        if not self.formats():
            self.say("Tick at least one file type: CBZ, EPUB or PDF.")
            return
        out = self.out.get().strip() or default_out_dir()
        self.save_all()
        self.stop.clear()
        self.btn_go.config(state="disabled")
        self.btn_stop.config(state="normal")
        books = [converter.Book(b.name, b.kind, list(b.items)) for b in self.books]
        self.worker = threading.Thread(target=self.run, args=(books, keys, self.formats(), out, custom),
                                       daemon=True)
        self.worker.start()

    def run(self, books, keys, formats, out, custom):
        try:
            self.say(f"Making {len(books)} book(s) for {len(keys)} device(s)...")
            res = converter.convert(books, keys, formats, out, custom, self.progress, self.say, self.stop)
            if res:
                total = sum(r["screens"] for r in res)
                clean = total - sum(r["bad"] for r in res)
                self.say(f"Done: {len(res)} set(s) of files in {out}. Snug-fit check: "
                         f"{clean} of {total} screens are clean.")
                shown = set()
                for r in res:
                    if r["folder"] not in shown:
                        shown.add(r["folder"])
                        self.say("Next - " + devices.next_steps(r["kind"], r["folder"]))
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
    """Used by the build: proves the packaged app can convert pictures, a PDF and a CBZ into
    every file type and open its window with drag and drop."""
    try:
        converter.selftest()
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


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(sys.argv[sys.argv.index("--selftest") + 1])
    r, has_dnd = make_root()
    App(r, has_dnd)
    r.mainloop()
