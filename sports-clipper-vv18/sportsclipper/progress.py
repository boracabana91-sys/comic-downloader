"""Live status for the window: which step is running and, where known, percent done.

Steps call set(text, pct). The window registers a listener and shows it, with elapsed time and
how long ago the last update came, so a long render can be seen moving (or seen to be stuck).
"""
from __future__ import annotations

_listeners: list = []


def listen(fn) -> None:
    _listeners.append(fn)


def set(text: str, pct: int | None = None) -> None:
    for fn in list(_listeners):
        try:
            fn(text, pct)
        except Exception:
            pass          # a status display must never stop the job
