"""When to scan. Two modes: every N hours, or at fixed clock times (HH:MM, local)."""
from __future__ import annotations
from datetime import datetime, timedelta


def next_scan(now: datetime, sched: dict, last: datetime | None = None) -> datetime:
    if sched.get("mode") == "times":
        slots = []
        for t in sched.get("times", []):
            try:
                h, m = [int(x) for x in t.split(":")]
                slots.append(h * 60 + m)
            except ValueError:
                continue
        if not slots:
            return now + timedelta(hours=2)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for day in (0, 1):
            for s in sorted(slots):
                cand = today + timedelta(days=day, minutes=s)
                if cand > now:
                    return cand
    hours = max(0.05, float(sched.get("hours", 2)))
    cand = (last or now) + timedelta(hours=hours)
    return cand if cand > now else now
