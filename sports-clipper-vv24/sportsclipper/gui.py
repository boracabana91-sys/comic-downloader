"""Sports Clipper window (same simple layout as Comic Downloader: sections top to bottom)."""
from __future__ import annotations
import base64
import os
import queue
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from datetime import datetime

import subprocess
import sys

from . import __version__, checks, config, job, pipeline, preview, progress, results, rights, sources, thumbnail, uploader, wake

RES = [2160, 1080, 720, 480, 360]


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"Sports Clipper {__version__}")
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

        ttk.Label(page, text=f"Sports Clipper  {__version__}", font=("Helvetica", 18, "bold")).pack(anchor="w", padx=14, pady=(14, 0))
        ttk.Label(page, text="Watches your licensed sources, cuts out the dead time, makes every resolution, and posts.",
                  foreground="#555").pack(anchor="w", padx=14)

        # --- sources: paste a link, nothing else to fill in
        ttk.Label(page, text="Add a channel or playlist - paste its YouTube link").pack(anchor="w", **pad)
        form = ttk.Frame(page); form.pack(fill="x", padx=14)
        self.s_link = tk.StringVar()
        ttk.Entry(form, textvariable=self.s_link).pack(side="left", fill="x", expand=True)
        ttk.Button(form, text="Paste", command=self.paste_link).pack(side="left", padx=6)
        ttk.Button(form, text="Add channel", command=self.add_source).pack(side="left")
        ttk.Label(page, text="Click (or Cmd-click several) the channels to scan: only highlighted channels are scanned.  Example: https://www.youtube.com/@ChannelName",
                  foreground="#777").pack(anchor="w", padx=14)
        self.s_lic = tk.BooleanVar(value=True)   # vv23: starts ticked; adding a channel is the permission statement
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
        self.scan_btn = ttk.Button(vb, text="Scan all videos", command=self.scan_channel)
        self.scan_btn.pack(side="left")
        ttk.Button(vb, text="Reclip selected video", command=self.reclip_selected).pack(side="left", padx=6)
        ttk.Button(vb, text="Reclip all highlighted", command=self.reclip_all_highlighted).pack(side="left")
        ttk.Label(vb, text="  Search:").pack(side="left")
        self.vid_filter = tk.StringVar()
        self.vid_filter.trace_add("write", lambda *_: self.show_videos())
        self.vid_entry = ttk.Entry(vb, textvariable=self.vid_filter, width=30)
        self.vid_entry.pack(side="left", padx=4)
        self.vid_entry.bind("<Return>", lambda e: self.scan_channel())
        self.vid_count = tk.StringVar(value="")
        ttk.Label(vb, textvariable=self.vid_count, foreground="#555").pack(side="left", padx=6)
        ttk.Label(vf, text="Tip: paste a playlist link OR a link to one video in Search and press Enter (or Scan all videos). A video link selects that video, ready to Reclip.",
                  foreground="#777").pack(anchor="w", padx=8)
        tf = ttk.Frame(vf); tf.pack(fill="x", padx=6, pady=(0, 6))
        self.vid_tree = ttk.Treeview(tf, columns=("date",), show="tree headings", height=10)
        self.vid_tree.heading("#0", text="Title (open a folder: Videos, Live, Shorts, Playlists)")
        self.vid_tree.column("#0", width=600)
        self.vid_tree.heading("date", text="Posted"); self.vid_tree.column("date", width=130, stretch=False)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.vid_tree.yview)
        self.vid_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y"); self.vid_tree.pack(side="left", fill="x", expand=True)
        self.vid_items = {}
        self.all_videos = []
        self.latest_ids = set()                      # vv20: newest unprocessed videos (shown green, pre-selected)
        self.vid_tree.tag_configure("latest", foreground="#1a8a3a")
        self.vid_tree.configure(selectmode="extended")
        self.vid_tree.bind("<<TreeviewSelect>>", self.video_selected)

        # --- thumbnail preview: the teams are read from a title / file name, one drop-down per team
        pv = ttk.LabelFrame(page, text="Thumbnail preview - appears by itself as soon as a game title names two teams")
        pv.pack(fill="x", padx=14, pady=4)
        tr = ttk.Frame(pv); tr.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(tr, text="Game title or file name:").pack(side="left")
        self.pv_title = tk.StringVar()
        self.pv_title.trace_add("write", lambda *_: self.pv_schedule())
        ttk.Entry(tr, textvariable=self.pv_title).pack(side="left", fill="x", expand=True, padx=6)
        fr = ttk.Frame(pv); fr.pack(fill="x", padx=6, pady=(0, 2))
        ttk.Label(fr, text="Font style:").pack(side="left")
        self.font_var = tk.StringVar(value=self.cfg.get("thumb_font", thumbnail.DEFAULT_STYLE))
        self.font_cb = ttk.Combobox(fr, textvariable=self.font_var, values=thumbnail.font_styles(), state="readonly", width=18)
        self.font_cb.pack(side="left", padx=6)
        self.font_cb.bind("<<ComboboxSelected>>", lambda e: self.font_pick())
        ttk.Label(fr, text="the preview below changes right away; your choice is remembered", foreground="#777").pack(side="left")
        self.pv_msg = tk.StringVar(value=preview.message({"teams": [], "slots": []}))
        ttk.Label(pv, textvariable=self.pv_msg, foreground="#555").pack(anchor="w", padx=8)
        self.pv_row = ttk.Frame(pv)
        self.pv_row.pack(fill="x", padx=6, pady=4)
        self.pv_vars, self.pv_combos, self.pv_names, self.pv_teams = [], [], [[], []], ["", ""]
        self.pv_photo_cbs, self.pv_photo_counts, self.pv_photo_old, self.pv_photo_close = [], [[], []], [[], []], [[], []]
        for i in range(2):
            col = ttk.Frame(self.pv_row); col.pack(side="left", fill="x", expand=True, padx=4)
            lab = ttk.Label(col, text="", font=("Helvetica", 11, "bold")); lab.pack(anchor="w")
            var = tk.StringVar()
            cb = ttk.Combobox(col, textvariable=var, state="disabled", width=34)
            cb.pack(fill="x")
            cb.bind("<<ComboboxSelected>>", lambda e, i=i: self.pv_pick(i))
            pr = ttk.Frame(col); pr.pack(fill="x", pady=(2, 0))
            ttk.Label(pr, text="Photo:").pack(side="left")
            pcb = ttk.Combobox(pr, state="disabled", width=14, values=[])
            pcb.pack(side="left", padx=4)
            pcb.bind("<<ComboboxSelected>>", lambda e, i=i: self.pv_photo_pick(i))
            self.pv_vars.append((lab, var)); self.pv_combos.append(cb); self.pv_photo_cbs.append(pcb)
        self.pv_img = ttk.Label(pv, anchor="center")
        self.pv_img.pack(pady=(2, 8))
        self._pv_photo = None
        self._pv_after = None
        self._pv_gen = 0

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
        self.min_min = tk.DoubleVar(value=self.cfg.get("min_minutes", 8)); self.max_min = tk.DoubleVar(value=self.cfg.get("max_minutes", 12))
        ttk.Label(rr, text="   Final length:  at least").pack(side="left")
        ttk.Spinbox(rr, from_=1, to=180, increment=1, width=4, textvariable=self.min_min).pack(side="left", padx=4)
        ttk.Label(rr, text="min,  at most").pack(side="left")
        ttk.Spinbox(rr, from_=1, to=180, increment=1, width=4, textvariable=self.max_min).pack(side="left", padx=4)
        ttk.Label(rr, text="min").pack(side="left")
        self.hl = tk.BooleanVar(value=bool(self.cfg.get("highlights", False)))
        hlf = ttk.Frame(page); hlf.pack(fill="x", padx=14, pady=(2, 0))
        ttk.Checkbutton(hlf, text="Highlights", variable=self.hl).pack(side="left")
        ttk.Label(hlf, text="  dead time out (intro, timeouts, free throws, post-game), then whole chunks of play spread evenly to reach the length. Game order, normal speed.",
                  foreground="#555").pack(side="left")
        self.bc = tk.BooleanVar(value=bool(self.cfg.get("best_clips", False)))
        bcf = ttk.Frame(page); bcf.pack(fill="x", padx=14, pady=(2, 0))
        ttk.Checkbutton(bcf, text="Best Clips", variable=self.bc).pack(side="left")
        ttk.Label(bcf, text="  off = the normal reclip.  On = only the best moments: the loudest crowd and commentator reactions, up to the 'at most' length. Game order, normal speed.",
                  foreground="#555").pack(side="left")
        self.iv = tk.BooleanVar(value=bool(self.cfg.get("include_interview", False)))
        ivf = ttk.Frame(page); ivf.pack(fill="x", padx=14, pady=(2, 0))
        ttk.Checkbutton(ivf, text="Include post-game interview", variable=self.iv).pack(side="left")
        ttk.Label(ivf, text="  off = everything after the last play is cut (and never added back to reach the minimum length)",
                  foreground="#555").pack(side="left")
        self.tip = tk.BooleanVar(value=bool(self.cfg.get("start_at_tipoff", True)))
        tpf = ttk.Frame(page); tpf.pack(fill="x", padx=14, pady=(2, 0))
        ttk.Checkbutton(tpf, text="Start at the jump ball", variable=self.tip).pack(side="left")
        ttk.Label(tpf, text="  cuts the long opening (intros, warm-up, pre-game show) before tip-off; needs the scoreboard clock to be readable",
                  foreground="#555").pack(side="left")
        self.cov = tk.BooleanVar(value=bool(self.cfg.get("thumb_cover_art", False)))
        self.intro = tk.BooleanVar(value=bool(self.cfg.get("thumb_intro", False)))
        tf2 = ttk.Frame(page); tf2.pack(fill="x", padx=14, pady=(2, 0))
        ttk.Checkbutton(tf2, text="Save the thumbnail inside the video file (cover picture)", variable=self.cov).pack(side="left")
        ttk.Checkbutton(tf2, text="Show the thumbnail for 1 second at the start", variable=self.intro).pack(side="left", padx=14)
        ttk.Label(page, text="YouTube does not read a picture from inside the video: the thumbnail is always sent to YouTube separately (your channel must be verified). "
                             "These two ticks are optional extras.", foreground="#777", wraplength=860, justify="left").pack(anchor="w", padx=14)
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
        ttk.Checkbutton(ex, text="3 AI writers for title, tags and description (key goes in config.json)", variable=self.ai_on).pack(side="left")
        ttk.Checkbutton(ex, text="Back up to Cloudinary (set keys in config.json)", variable=self.cl_on).pack(side="left", padx=14)
        ttk.Checkbutton(ex, text="Auto thumbnail", variable=self.th_on).pack(side="left", padx=14)
        self.th_close = tk.BooleanVar(value=self.cfg.get("thumb_layout", "closeup") != "stars")
        thumbnail.set_layout(self.cfg.get("thumb_layout", "closeup"))
        ttk.Checkbutton(ex, text="Close-up faces style", variable=self.th_close,
                        command=lambda: (thumbnail.set_layout("closeup" if self.th_close.get() else "stars"), self.pv_update())).pack(side="left")

        # --- vv22: YT Preview (separate from the thumbnail preview): exactly what will be posted, and whether it follows the rules
        yp = ttk.LabelFrame(page, text="YT Preview - what will be posted on YouTube (fills after Test, Reclip or a held video)")
        yp.pack(fill="x", padx=14, pady=4)
        self.yt_data = None
        self.yt_file = tk.StringVar(); self.yt_title = tk.StringVar()
        for lab, var in (("File name", self.yt_file), ("Title", self.yt_title)):
            r = ttk.Frame(yp); r.pack(fill="x", padx=6, pady=2)
            ttk.Label(r, text=lab, width=10).pack(side="left")
            ttk.Entry(r, textvariable=var, state="readonly").pack(side="left", fill="x", expand=True)
        self.yt_desc = self._ro_text(yp, "Description", 8)
        self.yt_tags = self._ro_text(yp, "Tags", 3)
        self.yt_rules = self._ro_text(yp, "Rules", 10)
        self.yt_rules.tag_configure("ok", foreground="#1a8a3a"); self.yt_rules.tag_configure("bad", foreground="#c0392b")
        yb = ttk.Frame(yp); yb.pack(fill="x", padx=6, pady=(2, 6))
        self.yt_post_btn = ttk.Button(yb, text="OK - post it", command=self.yt_post, state="disabled")
        self.yt_post_btn.pack(side="left")
        self.yt_state = tk.StringVar(value="Nothing to preview yet.")
        ttk.Label(yb, textvariable=self.yt_state, foreground="#555").pack(side="left", padx=10)

        # --- buttons
        bb = ttk.Frame(page); bb.pack(fill="x", padx=14, pady=8)
        self.start_btn = ttk.Button(bb, text="Start 24/7", command=self.start); self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(bb, text="Stop", command=self.stop_now, state="disabled"); self.stop_btn.pack(side="left", padx=6)
        ttk.Button(bb, text="Scan now", command=self.scan_now).pack(side="left", padx=6)
        ttk.Button(bb, text="Test on a video file...", command=self.test_file).pack(side="left", padx=6)
        ttk.Button(bb, text="Set up auto wake-up", command=self.setup_wake).pack(side="left", padx=6)
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
        self.log(f"Sports Clipper {__version__} ready")
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

    # ---- thumbnail preview
    def pv_schedule(self):
        """Wait a moment after typing stops, then re-read the teams."""
        if self._pv_after:
            self.root.after_cancel(self._pv_after)
        self._pv_after = self.root.after(350, self.pv_update)

    def pv_update(self):
        self._pv_after = None
        state = preview.analyse(self.pv_title.get(), self.cfg.get("player_choice", {}), self.cfg.get("photo_choice", {}))
        self.pv_msg.set(preview.message(state))
        for i in range(2):
            lab, var = self.pv_vars[i]
            cb = self.pv_combos[i]
            if i < len(state["slots"]) and state["slots"][i]["labels"]:
                sl = state["slots"][i]
                self.pv_teams[i], self.pv_names[i] = sl["team"], sl["names"]
                self.pv_photo_counts[i] = sl["photo_counts"]
                self.pv_photo_old[i] = sl.get("photo_old", [])
                self.pv_photo_close[i] = sl.get("photo_close", [])
                lab.config(text=f"{sl['team']}  -  {sl['label']}")
                cb.config(values=sl["labels"], state="readonly" if len(sl["labels"]) > 1 else "disabled")
                cb.current(sl["selected"])
                self._fill_photo_combo(i, sl["photos"], sl["photo"], (sl.get("photo_old") or [[]])[sl["selected"]] if sl.get("photo_old") else (),
                                       (sl.get("photo_close") or [[]])[sl["selected"]] if sl.get("photo_close") else ())
            else:
                self.pv_teams[i], self.pv_names[i] = "", []
                self.pv_photo_counts[i] = []
                self._fill_photo_combo(i, 0, 0)
                lab.config(text=state["slots"][i]["label"] if i < len(state["slots"]) else "")
                var.set(""); cb.config(values=[], state="disabled")
        self.pv_render()

    @staticmethod
    def _photo_tag(k, old, close) -> str:
        tags = [t for t, on in (("close-up", k in close), ("old team", k in old)) if on]
        return f" ({', '.join(tags)})" if tags else ""

    def _fill_photo_combo(self, i, n, sel, old=(), close=()):
        """The Photo drop-down of a team: 'Photo 1 of 3'; greyed out when the player has just one picture."""
        pcb = self.pv_photo_cbs[i]
        if n <= 0:
            pcb.config(values=[], state="disabled"); pcb.set("")
            return
        pcb.config(values=[f"Photo {k + 1} of {n}" + self._photo_tag(k, old, close) for k in range(n)], state="readonly" if n > 1 else "disabled")
        pcb.current(min(sel, n - 1))

    def pv_pick(self, i):
        """A player was chosen in a drop-down: remember it for that team and redraw."""
        idx = self.pv_combos[i].current()
        team, names = self.pv_teams[i], self.pv_names[i]
        if team and 0 <= idx < len(names):
            self.cfg.setdefault("player_choice", {})[team] = names[idx]
            self.save()
            counts = self.pv_photo_counts[i]
            n = counts[idx] if idx < len(counts) else 1
            olds, closes = self.pv_photo_old[i], self.pv_photo_close[i]
            self._fill_photo_combo(i, n, int(self.cfg.get("photo_choice", {}).get(names[idx], 0)),
                                   olds[idx] if idx < len(olds) else (), closes[idx] if idx < len(closes) else ())     # that player's own photos
        self.pv_render()

    def pv_photo_pick(self, i):
        """A photo was chosen for the selected player: remember it (per player) and redraw."""
        idx, pidx = self.pv_combos[i].current(), self.pv_photo_cbs[i].current()
        names = self.pv_names[i]
        if 0 <= idx < len(names) and pidx >= 0:
            self.cfg.setdefault("photo_choice", {})[names[idx]] = pidx
            self.save()
        self.pv_render()

    def font_pick(self):
        """A font style was chosen: remember it and redraw the preview."""
        self.cfg["thumb_font"] = self.font_var.get()
        self.save()
        self.pv_render()

    def pv_render(self):
        self._pv_gen += 1
        gen, title, picks = self._pv_gen, self.pv_title.get(), dict(self.cfg.get("player_choice", {}))
        style, photos = self.font_var.get(), dict(self.cfg.get("photo_choice", {}))
        def work():
            try:
                png = preview.render_png(title, picks, style=style, photos=photos)
            except Exception as e:
                self.q.put(f"preview failed: {e}")
                png = None
            self.q.put(("__preview__", gen, png))
        threading.Thread(target=work, daemon=True).start()

    # ---- helpers
    def log(self, m): self.q.put(m)

    def pump(self):
        try:
            while True:
                m = self.q.get_nowait()
                if isinstance(m, tuple) and m[0] == "__add__":
                    self.cfg["sources"].append(m[1]); self.refresh_tree(); self.save()
                    self.s_link.set(""); self.s_lic.set(True)
                    self.log(f"added channel: {m[1]['name']} ({m[1]['location']})")
                    continue
                if isinstance(m, tuple) and m[0] == "__yt__":
                    self.yt_show(m[1])
                    continue
                if isinstance(m, tuple) and m[0] == "__error__":
                    messagebox.showerror(m[1], m[2])
                    continue
                if isinstance(m, tuple) and m[0] == "__status__":
                    self.st, self.st_t = (m[1], m[2]), time.time()
                    if m[2] is not None:
                        self.bar.stop(); self.bar.config(mode="determinate", value=m[2])
                    continue
                if isinstance(m, tuple) and m[0] == "__preview__":
                    if m[1] == self._pv_gen:                          # ignore a picture that is already out of date
                        if m[2]:
                            self._pv_photo = tk.PhotoImage(data=base64.b64encode(m[2]))
                            self.pv_img.config(image=self._pv_photo, text="")
                        else:
                            self._pv_photo = None
                            self.pv_img.config(image="", text="")
                    continue
                if isinstance(m, tuple) and m[0] == "__latest__":      # vv20: Scan now suggests the newest videos
                    self.all_videos = m[1]; self.latest_ids = {v.id for v in m[1]}
                    self.show_videos()
                    kids = [k for g in self.vid_tree.get_children() for k in self.vid_tree.get_children(g)]
                    self.vid_tree.selection_set(kids)
                    if kids:
                        self.vid_tree.see(kids[0])
                    continue
                if isinstance(m, tuple) and m[0] == "__videos__":
                    self.all_videos = m[1]; self.latest_ids = set()
                    self.scan_btn.config(state="normal")
                    self.show_videos()
                    if len(self.all_videos) == 1 and self.all_videos[0].group == "Single video":   # vv17: one link = select it
                        kids = self.vid_tree.get_children()
                        if kids and self.vid_tree.get_children(kids[0]):
                            first = self.vid_tree.get_children(kids[0])[0]
                            self.vid_tree.selection_set(first); self.vid_tree.see(first); self.video_selected()
                    continue
                if m == "\0done":
                    self.bar.stop(); self.bar.config(mode="determinate", value=0)
                    self.status_var.set("Finished - see Results below, or the log for details")
                    self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); self.refresh_results(); continue
                self.logbox.config(state="normal"); self.logbox.insert("end", m + "\n"); self.logbox.see("end"); self.logbox.config(state="disabled")
                if isinstance(m, str) and m.startswith("!! "):             # a problem the person must see, not just read in the log
                    messagebox.showwarning("Sports Clipper", m[3:])
        except queue.Empty:
            pass
        self.root.after(200, self.pump)

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        keep = []
        for d in self.cfg["sources"]:
            iid = self.tree.insert("", "end", values=(d["name"], d["location"],
                                                      "yes" if d.get("licensed") and d.get("license_note") else "NO"))
            if d["name"] in (self.cfg.get("scan_only") or []):
                keep.append(iid)
        if keep:
            self.tree.selection_set(keep)                    # vv20: the highlighted channels come back after a restart

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
        link = self.vid_filter.get().strip()
        if sources.video_id(link):                          # vv17: a link to ONE video: fetch just that video, ready to reclip
            src, what = None, "that video"
            self.vid_filter.set("")
        elif sources.playlist_id(link):                     # a playlist link in the search bar: scan just that playlist
            src, what = None, "that playlist"
            self.vid_filter.set("")
        else:
            src = self._channel_src()
            if not src:
                return
            what = src.name
        self.log(f"reading {what} ..." if sources.video_id(link) else f"reading every video on {what} (this can take a minute on a big list) ...")
        self.vid_count.set("reading ...")
        self.scan_btn.config(state="disabled")
        def job():
            try:
                if sources.video_id(link):
                    vids = sources.fetch_video(link, self.log)
                elif src is None:
                    vids = sources.scan_playlist(link, self.log)
                else:
                    vids = sources.list_all(src, self.log)
                self.q.put(("__videos__", vids))
                n = len({v.id for v in vids})
                self.log(f"found {n} video(s) on {what} - " + ("it is selected: press Reclip selected video" if sources.video_id(link) else "open a folder, click one, then Reclip selected video"))
            except Exception as e:
                self.log(f"scan failed: {e}")
                self.q.put(("__videos__", []))
        threading.Thread(target=job, daemon=True).start()

    def show_videos(self):
        """Fill the list from everything scanned, grouped like the channel, filtered by the search box."""
        q = self.vid_filter.get().strip().lower()
        if sources.playlist_id(q) or sources.video_id(q):    # a pasted link is not a title filter
            q = ""
        self.vid_tree.delete(*self.vid_tree.get_children())
        self.vid_items = {}
        groups: dict = {}
        for v in self.all_videos:
            if q and q not in v.title.lower():
                continue
            groups.setdefault(v.group or "Videos", []).append(v)
        shown = 0
        for gi, (g, vids) in enumerate(groups.items()):
            parent = self.vid_tree.insert("", "end", iid=f"g{gi}", text=f"{g}  ({len(vids)})", open=bool(q) or gi == 0)
            for j, v in enumerate(vids):
                iid = f"v{gi}_{j}"
                self.vid_items[iid] = v
                when = v.published.astimezone().strftime("%Y-%m-%d") if v.dated else ""
                self.vid_tree.insert(parent, "end", iid=iid, text=v.title, values=(when,),
                                     tags=("latest",) if v.id in self.latest_ids else ())
                shown += 1
        total = len({v.id for v in self.all_videos})
        self.vid_count.set(f"{shown} shown of {total}" if self.all_videos else "")

    def video_selected(self, _=None):
        """Clicking a video puts its title in the thumbnail preview box."""
        sel = self.vid_tree.selection()
        if sel and sel[0] in self.vid_items:
            self.pv_title.set(self.vid_items[sel[0]].title)

    def _owner_or_add(self, v):
        """vv23: the channel entry that covers this video; if none, ask once whether it is yours and add it."""
        d = sources.owner_source(v, self.cfg["sources"])
        if d:
            return d
        who = v.channel_name or v.channel_id or "this channel"
        if not v.channel_id:
            messagebox.showinfo("Reclip", f"{sources.why_not_owned(v)}\nPaste its channel link in Add channel first, then reclip.")
            return None
        if not messagebox.askyesno("Reclip", f"{sources.why_not_owned(v)}\n\nIs '{who}' your channel, or do you have permission "
                                             "to use its videos?\nYes = add it to your channels and reclip."):
            return None
        note = f"Owner confirmed in the app on {datetime.now():%Y-%m-%d} (added from a video)"
        d = sources.source_for_video(v, note)
        self.cfg["sources"].append(d); self.refresh_tree(); self.save()
        self.log(f"added channel: {d['name']} ({d['location']})")
        return d

    def reclip_selected(self):
        sel = self.vid_tree.selection()
        if not sel or sel[0] not in self.vid_items:
            return messagebox.showinfo("Reclip", "Scan all videos, open a folder and click a video first.")
        v = self.vid_items[sel[0]]
        d = self._owner_or_add(v)
        if not d:
            return
        src = rights.Source.from_dict(d)
        self.log(f"reclipping: {v.title}")
        def fn():
            try:
                pl = pipeline.Pipeline(config.load(), self.log, self.stop)
                pl.on_preview = lambda x: self.q.put(("__yt__", x))
                r = pl.process(src, v)
                self.log("done: " + v.title)
                if r.get("post"):
                    r["checks"] = r.get("checks") or []
                    self.q.put(("__yt__", r))
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
        lo = max(0.5, float(self.min_min.get())); hi = max(lo, float(self.max_min.get()))
        c["min_minutes"], c["max_minutes"] = lo, hi
        c["highlights"] = self.hl.get()
        c["best_clips"] = self.bc.get()
        picked = [self.cfg["sources"][self.tree.index(i)]["name"] for i in self.tree.selection()
                  if self.tree.index(i) < len(self.cfg["sources"])]
        if picked:
            c["scan_only"] = picked
        c["include_interview"] = self.iv.get()
        c["start_at_tipoff"] = self.tip.get()
        c["thumb_cover_art"] = self.cov.get(); c["thumb_intro"] = self.intro.get()
        c["thumb_font"] = self.font_var.get()
        c["upload"]["enabled"] = self.up_on.get(); c["upload"]["client_secret"] = self.secret.get()
        c["ai"]["enabled"] = self.ai_on.get(); c["cloudinary"]["enabled"] = self.cl_on.get(); c["thumbnail"]["enabled"] = self.th_on.get()
        c["thumb_layout"] = "closeup" if self.th_close.get() else "stars"
        thumbnail.set_layout(c["thumb_layout"])
        config.save(c)

    # ---- actions
    def _go(self, fn):
        if self.worker and self.worker.is_alive():
            self.log("a clip is already running - wait for it to finish (or press Stop)")
            return messagebox.showinfo("Busy", "A clip is already running. Wait for it to finish, or press Stop.")
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
        """vv20: look at the highlighted channels and suggest the newest unprocessed videos (green, pre-selected)."""
        self.save()
        cfg = config.load()
        if not cfg.get("scan_only"):
            return messagebox.showinfo("Scan now", "Click the channel(s) to scan in the channel list first.")
        self.log("looking for the newest videos on the highlighted channel(s) ...")
        def job():
            pl = pipeline.Pipeline(cfg, self.log, self.stop)
            found = []
            for d in pl.selected_sources():
                src = rights.Source.from_dict(d)
                try:
                    rights.check(src)
                    found += pl.latest_new(src, int(cfg.get("videos_per_scan", 3)))
                except Exception as e:
                    self.log(f"[{src.name}] {e}")
            self.q.put(("__latest__", found))
            self.log(f"{len(found)} new video(s) suggested (green, already selected): press Reclip all highlighted"
                     if found else "nothing new on the highlighted channel(s)")
        threading.Thread(target=job, daemon=True).start()

    def reclip_all_highlighted(self):
        """vv20: reclip every highlighted video in the list, one after another."""
        vids = [self.vid_items[i] for i in self.vid_tree.selection() if i in self.vid_items]
        if not vids:
            return messagebox.showinfo("Reclip", "Highlight videos in the list first (Scan now selects the newest ones for you).")
        jobs = []
        for v in vids:
            d = sources.owner_source(v, self.cfg["sources"])
            if not d:
                self.log(f"skipped ({sources.why_not_owned(v)}): {v.title}")
                continue
            jobs.append((rights.Source.from_dict(d), v))
        if not jobs:
            return messagebox.showinfo("Reclip", "None of those videos belong to a channel with the permission box ticked.")
        self.log(f"reclipping {len(jobs)} video(s), one after another ...")
        def fn():
            pl = pipeline.Pipeline(config.load(), self.log, self.stop)
            pl.on_preview = lambda x: self.q.put(("__yt__", x))
            ok = 0
            for src, v in jobs:
                if self.stop.is_set():
                    break
                try:
                    pl.process(src, v); ok += 1
                    self.log("done: " + v.title)
                except Exception as e:
                    pl.db.set(src.name, v.id, v.title, "error", str(e)[:300])
                    self.log(f"FAILED (files kept on the drive): {v.title}: {str(e)[:300]}")
            self.log(f"finished: {ok} of {len(jobs)} video(s) done")
        self._go(fn)

    def setup_wake(self):
        self.save()
        c = self.cfg; c["wake"] = {"enabled": True}; config.save(c)
        threading.Thread(target=lambda: wake.setup(c["schedule"], self.log), daemon=True).start()

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
        self.pv_title.set(title)
        self.log(f"testing: {os.path.basename(f)}")
        def fn():
            try:
                r = job.clip_file(f, config.load(), title, self.log, on_preview=lambda x: self.q.put(("__yt__", x)))
                self.log("done. Sizes: " + ", ".join(f"{h}p" for h in sorted(r["outputs"], reverse=True))
                         + ("  + thumbnail" if r["thumb"] else "") + "  - check the YT Preview box, then press OK - post it")
                self.q.put(("__yt__", r))
            except Exception as e:
                msg = str(e)[:800]
                self.log(f"TEST FAILED: {msg}")
                self.q.put(("__error__", "Test failed", msg))
        self._go(fn)

    @staticmethod
    def _ro_text(parent, label, height):
        r = ttk.Frame(parent); r.pack(fill="x", padx=6, pady=2)
        ttk.Label(r, text=label, width=10).pack(side="left", anchor="n")
        t = tk.Text(r, height=height, wrap="word", state="disabled")
        t.pack(side="left", fill="x", expand=True)
        return t

    @staticmethod
    def _set_text(box, text, tag=None):
        box.config(state="normal"); box.delete("1.0", "end")
        for line, tg in (text if isinstance(text, list) else [(text, tag)]):
            box.insert("end", line, tg or ())
        box.config(state="disabled")

    def yt_show(self, r):
        """vv22: fill the YT Preview from a finished test / reclip: file name, title, description, tags and every rule."""
        pp = r.get("post")
        if not pp:
            return
        meta = pp["meta"]
        self.yt_data = r
        self.yt_file.set(os.path.basename(r.get("upload_file", "")))
        self.yt_title.set(meta["title"])
        self._set_text(self.yt_desc, meta["description"])
        self._set_text(self.yt_tags, ", ".join(meta["tags"]))
        checks = r.get("checks") or []
        self._set_text(self.yt_rules, [((("OK   " if ok else "FAIL ") + rule + (f"  ({d})" if d and not ok else "") + "\n"),
                                       "ok" if ok else "bad") for ok, rule, d in checks])
        good = bool(checks) and all(ok for ok, _, _ in checks)
        if r.get("preview"):                                   # vv24: shown before the video is cut; posting comes after it is finished
            self.yt_post_btn.config(state="disabled")
            self.yt_state.set("Preview - the video is being cut now. The rules are checked again on the finished video." if good
                              else "Preview - a rule already fails; it will be checked again on the finished video.")
            return
        self.yt_post_btn.config(state="normal" if good else "disabled")
        self.yt_state.set("All rules pass - press OK - post it to upload." if good else "A rule fails - fix it before posting (the video will not post by itself).")

    def yt_post(self):
        r = self.yt_data
        if not r or not messagebox.askyesno("Post it", f"Upload this video to your channel now?\n\n{r['post']['meta']['title']}"):
            return
        def fn():
            cfg = config.load()
            try:
                vid = uploader.upload_youtube(cfg, r["upload_file"], r["post"]["meta"], None, self.log)
                self.log(f"posted: https://youtu.be/{vid}")
                th = r.get("thumb") or r.get("thumbnail")
                if th:
                    try:
                        uploader.set_thumbnail(cfg, vid, th, self.log); self.log("thumbnail set on YouTube")
                    except Exception as e:
                        self.log(f"!! The video is on YouTube, but its thumbnail was NOT set: {e}")
            except Exception as e:
                self.log(f"!! UPLOAD FAILED: {str(e)[:300]}  -- the video is still here: {r['upload_file']}")
        self.yt_post_btn.config(state="disabled"); self.yt_state.set("uploading ...")
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
