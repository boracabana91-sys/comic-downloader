"""What the window's thumbnail preview needs, without any window code (so it can be tested):
read the two teams from a title or file name, list each team's players for the drop-downs, and draw the preview."""
from __future__ import annotations
import io

from . import roster, thumbnail


def analyse(title: str, picks: dict | None = None, photos: dict | None = None) -> dict:
    """{"teams": ["DEN", "LAC"], "slots": [{"team", "label", "labels": [...], "selected": 0, "names": [...]}, ...]}
    slots is empty until the title names two teams. A team with no picture has an empty "labels"."""
    picks = picks or {}
    photos = photos or {}
    teams = thumbnail.parse_teams(title or "")
    slots = []
    if len(teams) == 2:
        for t in teams:
            opts = roster.options(t)
            names = [o["name"] for o in opts]
            sel = names.index(picks[t]) if picks.get(t) in names else 0
            n_photos = len(opts[sel].get("cutouts") or [1]) if opts else 0
            try:
                ph = min(max(int(photos.get(names[sel], 0)), 0), max(0, n_photos - 1)) if names else 0
            except (TypeError, ValueError):
                ph = 0
            slots.append({"team": t, "label": roster.TEAMS[t][0], "names": names,
                          "labels": [roster.label(o) for o in opts], "selected": sel,
                          "photos": n_photos, "photo": ph,
                          "photo_counts": [len(o.get("cutouts") or [1]) for o in opts]})
    return {"teams": teams, "slots": slots}


def message(state: dict) -> str:
    """One line under the title box telling what was understood."""
    teams, slots = state["teams"], state["slots"]
    if len(teams) < 2:
        return "Type or pick a game title with two NBA teams, e.g. 'DEN vs LAC' - the preview appears by itself."
    missing = [s["team"] for s in slots if not s["labels"]]
    head = f"{teams[0]} vs {teams[1]}"
    if missing:
        return f"{head}: no player picture yet for {', '.join(missing)} - the older photo-style thumbnail will be used."
    return head


def render_png(title: str, picks: dict | None = None, width: int = 720, style: str | None = None,
               photos: dict | None = None) -> bytes | None:
    """The preview as PNG bytes (Tk can show these directly), or None if the title does not give two teams with pictures."""
    rgb = thumbnail.preview_rgb(title, picks, style=style, photos=photos)
    if rgb is None:
        return None
    from PIL import Image
    im = Image.fromarray(rgb)
    im = im.resize((width, int(width * im.height / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
