"""Comic Downloader - paste a chapter link, get images saved in folders of 5 pages."""
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

# A windowed app on Windows has no console; some libraries write to it and would crash.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


class App:
    def __init__(self, root, dnd=False):
        self.root = root
        root.title("Comic Downloader")
        root.geometry("720x720")
        root.minsize(640, 640)
        self.cover_path = None
        self._photo = None
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.worker = None

        pad = {"padx": 14, "pady": 6}
        ttk.Label(root, text="Comic Downloader",
                  font=("Helvetica", 18, "bold")).pack(anchor="w", padx=14, pady=(14, 0))
        ttk.Label(root, text="Paste the link of the chapter page, choose a folder, press Download.",
                  foreground="#555").pack(anchor="w", padx=14)

        ttk.Label(root, text="Chapter link").pack(anchor="w", **pad)
        row = ttk.Frame(root)
        row.pack(fill="x", padx=14)
        self.url = tk.StringVar()
        ttk.Entry(row, textvariable=self.url).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Paste", command=self.paste).pack(side="left", padx=(8, 0))

        ttk.Label(root, text="Save to folder").pack(anchor="w", **pad)
        row2 = ttk.Frame(root)
        row2.pack(fill="x", padx=14)
        self.folder = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "Comics"))
        ttk.Entry(row2, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Choose folder", command=self.choose).pack(side="left", padx=(8, 0))

        opts = ttk.Frame(root)
        opts.pack(fill="x", padx=14, pady=8)
        ttk.Label(opts, text="Pages per folder:").pack(side="left")
        self.size = tk.IntVar(value=5)
        ttk.Spinbox(opts, from_=1, to=50, width=4, textvariable=self.size).pack(side="left", padx=6)
        self.convert = tk.BooleanVar(value=False)
        if core.HAS_PIL:
            ttk.Checkbutton(opts, text="Convert WebP to JPG",
                            variable=self.convert).pack(side="left", padx=18)

        hide_row = ttk.Frame(root)
        hide_row.pack(fill="x", padx=14, pady=(0, 6))
        self.hide = tk.BooleanVar(value=True)
        self.hide_box = ttk.Checkbutton(hide_row, text="Hide these words on the pages:",
                                        variable=self.hide)
        self.hide_box.pack(side="left")
        self.words = tk.StringVar(value="luacomic.org")
        ttk.Entry(hide_row, textvariable=self.words, width=34).pack(side="left", padx=6)
        if not cleaner.ocr_available():
            self.hide.set(False)
            self.hide_box.config(state="disabled")

        cover_row = ttk.Frame(root)
        cover_row.pack(fill="x", padx=14, pady=(0, 8))
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
                  wraplength=360).pack(anchor="w", pady=(6, 0))
        if dnd:
            try:
                from tkinterdnd2 import DND_FILES
                self.zone.drop_target_register(DND_FILES)
                self.zone.dnd_bind("<<Drop>>", self.on_drop)
            except Exception:
                pass  # the Choose cover button still works

        send = ttk.Frame(root)
        send.pack(fill="x", padx=14, pady=(0, 6))
        ttk.Label(send, text="Send to:").pack(side="left")
        self.device_labels = [core.DEVICES[k]["label"] for k in core.DEVICE_KEYS]
        self.device = tk.StringVar(value=self.device_labels[0])
        box = ttk.Combobox(send, textvariable=self.device, values=self.device_labels,
                           state="readonly", width=58)
        box.pack(side="left", padx=6)
        if not core.HAS_PIL:
            box.config(state="disabled")
        box.bind("<<ComboboxSelected>>", lambda e: self.update_custom())

        # Extra boxes that only appear for "Custom size"
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

        btns = ttk.Frame(root)
        btns.pack(fill="x", padx=14, pady=4)
        self.btns = btns
        self.btn_go = ttk.Button(btns, text="Download", command=self.start)
        self.btn_go.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=8)
        ttk.Button(btns, text="Open folder", command=self.open_folder).pack(side="left")

        self.bar = ttk.Progressbar(root, mode="determinate")
        self.bar.pack(fill="x", padx=14, pady=(10, 2))
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(root, textvariable=self.status).pack(anchor="w", padx=14)

        self.log = tk.Text(root, height=10, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=14, pady=(8, 14))
        root.after(100, self.pump)

    # ----- small helpers -----
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
            from PIL import Image, ImageTk
            im = covers.load_cover(path)
            im.thumbnail((150, 150))
            self._photo = ImageTk.PhotoImage(im)
            self.zone.config(image=self._photo, text="", width=self._photo.width(),
                             height=self._photo.height())
        except Exception:
            pass  # no preview, but the cover is still used
        self.cover_path = path
        self.cover_note.set(f"Cover: {os.path.basename(path)}\nIt is used for every download "
                            "until you press Clear cover.")

    def clear_cover(self):
        self.cover_path = None
        self._photo = None
        self.zone.config(image="", text="Drop your cover picture here\n(or click to choose)",
                         width=30, height=5)
        self.cover_note.set("No cover picture chosen.")

    def update_custom(self):
        if self.device_key() == "custom":
            self.custom_row.pack(fill="x", padx=14, pady=(0, 6), before=self.btns)
        else:
            self.custom_row.pack_forget()

    def custom_info(self):
        """The typed-in screen size, or None if it is not a sensible number."""
        try:
            w, h = int(self.c_w.get()), int(self.c_h.get())
        except ValueError:
            return None
        if not (300 <= w <= 4000 and 400 <= h <= 5000):
            return None
        return {"width": w, "height": h, "ext": self.c_ext.get(), "gray": self.c_gray.get()}

    def open_folder(self):
        d = self.folder.get()
        os.makedirs(d, exist_ok=True)
        key = self.device_key()
        if key != "images":  # open the folder holding the files to drag onto the e-reader
            sub = os.path.join(d, core.DEVICES[key]["folder"])
            if os.path.isdir(sub):
                d = sub
        if sys.platform == "darwin":
            subprocess.Popen(["open", d])
        elif sys.platform.startswith("win"):
            os.startfile(d)  # noqa
        else:
            subprocess.Popen(["xdg-open", d])

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
                elif kind == "done":
                    self.btn_go.config(state="normal")
                    self.btn_stop.config(state="disabled")
                elif kind == "ask":
                    a()
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    # ----- actions -----
    def on_stop(self):
        self.stop.set()
        self.status.set("Stopping...")

    def start(self):
        link = self.url.get().strip()
        if not link.lower().startswith("http"):
            messagebox.showinfo("Link needed", "Please paste the full link, starting with https://")
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
                                    "(400 to 5000) in pixels. You can find it in your gadget's "
                                    "specifications.")
                return
        words = cleaner.parse_words(self.words.get()) if self.hide.get() else []
        cover = self.cover_path if self.cover_path and os.path.isfile(self.cover_path) else None
        self.stop.clear()
        self.btn_go.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.bar["value"] = 0
        self.worker = threading.Thread(
            target=self.run,
            args=(link, self.folder.get(), size, self.convert.get(), self.device_key(), custom,
                  words, cover),
            daemon=True)
        self.worker.start()

    def progress(self, done, total, text):
        self.q.put(("progress", done, total))
        self.q.put(("status", text))

    def run(self, link, out_root, size, convert, device="images", custom=None, words=None,
            cover=None):
        try:
            os.makedirs(out_root, exist_ok=True)
            self.say("Reading the page...")
            info = core.inspect_page(link)
            targets = []
            if len(info["images"]) >= 3 or not info["chapters"]:
                if not info["images"]:
                    raise core.NoImages()
                targets = [(link, info["title"], info["images"])]
            else:
                n = len(info["chapters"])
                answer = {}
                ev = threading.Event()

                def ask():
                    answer["v"] = messagebox.askyesno(
                        "Whole series?",
                        f"This looks like a series page with {n} chapters.\n\n"
                        "Download ALL chapters?\n(Choose No and paste a single chapter link instead.)")
                    ev.set()
                self.q.put(("ask", ask))
                ev.wait()
                if not answer.get("v"):
                    self.say("Cancelled. Paste a single chapter link and try again.")
                    return
                for i, cu in enumerate(info["chapters"], 1):
                    if self.stop.is_set():
                        raise core.Stopped()
                    self.say(f"Reading chapter {i} of {n}...")
                    try:
                        ci = core.inspect_page(cu)
                        if ci["images"]:
                            targets.append((cu, ci["title"], ci["images"]))
                    except Exception as e:
                        self.say(f"  Skipped a chapter ({e}).")
            for cu, title, imgs in targets:
                self.say(f"{title}: {len(imgs)} pages found.")
                failed = core.download_images(imgs, title, out_root, cu, self.progress,
                                              self.stop, size, convert)
                if failed:
                    self.say(f"  Pages that failed: {failed}. Press Download again to retry them.")
                else:
                    self.say(f"  Done: {title}")
                if words:
                    self.q.put(("status", "Loading the text reader..."))
                    try:
                        counts = cleaner.clean_chapter(out_root, title, len(imgs), size, words,
                                                       self.progress, self.stop)
                        hidden = counts["cut"] + counts["blurred"] + counts["deleted"]
                        if counts["scanned"]:
                            self.say(f"  Looked for the words on {counts['scanned']} page(s) "
                                     f"and hid them on {hidden}.")
                    except core.Stopped:
                        raise
                    except Exception as e:
                        self.say(f"  Could not look for the words ({e}). Continuing without it.")
                if cover:
                    try:
                        res = covers.apply_folder_covers(out_root, title, len(imgs), size, cover)
                        msg = f"  Cover picture saved in {res['folders']} folder(s)"
                        if res["icons"]:
                            msg += f", and {res['icons']} folder(s) now show it as their thumbnail"
                        self.say(msg + ".")
                        if res["problems"]:
                            self.say(f"  Some folders could not get the cover: {res['problems'][0]}")
                    except Exception as e:
                        self.say(f"  Could not add the cover to the folders ({e}).")
                if device != "images":
                    made, bad = core.build_device_files(out_root, title, len(imgs), size, device,
                                                        self.progress, self.stop, custom, cover)
                    dev = core.resolve_device(device, custom)
                    self.say(f"  Made {len(made)} {dev['ext']} file(s) in the folder '{dev['folder']}'.")
                    if bad:
                        self.say(f"  {len(bad)} image(s) could not be used and were skipped.")
            self.q.put(("status", f"All done. Saved in {out_root}"))
            if device != "images":
                self.say(core.resolve_device(device, custom)["next"])
        except core.Stopped:
            self.q.put(("status", "Stopped."))
            self.say("Stopped. Press Download again to continue where it left off.")
        except core.NoImages:
            self.q.put(("status", "No images found."))
            self.say("No images found on that page. Make sure the link is a chapter page, "
                     "then try again. If it keeps happening, send the link to your developer.")
        except Exception as e:
            self.q.put(("status", "Something went wrong."))
            msg = str(e)
            if "HTTP Error 403" in msg or "HTTP Error 401" in msg:
                msg += " (the website refused the program; send this message to your developer)"
            elif "CERTIFICATE" in msg.upper():
                msg += " (secure connection problem; send this message to your developer)"
            elif "urlopen error" in msg:
                msg += " (check your internet connection and the link)"
            self.say(f"Error: {msg}")
        finally:
            self.q.put(("done", None))


def selftest(path):
    """Used by the build: opens a secure (https) page from the packaged app itself."""
    try:
        core.fetch_text("https://github.com")
        core.selftest_device()
        if cleaner.ocr_available():
            cleaner.selftest()
        else:
            raise RuntimeError("the text reader is missing from this app")
        root, dnd = make_root()  # proves the drag-and-drop tool loads inside the packaged app
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
    """The window, with drag and drop if the tool is available. Returns (window, has_dnd)."""
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk(), True
    except Exception:
        return tk.Tk(), False


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(sys.argv[sys.argv.index("--selftest") + 1])
    r, has_dnd = make_root()
    App(r, has_dnd)
    r.mainloop()
