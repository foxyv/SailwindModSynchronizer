from __future__ import annotations

import subprocess
from pathlib import Path

from sailwind_mod_sync.constants import GAME_EXE_NAME


def launch_modded(
    game_dir: Path,
    preloader: Path,
    dll_search_path: Path | None = None,
) -> subprocess.Popen:
    exe = game_dir / GAME_EXE_NAME
    if not exe.exists():
        raise FileNotFoundError(f"{GAME_EXE_NAME} not found in {game_dir}")
    if not preloader.exists():
        raise FileNotFoundError(f"BepInEx preloader not found: {preloader}")
    args = [
        str(exe),
        "--doorstop-enabled",
        "true",
        "--doorstop-target-assembly",
        str(preloader),
    ]
    if dll_search_path is not None:
        args.extend(["--doorstop-mono-dll-search-path-override", str(dll_search_path)])
    return subprocess.Popen(args, cwd=str(game_dir))


def launch_vanilla(game_dir: Path) -> subprocess.Popen:
    exe = game_dir / GAME_EXE_NAME
    if not exe.exists():
        raise FileNotFoundError(f"{GAME_EXE_NAME} not found in {game_dir}")
    args = [str(exe), "--doorstop-enabled", "false"]
    return subprocess.Popen(args, cwd=str(game_dir))
