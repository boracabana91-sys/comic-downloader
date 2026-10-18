"""Opens the real EBZ CNVRTR window and checks it (needs a screen; the build has one)."""
import os
import sys
import tempfile
import time
import traceback


def _hook(t, v, tb):   # failures show as a note on the GitHub build
    print("::error title=window test::" + "".join(traceback.format_exception(t, v, tb)).strip().replace("\n", "%0A"))


sys.excepthook = _hook

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devices  # noqa: E402
import ebz_app  # noqa: E402
import version  # noqa: E402

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

# what a drop delivers: a folder of pictures and a PDF
src = os.path.join(d, "My Book")
os.makedirs(src)
for i in range(3):
    Image.new("RGB", (800, 1100), (40 * i, 90, 160)).save(os.path.join(src, f"{i}.png"))
pdf = os.path.join(d, "Guide.pdf")
Image.new("RGB", (600, 900), (10, 120, 10)).save(pdf, "PDF")


class Ev:
    data = root.tk.call("list", src, pdf, os.path.join(d, "x.txt"))   # paths with spaces too


a.on_drop(Ev())
root.update()
assert a.lb.size() == 2 and "My Book" in a.lb.get(0), a.lb.get(0, "end")
a.on_drop(Ev())   # dropping the same things again does not add them twice
assert a.lb.size() == 2

# tick Kindle and custom, set out folder, convert
a.dev_lb.selection_set(devices.DEVICE_KEYS.index("kindle_pw7"))
a.dev_lb.selection_set(devices.DEVICE_KEYS.index("custom"))
a.update_devices()
assert str(a.cw_box.cget("state")) == "normal"
a.cw.set("900")
a.ch.set("1500")
out = os.path.join(d, "out")
a.out.set(out)
a.start()
t = time.time()
while a.worker.is_alive() and time.time() - t < 120:
    root.update()
    time.sleep(0.05)
root.update()
time.sleep(0.3)
root.update()
log = a.log.get("1.0", "end")
assert "screens are clean" in log, log
assert os.path.isfile(os.path.join(out, "Kobo Clara", "My Book.cbz"))
assert os.path.isfile(os.path.join(out, "Kobo Clara", "Guide.epub"))
assert os.path.isfile(os.path.join(out, "Kindle Paperwhite 7in", "My Book.pdf"))
assert os.path.isfile(os.path.join(out, "Custom 900x1500", "My Book.cbz"))
assert str(a.btn_go.cget("state")) == "normal"

# settings and window size are remembered
root.geometry("760x600+40+40")
root.update()
a.save_all()
s = ebz_app.load_settings(sp)
assert s["geometry"].startswith("760x600") and "kindle_pw7" in s["devices"], s
assert s["out_dir"] == out and s["custom"]["width"] == 900
root.geometry("700x540")
root.update()
assert a.btn_go.winfo_ismapped() and a.log.winfo_ismapped()   # a short window keeps the buttons
root.destroy()

root2, dnd2 = ebz_app.make_root()
b = ebz_app.App(root2, dnd2, sp)
root2.update()
assert set(b.device_keys()) == {"kobo_clara", "kindle_pw7", "custom"} and b.out.get() == out
root2.destroy()
print("EBZ window OK")
