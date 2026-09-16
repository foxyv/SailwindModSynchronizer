from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sailwind_mod_sync.constants import GAME_EXE_NAME, STEAM_APP_ID


def steam_launch_uri() -> str:
    """URL that hands a Sailwind launch to the Steam client."""
    return f"steam://rungameid/{STEAM_APP_ID}"


def open_steam_launch() -> None:
    """Ask Steam to start Sailwind.

    Mods are loaded automatically because Doorstop (winhttp.dll +
    doorstop_config.ini pointing at the pack's preloader) is already installed in
    the game folder before launch. No command-line args reach the game via Steam,
    so the Doorstop config file is the only thing that enables or disables it.
    """
    uri = steam_launch_uri()
    if os.name == "nt":
        try:
            os.startfile(uri)
        except OSError as exc:
            raise RuntimeError(f"Could not open Steam for {uri}: {exc}") from exc
        return
    subprocess.Popen(
        ["steam", uri],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def launch_modded(
    game_dir: Path,
    preloader: Path,
    dll_search_path: Path | None = None,
) -> None:
    exe = game_dir / GAME_EXE_NAME
    if not exe.exists():
        raise FileNotFoundError(f"{GAME_EXE_NAME} not found in {game_dir}")
    if not preloader.exists():
        raise FileNotFoundError(f"BepInEx preloader not found: {preloader}")
    open_steam_launch()


def launch_vanilla(game_dir: Path) -> None:
    exe = game_dir / GAME_EXE_NAME
    if not exe.exists():
        raise FileNotFoundError(f"{GAME_EXE_NAME} not found in {game_dir}")
    open_steam_launch()