from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from sailwind_mod_sync.config import AppConfig
from sailwind_mod_sync.game.backup import (
    BackupError,
    backup_bepinex_folder,
    inspect_bepinex_zip,
    is_valid_bepinex_directory,
    restore_bepinex_folder,
)
from sailwind_mod_sync.http_util import HttpClient
from sailwind_mod_sync.manager import Manager
from sailwind_mod_sync.paths import AppPaths


class _NoHttp(HttpClient):
    def __init__(self) -> None:
        self.token = ""
        self._owns_client = False
        self._client = None

    def close(self) -> None:
        return None


def _write_bepinex_tree(root: Path) -> Path:
    bepinex = root / "BepInEx"
    plugin = bepinex / "plugins" / "Dizzy.Gamma"
    plugin.mkdir(parents=True)
    (plugin / "Dizzy.Gamma.dll").write_bytes(b"MZ")
    config = bepinex / "config"
    config.mkdir()
    (config / "BepInEx.cfg").write_text("[Logging]\n", encoding="utf-8")
    (bepinex / "LogOutput.log").write_text("ok\n", encoding="utf-8")
    return bepinex


def test_backup_zips_plugins_and_config(tmp_path: Path) -> None:
    source = _write_bepinex_tree(tmp_path)
    dest = tmp_path / "out" / "backup.zip"
    result = backup_bepinex_folder(source, dest)
    assert result.dest == dest
    assert result.file_count == 3
    assert result.skipped == 0
    with zipfile.ZipFile(dest) as archive:
        names = set(archive.namelist())
    assert "BepInEx/plugins/Dizzy.Gamma/Dizzy.Gamma.dll" in names
    assert "BepInEx/config/BepInEx.cfg" in names
    assert "BepInEx/LogOutput.log" in names


def test_manager_backs_up_game_bepinex(paths: AppPaths, tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    (game / "Sailwind.exe").write_bytes(b"MZ")
    _write_bepinex_tree(game)
    manager = Manager(paths=paths, config=AppConfig(game_path=str(game)), http=_NoHttp())
    dest = tmp_path / "bepinex.zip"
    result = manager.backup_bepinex(dest)
    assert result.dest == dest
    assert result.source == game / "BepInEx"
    assert dest.is_file()


def test_manager_falls_back_to_pack_bepinex(paths: AppPaths, tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    (game / "Sailwind.exe").write_bytes(b"MZ")
    manager = Manager(paths=paths, config=AppConfig(game_path=str(game)), http=_NoHttp())
    pack = manager.packs.create("Dev")
    _write_bepinex_tree(manager.packs.instance_dir(pack.id))
    source, kind = manager.resolve_bepinex_folder(pack.id)
    assert kind == "pack"
    assert source == manager.packs.instance_dir(pack.id) / "BepInEx"
    dest = tmp_path / "pack.zip"
    result = manager.backup_bepinex(dest, pack_id=pack.id)
    assert result.file_count >= 1
    assert dest.is_file()


def test_restore_roundtrip_replaces_folder(tmp_path: Path) -> None:
    source = _write_bepinex_tree(tmp_path / "game")
    archive = tmp_path / "backup.zip"
    backup_bepinex_folder(source, archive)
    (source / "plugins" / "Dizzy.Gamma" / "Dizzy.Gamma.dll").write_bytes(b"CHANGED")
    dest = tmp_path / "restored" / "BepInEx"
    dest.mkdir(parents=True)
    (dest / "stale.txt").write_text("nope", encoding="utf-8")
    result = restore_bepinex_folder(archive, dest)
    assert result.file_count == 3
    assert (dest / "plugins" / "Dizzy.Gamma" / "Dizzy.Gamma.dll").read_bytes() == b"MZ"
    assert not (dest / "stale.txt").exists()
    assert is_valid_bepinex_directory(dest)


def test_inspect_rejects_random_zip(tmp_path: Path) -> None:
    archive = tmp_path / "notes.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    with pytest.raises(BackupError, match="not a BepInEx backup"):
        inspect_bepinex_zip(archive)


def test_inspect_rejects_mod_zip(tmp_path: Path) -> None:
    archive = tmp_path / "mod.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Dizzy.Gamma/Dizzy.Gamma.dll", b"MZ")
    with pytest.raises(BackupError, match="not a BepInEx backup"):
        inspect_bepinex_zip(archive)


def test_inspect_accepts_bepinex_contents_at_zip_root(tmp_path: Path) -> None:
    archive = tmp_path / "loose.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("plugins/Foo/Foo.dll", b"MZ")
        zf.writestr("config/BepInEx.cfg", "[Logging]\n")
    assert inspect_bepinex_zip(archive) == ""


def test_manager_restore_to_game_bepinex(paths: AppPaths, tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    (game / "Sailwind.exe").write_bytes(b"MZ")
    source = _write_bepinex_tree(game)
    archive = tmp_path / "backup.zip"
    backup_bepinex_folder(source, archive)
    (source / "plugins" / "Dizzy.Gamma" / "Dizzy.Gamma.dll").write_bytes(b"OLD")
    manager = Manager(paths=paths, config=AppConfig(game_path=str(game)), http=_NoHttp())
    result = manager.restore_bepinex(archive)
    assert result.dest == game / "BepInEx"
    assert (game / "BepInEx" / "plugins" / "Dizzy.Gamma" / "Dizzy.Gamma.dll").read_bytes() == b"MZ"
