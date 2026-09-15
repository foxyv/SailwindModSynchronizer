from __future__ import annotations

import shutil
from pathlib import Path

DOORSTOP_DLL = "winhttp.dll"
DOORSTOP_CONFIG = "doorstop_config.ini"
DOORSTOP_VERSION = ".doorstop_version"


def doorstop_installed(game_dir: Path) -> bool:
    return (game_dir / DOORSTOP_DLL).exists()


def install_doorstop(
    game_dir: Path,
    bepinex_extracted: Path,
    preloader: Path | None = None,
    dll_search_path: Path | None = None,
) -> None:
    src_dll = bepinex_extracted / DOORSTOP_DLL
    if not src_dll.exists():
        raise FileNotFoundError(f"{DOORSTOP_DLL} missing from BepInExPack at {bepinex_extracted}")
    shutil.copy2(src_dll, game_dir / DOORSTOP_DLL)
    version_src = bepinex_extracted / DOORSTOP_VERSION
    if version_src.exists():
        shutil.copy2(version_src, game_dir / DOORSTOP_VERSION)
    write_doorstop_config(game_dir, preloader, dll_search_path=dll_search_path)


def write_doorstop_config(
    game_dir: Path,
    preloader: Path | None = None,
    dll_search_path: Path | None = None,
    enabled: bool = True,
) -> None:
    target = str(preloader) if preloader else r"BepInEx\core\BepInEx.Preloader.dll"
    override = str(dll_search_path) if dll_search_path is not None else ""
    content = (
        "[General]\n"
        f"enabled = {'true' if enabled else 'false'}\n"
        f"target_assembly = {target}\n"
        "redirect_output_log = false\n"
        "ignore_disable_switch = false\n"
        "\n"
        "[UnityMono]\n"
        f"dll_search_path_override = {override}\n"
        "debug_enabled = false\n"
    )
    (game_dir / DOORSTOP_CONFIG).write_text(content, encoding="utf-8")
