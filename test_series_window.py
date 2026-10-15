"""Opens the real Series window and checks the chapter list and ticking."""
import series_app

root, dnd = series_app.make_root()
assert dnd, "the drag-and-drop tool did not load"
a = series_app.SeriesApp(root, dnd)
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
root.destroy()
print("series window OK")
