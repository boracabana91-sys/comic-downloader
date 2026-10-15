"""Sports Clipper window (same simple layout as Comic Downloader: sections top to bottom)."""
from __future__ import annotations
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from datetime import datetime

from . import analyze, checks, config, pipeline, render, rights, sources

RES = [2160, 1080, 720, 480, 360]


class App:
    def __init__(self, root):
        self.root = root
        root.title("Sports Clipper")
        root.geometry("900x980")
        root.minsize(760, 760)
        self.cfg = config.load()
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        pad = {"padx": 14, "pady": 4}

        ttk.Label(root, text="Sports Clipper", font=("Helvetica", 18, "bold")).pack(anchor="w", padx=14, pady=(14, 0))
        ttk.Label(root, text="Watches your licensed sources, cuts out the dead time, makes every resolution, and posts.",
                  foreground="#555").pack(anchor="w", padx=14)

        # --- sources: paste a link, nothing else to fill in
        ttk.Label(root, text="Add a channel - paste its YouTube link").pack(anchor="w", **pad)
        form = ttk.Frame(root); form.pack(fill="x", padx=14)
        self.s_link = tk.StringVar()
        ttk.Entry(form, textvariable=self.s_link).pack(side="left", fill="x", expand=True)
        ttk.Button(form, text="Paste", command=self.paste_link).pack(side="left", padx=6)
        ttk.Button(form, text="Add channel", command=self.add_source).pack(side="left")
        ttk.Label(root, text="Example: https://www.youtube.com/@ChannelName  - the name and channel ID are found automatically.",
                  foreground="#777").pack(anchor="w", padx=14)
        self.s_lic = tk.BooleanVar(value=False)
        ttk.Checkbutton(root, text="I own this channel or have permission / a license to use its videos",
                        variable=self.s_lic).pack(anchor="w", padx=14, pady=(4, 0))
        self.tree = ttk.Treeview(root, columns=("name", "id", "lic"), show="headings", height=4)
        for c, t, w in (("name", "Channel", 330), ("id", "Channel ID", 300), ("lic", "Permission", 90)):
            self.tree.heading(c, text=t); self.tree.column(c, width=w)
        self.tree.pack(fill="x", padx=14, pady=4)
        ttk.Button(root, text="Remove selected channel", command=self.remove_source).pack(anchor="w", padx=14)

        # --- schedule
        ttk.Label(root, text="When to scan").pack(anchor="w", **pad)
        sc = ttk.Frame(root); sc.pack(fill="x", padx=14)
        s = self.cfg["schedule"]
        self.mode = tk.StringVar(value=s["mode"]); self.hours = tk.DoubleVar(value=s["hours"])
        self.times = tk.StringVar(value=", ".join(s["times"]))
        ttk.Radiobutton(sc, text="Every", value="interval", variable=self.mode).pack(side="left")
        ttk.Spinbox(sc, from_=0.25, to=24, increment=0.25, width=5, textvariable=self.hours).pack(side="left", padx=4)
        ttk.Label(sc, text="hours     ").pack(side="left")
        ttk.Radiobutton(sc, text="At these times (HH:MM, comma separated):", value="times", variable=self.mode).pack(side="left")
        ttk.Entry(sc, textvariable=self.times, width=22).pack(side="left", padx=6)
        dl = ttk.Frame(root); dl.pack(fill="x", padx=14, pady=4)
        lo, hi = self.cfg["publish_delay_min"]
        self.dlo = tk.IntVar(value=lo); self.dhi = tk.IntVar(value=hi)
        ttk.Label(dl, text="Post").pack(side="left")
        ttk.Spinbox(dl, from_=0, to=120, width=4, textvariable=self.dlo).pack(side="left", padx=4)
        ttk.Label(dl, text="to").pack(side="left")
        ttk.Spinbox(dl, from_=0, to=120, width=4, textvariable=self.dhi).pack(side="left", padx=4)
        ttk.Label(dl, text="minutes after the source was published").pack(side="left")

        # --- output
        ttk.Label(root, text="Output").pack(anchor="w", **pad)
        row = ttk.Frame(root); row.pack(fill="x", padx=14)
        self.out = tk.StringVar(value=self.cfg["output_dir"])
        ttk.Entry(row, textvariable=self.out).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Choose folder", command=self.pick_out).pack(side="left", padx=(8, 0))
        rr = ttk.Frame(root); rr.pack(fill="x", padx=14, pady=4)
        self.res = {h: tk.BooleanVar(value=h in self.cfg["resolutions"]) for h in RES}
        for h in RES:
            ttk.Checkbutton(rr, text="4K" if h == 2160 else f"{h}p", variable=self.res[h]).pack(side="left", padx=(0, 10))
        self.ratio = tk.IntVar(value=int(self.cfg["target_ratio"] * 100))
        ttk.Label(rr, text="   Keep about").pack(side="left")
        ttk.Spinbox(rr, from_=20, to=100, width=4, textvariable=self.ratio).pack(side="left", padx=4)
        ttk.Label(rr, text="% of the video").pack(side="left")
        ttk.Label(root, text="Sizes above the source are upscaled and marked 'upscaled': sharper than a plain stretch, but not real extra detail.",
                  foreground="#777").pack(anchor="w", padx=14)

        # --- YouTube
        ttk.Label(root, text="YouTube upload").pack(anchor="w", **pad)
        yt = ttk.Frame(root); yt.pack(fill="x", padx=14)
        self.up_on = tk.BooleanVar(value=self.cfg["upload"]["enabled"])
        self.secret = tk.StringVar(value=self.cfg["upload"]["client_secret"])
        ttk.Checkbutton(yt, text="Upload to our channel. Google client_secret.json:", variable=self.up_on).pack(side="left")
        ttk.Entry(yt, textvariable=self.secret).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(yt, text="Choose", command=self.pick_secret).pack(side="left")
        ex = ttk.Frame(root); ex.pack(fill="x", padx=14, pady=4)
        self.ai_on = tk.BooleanVar(value=self.cfg["ai"]["enabled"]); self.cl_on = tk.BooleanVar(value=self.cfg["cloudinary"]["enabled"])
        self.th_on = tk.BooleanVar(value=self.cfg["thumbnail"]["enabled"])
        ttk.Checkbutton(ex, text="Write titles with Claude Haiku 5.5 (key goes in config.json)", variable=self.ai_on).pack(side="left")
        ttk.Checkbutton(ex, text="Back up to Cloudinary (set keys in config.json)", variable=self.cl_on).pack(side="left", padx=14)
        ttk.Checkbutton(ex, text="Auto thumbnail", variable=self.th_on).pack(side="left", padx=14)

        # --- buttons
        bb = ttk.Frame(root); bb.pack(fill="x", padx=14, pady=8)
        self.start_btn = ttk.Button(bb, text="Start 24/7", command=self.start); self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(bb, text="Stop", command=self.stop_now, state="disabled"); self.stop_btn.pack(side="left", padx=6)
        ttk.Button(bb, text="Scan now", command=self.scan_now).pack(side="left", padx=6)
        ttk.Button(bb, text="Test on a video file...", command=self.test_file).pack(side="left", padx=6)
        ttk.Button(bb, text="Save settings", command=self.save).pack(side="left", padx=6)
        ttk.Button(bb, text="Check setup", command=self.check_setup).pack(side="left", padx=6)
        self.bar = ttk.Progressbar(root, mode="indeterminate"); self.bar.pack(fill="x", padx=14)
        self.logbox = tk.Text(root, height=12, wrap="word", state="disabled"); self.logbox.pack(fill="both", expand=True, padx=14, pady=8)
        self.refresh_tree()
        self.root.after(200, self.pump)

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
                if m == "\0done":
                    self.bar.stop(); self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); continue
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
        c["upload"]["enabled"] = self.up_on.get(); c["upload"]["client_secret"] = self.secret.get()
        c["ai"]["enabled"] = self.ai_on.get(); c["cloudinary"]["enabled"] = self.cl_on.get(); c["thumbnail"]["enabled"] = self.th_on.get()
        config.save(c)

    # ---- actions
    def _go(self, fn):
        if self.worker and self.worker.is_alive():
            return
        self.save(); self.stop.clear(); self.bar.start(12)
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
        self.log(f"testing: {os.path.basename(f)}")
        def fn():
            try:
                cfg = config.load()
                p = analyze.plan(f, cfg, self.log)
                base = os.path.join(cfg["output_dir"], "manual", os.path.splitext(os.path.basename(f))[0])
                outs = render.render(f, p["segments"], p["info"], cfg, base, self.log)
                self.log("done. Files:\n" + "\n".join(f"  {h}p  {o}" for h, o in sorted(outs.items(), reverse=True)))
                self.log(f"Open this folder: {os.path.dirname(base)}")
            except Exception as e:
                self.log(f"TEST FAILED: {e}")
                self.root.after(0, lambda: messagebox.showerror("Test failed", str(e)[:800]))
        self._go(fn)


def main() -> int:
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
