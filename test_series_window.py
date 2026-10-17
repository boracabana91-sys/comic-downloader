"""Opens the real Series window and checks the chapter list and ticking."""
import series
import series_app

root, dnd = series_app.make_root()
assert dnd, "the drag-and-drop tool did not load"
import os, tempfile
_sp = os.path.join(tempfile.mkdtemp(), 's.json')
a = series_app.SeriesApp(root, dnd, _sp)
urls = [f"https://x.test/series/demo/chapter-{n}" for n in range(1, 13)]
a.show_chapters("Demo", urls)
root.update()
assert a.sname.get() == "Demo" and a.lb.size() == 12
assert len(a.lb.curselection()) == 12
a.sel_none()
assert len(a.lb.curselection()) == 0
a.lb.selection_set(2, 4)
a.update_count()
assert "3 ticked" in a.count.get(), a.count.get()
a.device.set(a.device_labels[-1])
a.update_custom()
root.update()
assert a.custom_info()
a.device.set(a.device_labels[1])
a.epub.set("Yes")
a.layout.set("one")
a.update_preview()
assert "Chapter 001.epub" in a.preview.cget("text") and "Pages/" not in a.preview.cget("text")
a.layout.set("parts")
a.update_preview()
assert "Pages/" in a.preview.cget("text") and "Pages 1-5" in a.preview.cget("text")
root.geometry("820x640+50+60")
root.update()
a.save_geometry()
assert series.load_settings(_sp)["geometry"].startswith("820x640"), series.load_settings(_sp)
root.update()
assert a.btn_go.winfo_ismapped() and a.log.winfo_ismapped()  # buttons and log stay visible
assert a.badge.get() is True
assert a.canvas.bbox('all') is not None  # the middle part scrolls
root.geometry('760x420')
root.update()
assert a.btn_go.winfo_ismapped()  # even a short window keeps the buttons
assert a.fit.get() == "new"
a.layout.set("central")
a.update_preview()
assert "EPUB" in a.preview.cget("text") and str(a.size_spin.cget("state")) == "disabled"
root.destroy()
print("series window OK")
