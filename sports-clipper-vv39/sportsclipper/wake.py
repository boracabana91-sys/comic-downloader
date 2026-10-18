"""vv20: wake the Mac for scheduled scans, and keep it awake while the app runs.

`pmset repeat wakeorpoweron` needs the Mac password, which macOS asks for in its own box. Nothing is stored:
the app never keeps your password or a standing admin rule. The Mac wakes every day at the time chosen; from
then on the app holds it awake (caffeinate) while Start 24/7 is running, so one daily wake is enough.
"""
from __future__ import annotations
import subprocess
import sys
from datetime import datetime, timedelta


def is_mac() -> bool:
    return sys.platform == "darwin"


def first_scan_time(sched: dict, now: datetime | None = None) -> str:
    """HH:MM of the earliest scan of the day (times mode), else 2 min before the next interval scan."""
    now = now or datetime.now()
    if sched.get("mode") == "times":
        ts = sorted(t for t in sched.get("times", []) if len(t.split(":")) == 2)
        if ts:
            return ts[0]
    return (now + timedelta(hours=float(sched.get("hours", 2)))).strftime("%H:%M")


def wake_hhmm(scan_hhmm: str, lead_min: int = 2) -> str:
    h, m = [int(x) for x in scan_hhmm.split(":")]
    t = (datetime(2000, 1, 1, h, m) - timedelta(minutes=lead_min))
    return t.strftime("%H:%M")


def pmset_command(wake_at: str) -> str:
    return f"/usr/bin/pmset repeat wakeorpoweron MTWRFSU {wake_at}:00"


def setup(sched: dict, log=print) -> bool:
    if not is_mac():
        log("auto wake-up only exists on a Mac"); return False
    at = wake_hhmm(first_scan_time(sched))
    try:
        subprocess.run(["osascript", "-e", f'do shell script "{pmset_command(at)}" with administrator privileges'],
                       check=True, capture_output=True, text=True, timeout=180)
    except Exception as e:
        log(f"auto wake-up was NOT set: {getattr(e, 'stderr', '') or e}"); return False
    log(f"auto wake-up is set: the Mac wakes every day at {at} (2 min before the first scan). "
        "Keep it plugged in and keep the app open with Start 24/7 pressed.")
    return True


class KeepAwake:
    """`caffeinate` holds the Mac awake while it is open."""
    def __init__(self):
        self.p = None

    def __enter__(self):
        if is_mac():
            try:
                self.p = subprocess.Popen(["caffeinate", "-i"])
            except OSError:
                self.p = None
        return self

    def __exit__(self, *a):
        if self.p:
            self.p.terminate()
