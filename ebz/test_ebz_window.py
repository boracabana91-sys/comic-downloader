"""Opens the real EBZ CNVRTR window and checks it (needs a screen; the build has one)."""
import os
import sys
import tempfile
import time
import traceback
import zipfile


def _hook(t, v, tb):   # failures show as a note on the GitHub build
    print("::error title=window test::" + "".join(traceback.format_exception(t, v, tb)).strip().replace("\n", "%0A"))


sys.excepthook = _hook

from PIL import Image  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devices  # noqa: E402
import ebz_app  # noqa: E402
import version  # noqa: E402


def wait(app, root):
    t = time.time()
    while app.worker.is_alive() and time.time() - t < 180:
        root.update()
        time.sleep(0.05)
    for _ in range(5):
        root.update()
        time.sleep(0.1)


class Ev:
    def __init__(self, root, *paths):
        self.data = root.tk.call("list", *paths)   # paths with spaces too


d = tempfile.mkdtemp()
sp = os.path.join(d, "s.json")
root, dnd = ebz_app.make_root()
assert dnd, "the drag-and-drop tool did not load"
a = ebz_app.App(root, dnd, sp)
root.update()
assert root.title() == f"EBZ CNVRTR {version.VERSION}", root.title()
assert a.version_label.cget("text") == f"Version {version.VERSION}"
assert a.drop_on
assert a.dev_lb.size() == len(devices.DEVICE_KEYS)
assert a.device_keys() == ["kobo_clara"]
assert str(a.cw_box.cget("state")) == "disabled"
assert a.btn_go.cget("text") == "Convert"

# ----- Convert tab: a folder, a PDF and a junk file dropped -----
src = os.path.join(d, "My Book Chapter 7")
os.makedirs(src)
for i in range(3):
    Image.new("RGB", (800, 1100), (40 * i, 90, 160)).save(os.path.join(src, f"{i}.png"))
pdf = os.path.join(d, "Guide.pdf")
Image.new("RGB", (600, 900), (10, 120, 10)).save(pdf, "PDF")
a.on_drop(Ev(root, src, pdf, os.path.join(d, "x.txt")))
root.update()
assert a.conv.lb.size() == 2 and "My Book" in a.conv.lb.get(0), a.conv.lb.get(0, "end")
a.on_drop(Ev(root, src, pdf))   # the same things again are not added twice
assert a.conv.lb.size() == 2 and a.comb.lb.size() == 0

# ----- cover picture dropped on the cover box, number options -----
cov = os.path.join(d, "cover art.png")
Image.new("RGB", (600, 900), (200, 180, 40)).save(cov)
a.on_cover_drop(Ev(root, cov))
root.update()
assert a.cover_path == cov and a.cover_mode.get() == "picture" and a._photo is not None
a.corner.set("Lower left")
a.bsize.set("Large")
a.update_cover()
o = a.cover_options()
assert o["corner"] == "ll" and o["size"] == 0.10 and o["number"] is True

# ----- tick Kindle and custom size, change the output folder, convert -----
a.dev_lb.selection_set(devices.DEVICE_KEYS.index("kindle_pw7"))
a.dev_lb.selection_set(devices.DEVICE_KEYS.index("custom"))
a.update_devices()
assert str(a.cw_box.cget("state")) == "normal"
a.cw.set("900")
a.ch.set("1500")
out = os.path.join(d, "my output")
a.out.set(out)
a.start()
wait(a, root)
log = a.log.get("1.0", "end")
assert "Your files are in:" in log and "strip screens" in log or "fitted whole" in log, log
assert os.path.isfile(os.path.join(out, "Kobo Clara", "My Book Chapter 7.cbz"))
assert os.path.isfile(os.path.join(out, "Kobo Clara", "Guide.epub"))
assert os.path.isfile(os.path.join(out, "Kindle Paperwhite 7in", "My Book Chapter 7.pdf"))
assert os.path.isfile(os.path.join(out, "Custom 900x1500", "My Book Chapter 7.cbz"))
assert str(a.btn_go.cget("state")) == "normal" and str(a.btn_last.cget("state")) == "normal"
with zipfile.ZipFile(os.path.join(out, "Kobo Clara", "My Book Chapter 7.cbz")) as z:
    names = sorted(z.namelist())
    with z.open(names[0]) as f, Image.open(f) as im:   # page 1 is the cover (yellow)
        assert im.size == (1072, 1448) and im.convert("RGB").getpixel((536, 724))[2] < 100

# ----- Combine tab: three chapters joined, in list order, with an auto name -----
a.tabs.select(1)
root.update()
assert a.btn_go.cget("text").startswith("Combine")
chs = []
for n in (10, 2, 1):
    p = os.path.join(d, f"Series Chapter {n}")
    os.makedirs(p)
    Image.new("RGB", (800, 1100), (20 * n, 60, 90)).save(os.path.join(p, "1.png"))
    chs.append(p)
a.on_drop(Ev(root, *chs))
root.update()
assert a.comb.lb.size() == 3 and a.conv.lb.size() == 2   # dropped on the tab that is showing
a.comb.sort()
assert [b.name for b in a.comb.books] == ["Series Chapter 1", "Series Chapter 2", "Series Chapter 10"]
assert a.cname.get() == "Series Chapter 1-10", a.cname.get()
a.comb.lb.selection_set(2)
a.comb.move(-1)
assert [b.name for b in a.comb.books][1] == "Series Chapter 10"
a.comb.sort()
a.dev_lb.selection_clear(0, "end")
a.dev_lb.selection_set(devices.DEVICE_KEYS.index("kobo_clara"))
a.update_devices()
a.cfit.set(True)
a.start()
wait(a, root)
joined = os.path.join(out, "Kobo Clara", "Series Chapter 1-10.epub")
assert os.path.isfile(joined), a.log.get("1.0", "end")
with zipfile.ZipFile(joined) as z:
    nav = z.read("OEBPS/nav.xhtml").decode()
    assert nav.count("<li>") == 3 and "Series Chapter 2" in nav
a.cfit.set(False)
a.start()
wait(a, root)
assert os.path.isfile(os.path.join(out, "Combined", "Series Chapter 1-10.epub")), a.log.get("1.0", "end")

# ----- settings and window size are remembered -----
root.geometry("780x620+40+40")
root.update()
a.save_all()
s = ebz_app.load_settings(sp)
assert s["geometry"].startswith("780x620") and s["out_dir"] == out and s["tab"] == 1, s
assert s["cover"]["corner"] == "ll" and s["cover"]["path"] == cov
root.geometry("700x560")
root.update()
assert a.btn_go.winfo_ismapped() and a.log.winfo_ismapped()   # a short window keeps the buttons
root.destroy()

root2, dnd2 = ebz_app.make_root()
b = ebz_app.App(root2, dnd2, sp)
root2.update()
assert b.device_keys() == ["kobo_clara"] and b.out.get() == out
assert b.combining() and b.cover_path == cov and b.corner.get() == "Lower left"
root2.destroy()
print("EBZ window OK")
