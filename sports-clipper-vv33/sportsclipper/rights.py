"""Rights gate: nothing is downloaded or edited unless the source is marked licensed.

You, the owner, attest that you have permission or a license for each source and
write down where that permission comes from. Sources without both are skipped.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict


class NotLicensed(Exception):
    pass


@dataclass
class Source:
    name: str
    kind: str                 # "folder" | "youtube" | "url"
    location: str             # folder path, channel id / URL, or direct video URL
    licensed: bool = False
    license_note: str = ""    # e.g. "Written permission from X, 2026-10-01"
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Source":
        keys = Source.__dataclass_fields__.keys()
        return Source(**{k: v for k, v in d.items() if k in keys})


def check(src: Source) -> None:
    if not src.licensed or not src.license_note.strip():
        raise NotLicensed(
            f"Source '{src.name}' is not marked licensed with a license note - skipped. "
            "Only sources you have permission to use may be processed.")
