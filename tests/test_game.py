from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from sailwind_mod_sync.game.bepinex import doorstop_installed, write_doorstop_config
from sailwind_mod_sync.game.detect import steam_libraries_from_vdf
from sailwind_mod_sync.game.launch import launch_modded, launch_vanilla
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


def test_launch_args(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    exe = game / "Sailwind.exe"
    exe.write_bytes(b"MZ")
    preloader = tmp_path / "BepInEx.Preloader.dll"
    preloader.write_bytes(b"MZ")
    with patch("sailwind_mod_sync.game.launch.subprocess.Popen") as popen:
        popen.return_value = MagicMock()
        launch_modded(game, preloader)
        args = popen.call_args[0][0]
        assert args[0] == str(exe)
        assert "--doorstop-enabled" in args
        assert "--doorstop-target-assembly" in args
        assert str(preloader) in args
        assert "--doorstop-mono-dll-search-path-override" not in args


def test_launch_modded_sets_dll_search_path(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    exe = game / "Sailwind.exe"
    exe.write_bytes(b"MZ")
    preloader = tmp_path / "BepInEx.Preloader.dll"
    preloader.write_bytes(b"MZ")
    search = tmp_path / "instance" / "BepInEx" / "plugins" / "SailwindCoop"
    with patch("sailwind_mod_sync.game.launch.subprocess.Popen") as popen:
        popen.return_value = MagicMock()
        launch_modded(game, preloader, dll_search_path=search)
        args = popen.call_args[0][0]
        assert "--doorstop-mono-dll-search-path-override" in args
        assert str(search) in args


def test_launch_vanilla_disables_doorstop(tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    exe = game / "Sailwind.exe"
    exe.write_bytes(b"MZ")
    with patch("sailwind_mod_sync.game.launch.subprocess.Popen") as popen:
        popen.return_value = MagicMock()
        launch_vanilla(game)
        args = popen.call_args[0][0]
        assert args[0] == str(exe)
        assert args[1:3] == ["--doorstop-enabled", "false"]
        assert "--doorstop-target-assembly" not in args
