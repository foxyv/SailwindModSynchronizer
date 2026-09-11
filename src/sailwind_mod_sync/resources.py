from __future__ import annotations

import sys
from pathlib import Path


def icon_path() -> Path | None:
    names = ("icon.ico", "icon.png")
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass)
        for name in names:
            candidates.append(bundled / "assets" / name)
            candidates.append(bundled / name)
    here = Path(__file__).resolve().parent
    repo_assets = here.parent.parent / "assets"
    for name in names:
        candidates.append(repo_assets / name)
        candidates.append(here / "assets" / name)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for name in names:
            candidates.append(exe_dir / "assets" / name)
            candidates.append(exe_dir / name)
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return None
