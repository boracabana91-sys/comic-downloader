"""Comic Downloader - paste a chapter link, get images saved in folders of 5 pages."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core


class App:
    def __init__(self, root):
        self.root = root
        root.title("Comic Downloader")
        root.geometry("680x520")
        root.minsize(600, 460)
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

        btns = ttk.Frame(root)
        btns.pack(fill="x", padx=14, pady=4)
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

    def open_folder(self):
        d = self.folder.get()
        os.makedirs(d, exist_ok=True)
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
        self.stop.clear()
        self.btn_go.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.bar["value"] = 0
        self.worker = threading.Thread(
            target=self.run, args=(link, self.folder.get(), size, self.convert.get()), daemon=True)
        self.worker.start()

    def progress(self, done, total, text):
        self.q.put(("progress", done, total))
        self.q.put(("status", text))

    def run(self, link, out_root, size, convert):
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
            self.q.put(("status", f"All done. Saved in {out_root}"))
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
        result = "OK"
    except Exception as e:
        result = f"FAIL {e}"
    with open(path, "w") as f:
        f.write(result)
    sys.exit(0 if result == "OK" else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(sys.argv[sys.argv.index("--selftest") + 1])
    r = tk.Tk()
    App(r)
    r.mainloop()
