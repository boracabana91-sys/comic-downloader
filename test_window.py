"""Opens the real window and tries the Custom size boxes and the cover drop box."""
import os
import tempfile

from PIL import Image

import app

root, dnd = app.make_root()
assert dnd, "the drag-and-drop tool did not load"
a = app.App(root, dnd)

# Custom size boxes appear and read back
a.device.set(a.device_labels[-1])
a.update_custom()
root.update()
assert a.custom_info()
a.device.set(a.device_labels[0])
a.update_custom()
root.update()

# Cover drop box: choose, preview, clear
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    p = os.path.join(d, "c.png")
    Image.new("RGB", (300, 500), (200, 30, 30)).save(p)
    a.set_cover(p)
    root.update()
    assert a.cover_path == p and a._photo is not None
    a.clear_cover()
    root.update()
    assert a.cover_path is None

root.destroy()
print("window OK")
