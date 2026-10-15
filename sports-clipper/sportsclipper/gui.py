"""Sports Clipper window (same simple layout as Comic Downloader: sections top to bottom)."""
from __future__ import annotations
import os
import queue
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from datetime import datetime

import subprocess
import sys

from . import checks, config, job, pipeline, progress, results, rights, sources

RES = [2160, 1080, 720, 480, 360]


class App:
    def __init__(self, root):
        self.root = root
        root.title("Sports Clipper")
        root.geometry("920x860")
        root.minsize(640, 420)
        self.cfg = config.load()
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        pad = {"padx": 14, "pady": 4}

        # everything below goes on one scrollable page: resize the window and nothing gets cut off
        outer = ttk.Frame(root); outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        page = ttk.Frame(canvas)
        page_id = canvas.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(page_id, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        ttk.Label(page, text="Sports Clipper", font=("Helvetica", 18, "bold")).pack(anchor="w", padx=14, pady=(14, 0))
        ttk.Label(page, text="Watches your licensed sources, cuts out the dead time, makes every resolution, and posts.",
                  foreground="#555").pack(anchor="w", padx=14)

        # --- sources: paste a link, nothing else to fill in
        ttk.Label(page, text="Add a channel - paste its YouTube link").pack(anchor="w", **pad)
        form = ttk.Frame(page); form.pack(fill="x", padx=14)
        self.s_link = tk.StringVar()
        ttk.Entry(form, textvariable=self.s_link).pack(side="left", fill="x", expand=True)
        ttk.Button(form, text="Paste", command=self.paste_link).pack(side="left", padx=6)
        ttk.Button(form, text="Add channel", command=self.add_source).pack(side="left")
        ttk.Label(page, text="Example: https://www.youtube.com/@ChannelName  - the name and channel ID are found automatically.",
                  foreground="#777").pack(anchor="w", padx=14)
        self.s_lic = tk.BooleanVar(value=False)
        ttk.Checkbutton(page, text="I own this channel or have permission / a license to use its videos",
                        variable=self.s_lic).pack(anchor="w", padx=14, pady=(4, 0))
        self.tree = ttk.Treeview(page, columns=("name", "id", "lic"), show="headings", height=4)
        for c, t, w in (("name", "Channel", 330), ("id", "Channel ID", 300), ("lic", "Permission", 90)):
            self.tree.heading(c, text=t); self.tree.column(c, width=w)
        self.tree.pack(fill="x", padx=14, pady=4)
        ttk.Button(page, text="Remove selected channel", command=self.remove_source).pack(anchor="w", padx=14)

        # --- pick one video from a channel to reclip
        vf = ttk.LabelFrame(page, text="Pick a video from the selected channel")
        vf.pack(fill="x", padx=14, pady=4)
        vb = ttk.Frame(vf); vb.pack(fill="x", padx=6, pady=4)
        ttk.Button(vb, text="Scan selected channel", command=self.scan_channel).pack(side="left")
        ttk.Button(vb, text="Reclip selected video", command=self.reclip_selected).pack(side="left", padx=6)
        self.vid_tree = ttk.Treeview(vf, columns=("title", "date"), show="headings", height=5)
        self.vid_tree.heading("title", text="Title"); self.vid_tree.column("title", width=560)
        self.vid_tree.heading("date", text="Posted"); self.vid_tree.column("date", width=140)
        self.vid_tree.pack(fill="x", padx=6, pady=(0, 6))
        self.vid_items = {}

        # --- schedule
        ttk.Label(page, text="When to scan").pack(anchor="w", **pad)
        sc = ttk.Frame(page); sc.pack(fill="x", padx=14)
        s = self.cfg["schedule"]
        self.mode = tk.StringVar(value=s["mode"]); self.hours = tk.DoubleVar(value=s["hours"])
        self.times = tk.StringVar(value=", ".join(s["times"]))
        ttk.Radiobutton(sc, text="Every", value="interval", variable=self.mode).pack(side="left")
        ttk.Spinbox(sc, from_=0.25, to=24, increment=0.25, width=5, textvariable=self.hours).pack(side="left", padx=4)
        ttk.Label(sc, text="hours     ").pack(side="left")
        ttk.Radiobutton(sc, text="At these times (HH:MM, comma separated):", value="times", variable=self.mode).pack(side="left")
        ttk.Entry(sc, textvariable=self.times, width=22).pack(side="left", padx=6)
        dl = ttk.Frame(page); dl.pack(fill="x", padx=14, pady=4)
        lo, hi = self.cfg["publish_delay_min"]
        self.dlo = tk.IntVar(value=lo); self.dhi = tk.IntVar(value=hi)
        ttk.Label(dl, text="Post").pack(side="left")
        ttk.Spinbox(dl, from_=0, to=120, width=4, textvariable=self.dlo).pack(side="left", padx=4)
        ttk.Label(dl, text="to").pack(side="left")
        ttk.Spinbox(dl, from_=0, to=120, width=4, textvariable=self.dhi).pack(side="left", padx=4)
        ttk.Label(dl, text="minutes after the source was published").pack(side="left")

        # --- output
        ttk.Label(page, text="Output").pack(anchor="w", **pad)
        row = ttk.Frame(page); row.pack(fill="x", padx=14)
        self.out = tk.StringVar(value=self.cfg["output_dir"])
        ttk.Entry(row, textvariable=self.out).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Choose folder", command=self.pick_out).pack(side="left", padx=(8, 0))
        rr = ttk.Frame(page); rr.pack(fill="x", padx=14, pady=4)
        self.res = {h: tk.BooleanVar(value=h in self.cfg["resolutions"]) for h in RES}
        for h in RES:
            ttk.Checkbutton(rr, text="4K" if h == 2160 else f"{h}p", variable=self.res[h]).pack(side="left", padx=(0, 10))
        self.ratio = tk.IntVar(value=int(self.cfg["target_ratio"] * 100))
        ttk.Label(rr, text="   Keep about").pack(side="left")
        ttk.Spinbox(rr, from_=20, to=100, width=4, textvariable=self.ratio).pack(side="left", padx=4)
        ttk.Label(rr, text="% of the video (Highlights: the final length)").pack(side="left")
        self.hl = tk.BooleanVar(value=bool(self.cfg.get("highlights", False)))
        hlf = ttk.Frame(page); hlf.pack(fill="x", padx=14, pady=(2, 0))
        ttk.Checkbutton(hlf, text="Highlights", variable=self.hl).pack(side="left")
        ttk.Label(hlf, text="  dead time out (intro, timeouts, free throws, post-game), then whole chunks of play spread evenly to reach the length. Game order, normal speed.",
                  foreground="#555").pack(side="left")
        ttk.Label(page, text="Sizes above the source are upscaled and marked 'upscaled': sharper than a plain stretch, but not real extra detail.",
                  foreground="#777").pack(anchor="w", padx=14)

        # --- YouTube
        ttk.Label(page, text="YouTube upload").pack(anchor="w", **pad)
        yt = ttk.Frame(page); yt.pack(fill="x", padx=14)
        self.up_on = tk.BooleanVar(value=self.cfg["upload"]["enabled"])
        self.secret = tk.StringVar(value=self.cfg["upload"]["client_secret"])
        ttk.Checkbutton(yt, text="Upload to our channel. Google client_secret.json:", variable=self.up_on).pack(side="left")
        ttk.Entry(yt, textvariable=self.secret).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(yt, text="Choose", command=self.pick_secret).pack(side="left")
        ex = ttk.Frame(page); ex.pack(fill="x", padx=14, pady=4)
        self.ai_on = tk.BooleanVar(value=self.cfg["ai"]["enabled"]); self.cl_on = tk.BooleanVar(value=self.cfg["cloudinary"]["enabled"])
        self.th_on = tk.BooleanVar(value=self.cfg["thumbnail"]["enabled"])
        ttk.Checkbutton(ex, text="Write titles with Claude Haiku 5.5 (key goes in config.json)", variable=self.ai_on).pack(side="left")
        ttk.Checkbutton(ex, text="Back up to Cloudinary (set keys in config.json)", variable=self.cl_on).pack(side="left", padx=14)
        ttk.Checkbutton(ex, text="Auto thumbnail", variable=self.th_on).pack(side="left", padx=14)

        # --- buttons
        bb = ttk.Frame(page); bb.pack(fill="x", padx=14, pady=8)
        self.start_btn = ttk.Button(bb, text="Start 24/7", command=self.start); self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(bb, text="Stop", command=self.stop_now, state="disabled"); self.stop_btn.pack(side="left", padx=6)
        ttk.Button(bb, text="Scan now", command=self.scan_now).pack(side="left", padx=6)
        ttk.Button(bb, text="Test on a video file...", command=self.test_file).pack(side="left", padx=6)
        ttk.Button(bb, text="Save settings", command=self.save).pack(side="left", padx=6)
        ttk.Button(bb, text="Check setup", command=self.check_setup).pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="Idle - nothing running")
        ttk.Label(page, textvariable=self.status_var, font=("Helvetica", 12, "bold")).pack(anchor="w", padx=14, pady=(6, 0))
        self.bar = ttk.Progressbar(page, mode="indeterminate", maximum=100); self.bar.pack(fill="x", padx=14)
        progress.listen(lambda text, pct: self.q.put(("__status__", text, pct)))
        self.logbox = tk.Text(page, height=12, wrap="word", state="disabled"); self.logbox.pack(fill="both", expand=True, padx=14, pady=8)
        # --- results: thumbnail and video outputs
        res = ttk.LabelFrame(page, text="Results: thumbnail and video outputs")
        res.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        left = ttk.Frame(res); left.pack(side="left", fill="y", padx=6, pady=6)
        self.res_tree = ttk.Treeview(left, columns=("title", "sizes"), show="headings", height=7)
        self.res_tree.heading("title", text="Clip"); self.res_tree.column("title", width=280)
        self.res_tree.heading("sizes", text="Sizes"); self.res_tree.column("sizes", width=120)
        self.res_tree.pack()
        self.res_tree.bind("<<TreeviewSelect>>", self.show_result)
        right = ttk.Frame(res); right.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.preview = ttk.Label(right, text="Pick a clip on the left", anchor="center")
        self.preview.pack(fill="both", expand=True)
        btns = ttk.Frame(right); btns.pack(pady=6)
        ttk.Button(btns, text="Open thumbnail", command=lambda: self.open_selected("thumb")).pack(side="left", padx=4)
        ttk.Button(btns, text="Open video (upload size)", command=lambda: self.open_selected("video")).pack(side="left", padx=4)
        ttk.Button(btns, text="Show folder", command=lambda: self.open_selected("folder")).pack(side="left", padx=4)
        ttk.Button(btns, text="Refresh", command=self.refresh_results).pack(side="left", padx=4)
        self.result_items = {}
        self._photo = None
        self.refresh_results()

        self.refresh_tree()
        self.root.after(200, self.pump)
        self.root.after(1000, self._status_loop)

    def _status_loop(self):
        self._refresh_status()
        self.root.after(1000, self._status_loop)

    def _refresh_status(self):
        if not self.worker or not self.worker.is_alive() or not hasattr(self, "st"):
            return
        el = int(time.time() - self.job_t0)
        text, pct = self.st
        pc = f" - {pct}%" if pct is not None else ""
        self.status_var.set(f"{text}{pc}   |   elapsed {el // 60}:{el % 60:02d}   |   last update {int(time.time() - self.st_t)}s ago")

    # ---- helpers
    def log(self, m): self.q.put(m)

    def pump(self):
        try:
            while True:
                m = self.q.get_nowait()
                if isinstance(m, tuple) and m[0] == "__add__":
                    self.cfg["sources"].append(m[1]); self.refresh_tree(); self.save()
                    self.s_link.set(""); self.s_lic.set(False)
                    self.log(f"added channel: {m[1]['name']} ({m[1]['location']})")
                    continue
                if isinstance(m, tuple) and m[0] == "__error__":
                    messagebox.showerror(m[1], m[2])
                    continue
                if isinstance(m, tuple) and m[0] == "__status__":
                    self.st, self.st_t = (m[1], m[2]), time.time()
                    if m[2] is not None:
                        self.bar.stop(); self.bar.config(mode="determinate", value=m[2])
                    continue
                if isinstance(m, tuple) and m[0] == "__videos__":
                    self.vid_tree.delete(*self.vid_tree.get_children()); self.vid_items = {}
                    for i, v in enumerate(m[1]):
                        self.vid_items[str(i)] = v
                        self.vid_tree.insert("", "end", iid=str(i), values=(v.title, v.published.astimezone().strftime("%Y-%m-%d %H:%M")))
                    continue
                if m == "\0done":
                    self.bar.stop(); self.bar.config(mode="determinate", value=0)
                    self.status_var.set("Finished - see Results below, or the log for details")
                    self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); self.refresh_results(); continue
                self.logbox.config(state="normal"); self.logbox.insert("end", m + "\n"); self.logbox.see("end"); self.logbox.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(200, self.pump)

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for d in self.cfg["sources"]:
            self.tree.insert("", "end", values=(d["name"], d["location"],
                                                "yes" if d.get("licensed") and d.get("license_note") else "NO"))

    def paste_link(self):
        try:
            self.s_link.set(self.root.clipboard_get().strip())
        except tk.TclError:
            pass

    def add_source(self):
        if not self.s_lic.get():
            return messagebox.showwarning("Add channel", "Tick the box first: you own the channel or have permission to use its videos.")
        link = self.s_link.get()
        self.log("looking up the channel ...")
        def job():
            try:
                info = sources.resolve_youtube(link)
            except Exception as e:
                self.q.put(f"could not add the channel: {e}")
                return
            note = f"Owner confirmed in the app on {datetime.now():%Y-%m-%d}"
            self.q.put(("__add__", rights.Source(info["name"], "youtube", info["location"], True, note).to_dict()))
        threading.Thread(target=job, daemon=True).start()

    def remove_source(self):
        for i in sorted((self.tree.index(x) for x in self.tree.selection()), reverse=True):
            del self.cfg["sources"][i]
        self.refresh_tree(); self.save()

    def _channel_src(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Channel", "Click a channel in the list first.")
            return None
        return rights.Source.from_dict(self.cfg["sources"][self.tree.index(sel[0])])

    def scan_channel(self):
        src = self._channel_src()
        if not src:
            return
        self.log(f"scanning {src.name} ...")
        def job():
            try:
                vids = sources.list_videos(src, 25)
                self.q.put(("__videos__", vids))
                self.log(f"found {len(vids)} video(s) on {src.name} - click one, then Reclip selected video")
            except Exception as e:
                self.log(f"scan failed: {e}")
        threading.Thread(target=job, daemon=True).start()

    def reclip_selected(self):
        sel = self.vid_tree.selection()
        if not sel:
            return messagebox.showinfo("Reclip", "Scan a channel and click a video first.")
        src = self._channel_src()
        if not src:
            return
        v = self.vid_items[sel[0]]
        self.log(f"reclipping: {v.title}")
        def fn():
            try:
                pipeline.Pipeline(config.load(), self.log, self.stop).process(src, v)
                self.log("done: " + v.title)
            except Exception as e:
                msg = str(e)[:800]
                self.log(f"RECLIP FAILED: {msg}")
                self.q.put(("__error__", "Reclip failed", msg))   # pop-ups only from the main thread (macOS crash fix)
        self._go(fn)

    def check_setup(self):
        self._go(lambda: checks.run(config.load(), self.log))

    def pick_out(self):
        d = filedialog.askdirectory()
        if d: self.out.set(d)

    def pick_secret(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if f: self.secret.set(f)

    def save(self):
        c = self.cfg
        c["schedule"] = {"mode": self.mode.get(), "hours": float(self.hours.get()),
                         "times": [t.strip() for t in self.times.get().split(",") if t.strip()]}
        c["publish_delay_min"] = [int(self.dlo.get()), max(int(self.dlo.get()), int(self.dhi.get()))]
        c["output_dir"] = self.out.get()
        c["resolutions"] = [h for h in RES if self.res[h].get()] or [1080]
        c["target_ratio"] = max(0.2, min(1.0, self.ratio.get() / 100))
        c["highlights"] = self.hl.get()
        c["upload"]["enabled"] = self.up_on.get(); c["upload"]["client_secret"] = self.secret.get()
        c["ai"]["enabled"] = self.ai_on.get(); c["cloudinary"]["enabled"] = self.cl_on.get(); c["thumbnail"]["enabled"] = self.th_on.get()
        config.save(c)

    # ---- actions
    def _go(self, fn):
        if self.worker and self.worker.is_alive():
            return
        self.save(); self.stop.clear()
        self.bar.stop(); self.bar.config(mode="indeterminate"); self.bar.start(12)
        self.job_t0 = time.time(); self.st = ("starting", None); self.st_t = time.time()
        self.start_btn.config(state="disabled"); self.stop_btn.config(state="normal")
        def job():
            try:
                fn()
            except Exception as e:
                self.log(f"ERROR: {e}")
            self.q.put("\0done")
        self.worker = threading.Thread(target=job, daemon=True); self.worker.start()

    def start(self):
        self._go(lambda: pipeline.Pipeline(config.load(), self.log, self.stop).run_forever())

    def scan_now(self):
        self._go(lambda: self.log(f"done: {pipeline.Pipeline(config.load(), self.log, self.stop).scan_once()} new video(s)"))

    def stop_now(self):
        self.stop.set(); self.log("stopping after the current step ...")

    def test_file(self):
        f = filedialog.askopenfilename(
            title="Choose a video to test (click the file, then Open)",
            initialdir=os.path.expanduser("~/Downloads"),
            filetypes=[("Video", "*.mp4 *.mov *.mkv *.m4v *.webm"), ("All files", "*")])
        if not f:
            return
        title = os.path.splitext(os.path.basename(f))[0]
        self.log(f"testing: {os.path.basename(f)}")
        def fn():
            try:
                r = job.clip_file(f, config.load(), title, self.log)
                self.log("done. Sizes: " + ", ".join(f"{h}p" for h in sorted(r["outputs"], reverse=True))
                         + ("  + thumbnail" if r["thumb"] else ""))
            except Exception as e:
                msg = str(e)[:800]
                self.log(f"TEST FAILED: {msg}")
                self.q.put(("__error__", "Test failed", msg))
        self._go(fn)

    def refresh_results(self):
        self.res_tree.delete(*self.res_tree.get_children())
        self.result_items = {}
        for i, r in enumerate(results.scan_outputs(config.load()["output_dir"])):
            iid = str(i)
            self.res_tree.insert("", "end", iid=iid, values=(r["title"], ", ".join(f"{h}p" for h, _ in r["videos"])))
            self.result_items[iid] = r

    def _selected(self):
        sel = self.res_tree.selection()
        return self.result_items.get(sel[0]) if sel else None

    def show_result(self, _=None):
        r = self._selected()
        if not r:
            return
        if r["thumb"]:
            from PIL import Image, ImageTk
            im = Image.open(r["thumb"]); im.thumbnail((720, 405))
            self._photo = ImageTk.PhotoImage(im)
            self.preview.config(image=self._photo, text="")
        else:
            self._photo = None
            self.preview.config(image="", text="No thumbnail for this clip")

    def open_selected(self, what):
        r = self._selected()
        if not r:
            return messagebox.showinfo("Results", "Pick a clip on the left first.")
        if what == "thumb":
            path = r["thumb"]
        elif what == "video":
            want = config.load().get("upload_resolution", 1080)     # not the 4K: that one is huge
            path = min(r["videos"], key=lambda v: (abs(v[0] - want), -v[0]))[1] if r["videos"] else None
        else:
            path = r["folder"]
        if not path:
            return messagebox.showinfo("Results", "That file is not there.")
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


def main() -> int:
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
