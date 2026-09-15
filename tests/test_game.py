from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from sailwind_mod_sync.game.bepinex import doorstop_installed, write_doorstop_config
from sailwind_mod_sync.game.detect import steam_libraries_from_vdf
from sailwind_mod_sync.game.launch import (
    launch_modded,
    launch_vanilla,
    open_steam_launch,
    steam_launch_uri,
)
from sailwind_mod_sync.packs.instance import ensure_instance_bepinex


def test_parse_libraryfolders() -> None:
    text = """
"libraryfolders"
{
    "0"
    {
        "path"        "C:\\\\Program Files (x86)\\\\Steam"
    }
    "1"
    {
        "path"        "D:\\\\SteamLibrary"
    }
}
"""
    paths = steam_libraries_from_vdf(text)
    assert Path(r"C:\Program Files (x86)\Steam") in paths
    assert Path(r"D:\SteamLibrary") in paths


def test_doorstop_config(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    preloader = tmp_path / "instance" / "BepInEx" / "core" / "BepInEx.Preloader.dll"
    write_doorstop_config(game, preloader)
    text = (game / "doorstop_config.ini").read_text(encoding="utf-8")
    assert "enabled = true" in text
    assert str(preloader) in text
    assert "dll_search_path_override =" in text
    assert not doorstop_installed(game)


def test_doorstop_config_sets_search_path(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    preloader = tmp_path / "instance" / "BepInEx" / "core" / "BepInEx.Preloader.dll"
    search = tmp_path / "instance" / "BepInEx" / "plugins" / "SailwindCoop"
    write_doorstop_config(game, preloader, dll_search_path=search)
    text = (game / "doorstop_config.ini").read_text(encoding="utf-8")
    assert f"dll_search_path_override = {search}" in text


def test_ensure_instance_copies_core(tmp_path: Path) -> None:
    extracted = tmp_path / "bx"
    core = extracted / "BepInEx" / "core"
    core.mkdir(parents=True)
    (core / "BepInEx.Preloader.dll").write_bytes(b"MZ")
    (extracted / "BepInEx" / "patchers").mkdir()
    instance = tmp_path / "instance"
    preloader = ensure_instance_bepinex(instance, extracted)
    assert preloader.exists()
    assert (instance / "BepInEx" / "plugins").is_dir()


def test_steam_launch_uri_uses_sailwind_appid() -> None:
    assert steam_launch_uri() == "steam://rungameid/1764530"


@pytest.mark.skipif(os.name != "nt", reason="os.startfile only exists on Windows")
def test_open_steam_launch_uses_uri_handler() -> None:
    with patch("sailwind_mod_sync.game.launch.os.startfile") as startfile:
        open_steam_launch()
    startfile.assert_called_once_with("steam://rungameid/1764530")


def test_launch_modded_opens_steam(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    exe = game / "Sailwind.exe"
    exe.write_bytes(b"MZ")
    preloader = tmp_path / "BepInEx.Preloader.dll"
    preloader.write_bytes(b"MZ")
    search = tmp_path / "instance" / "BepInEx" / "plugins" / "SailwindCoop"
    with patch("sailwind_mod_sync.game.launch.open_steam_launch") as open_steam:
        result = launch_modded(game, preloader, dll_search_path=search)
    assert result is None
    open_steam.assert_called_once()


def test_launch_modded_requires_exe_and_preloader(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    exe = game / "Sailwind.exe"
    preloader = tmp_path / "BepInEx.Preloader.dll"
    preloader.write_bytes(b"MZ")

    # Missing game executable.
    with patch("sailwind_mod_sync.game.launch.open_steam_launch") as open_steam:
        with pytest.raises(FileNotFoundError):
            launch_modded(game, preloader)
        open_steam.assert_not_called()

    # Missing preloader.
    exe.write_bytes(b"MZ")
    with patch("sailwind_mod_sync.game.launch.open_steam_launch") as open_steam:
        with pytest.raises(FileNotFoundError):
            launch_modded(game, tmp_path / "Missing.Preloader.dll")
        open_steam.assert_not_called()


def test_launch_vanilla_opens_steam(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    exe = game / "Sailwind.exe"
    exe.write_bytes(b"MZ")
    with patch("sailwind_mod_sync.game.launch.open_steam_launch") as open_steam:
        result = launch_vanilla(game)
    assert result is None
    open_steam.assert_called_once()


def test_launch_vanilla_requires_exe(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    with patch("sailwind_mod_sync.game.launch.open_steam_launch") as open_steam:
        with pytest.raises(FileNotFoundError):
            launch_vanilla(game)
        open_steam.assert_not_called()


def test_doorstop_config_disables_doorstop(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    write_doorstop_config(game, None, enabled=False)
    text = (game / "doorstop_config.ini").read_text(encoding="utf-8")
    assert "enabled = false" in text
    assert "target_assembly =" in text


def test_doorstop_config_disables_doorstop_without_preloader(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    write_doorstop_config(game, enabled=False)
    text = (game / "doorstop_config.ini").read_text(encoding="utf-8")
    assert "enabled = false" in text
    assert "target_assembly =" in text
