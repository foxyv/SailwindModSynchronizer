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
from sailwind_mod_sync.game.saves import (
    backup_saves_folder,
    inspect_saves_zip,
    restore_saves_folder,
)
from sailwind_mod_sync.http_util import HttpClient
from sailwind_mod_sync.manager import Manager
from sailwind_mod_sync.models import CatalogEntry
from sailwind_mod_sync.paths import AppPaths
from sailwind_mod_sync.ui.main_window import MainWindow


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


def test_backup_commands_are_under_backup_menu(paths: AppPaths) -> None:
    from PySide6.QtWidgets import QApplication, QPushButton

    app = QApplication.instance() or QApplication([])
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    manager.catalog = [
        CatalogEntry(
            repo="https://github.com/example/mod",
            guids=["com.example.mod"],
            primary_guid="com.example.mod",
            name="mod",
            latest_raw="v1.0.0",
            latest_version="1.0.0",
            available=True,
        )
    ]
    window = MainWindow(manager)
    try:
        labels = [button.text() for button in window.findChildren(QPushButton)]
        assert "Backup BepInEx" not in labels
        assert "Restore BepInEx" not in labels
        backup_menu = next(
            action.menu()
            for action in window.menuBar().actions()
            if action.menu() and action.menu().title().replace("&", "") == "Backup"
        )
        items = [
            action.text().replace("&", "")
            for action in backup_menu.actions()
            if not action.isSeparator()
        ]
        assert items == [
            "Backup BepInEx",
            "Restore BepInEx",
            "Backup saves",
            "Restore saves",
            "Import game plugins",
        ]
        top_level = [action.text().replace("&", "") for action in window.menuBar().actions()]
        assert "Backup BepInEx" not in top_level
        assert "Restore BepInEx" not in top_level
        assert "Backup saves" not in top_level
        assert "Restore saves" not in top_level
        assert "Import game plugins" not in top_level
    finally:
        window.close()
        window.deleteLater()
        manager.close()
    app.processEvents()


def _write_saves_tree(root: Path, slot0: bytes = b"SLOT0") -> Path:
    saves = root / "Sailwind"
    slot_dir = saves / "slot0"
    slot_dir.mkdir(parents=True)
    (saves / "slot0.save").write_bytes(slot0)
    (saves / "slot0.save.png").write_bytes(b"PNG")
    (slot_dir / "com.example.mod.save").write_bytes(b"MOD")
    (saves / "Player.log").write_text("huge log\n", encoding="utf-8")
    (saves / "Player-prev.log").write_text("old log\n", encoding="utf-8")
    unity = saves / "Unity" / "analytics"
    unity.mkdir(parents=True)
    (unity / "config").write_text("skip\n", encoding="utf-8")
    return saves


def test_save_backup_skips_logs_and_unity(tmp_path: Path) -> None:
    source = _write_saves_tree(tmp_path)
    dest = tmp_path / "saves.zip"
    result = backup_saves_folder(source, dest)
    assert result.file_count == 3
    with zipfile.ZipFile(dest) as archive:
        names = set(archive.namelist())
    assert "Sailwind/slot0.save" in names
    assert "Sailwind/slot0.save.png" in names
    assert "Sailwind/slot0/com.example.mod.save" in names
    assert not any(name.lower().endswith(".log") for name in names)
    assert not any("/Unity/" in name or name.endswith("/Unity") for name in names)


def test_inspect_saves_rejects_bepinex_zip(tmp_path: Path) -> None:
    source = _write_bepinex_tree(tmp_path)
    archive = tmp_path / "bepinex.zip"
    backup_bepinex_folder(source, archive)
    with pytest.raises(BackupError, match="not a Sailwind save backup"):
        inspect_saves_zip(archive)


def test_inspect_saves_accepts_files_at_zip_root(tmp_path: Path) -> None:
    archive = tmp_path / "loose.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("slot0.save", b"SLOT")
        zf.writestr("slot0.save.png", b"PNG")
    assert inspect_saves_zip(archive) == ""


def test_restore_saves_backs_up_existing_first(tmp_path: Path) -> None:
    source = _write_saves_tree(tmp_path / "old", slot0=b"NEW")
    archive = tmp_path / "saves.zip"
    backup_saves_folder(source, archive)
    dest = _write_saves_tree(tmp_path / "live", slot0=b"OLD")
    (dest / "stale.save").write_bytes(b"STALE")
    safety = tmp_path / "before.zip"
    result = restore_saves_folder(archive, dest, safety_dest=safety)
    assert result.safety_backup == safety
    assert dest.joinpath("slot0.save").read_bytes() == b"NEW"
    assert not dest.joinpath("stale.save").exists()
    assert dest.joinpath("Player.log").read_text(encoding="utf-8") == "huge log\n"
    assert dest.joinpath("Unity", "analytics", "config").is_file()
    with zipfile.ZipFile(safety) as zf:
        assert zf.read("Sailwind/slot0.save") == b"OLD"
        assert zf.read("Sailwind/stale.save") == b"STALE"


def test_restore_saves_skips_safety_backup_when_empty(tmp_path: Path) -> None:
    source = _write_saves_tree(tmp_path / "old")
    archive = tmp_path / "saves.zip"
    backup_saves_folder(source, archive)
    dest = tmp_path / "empty" / "Sailwind"
    safety = tmp_path / "unused.zip"
    result = restore_saves_folder(archive, dest, safety_dest=safety)
    assert result.safety_backup is None
    assert not safety.exists()
    assert dest.joinpath("slot0.save").read_bytes() == b"SLOT0"


def test_manager_backup_and_restore_saves(paths: AppPaths, tmp_path: Path) -> None:
    saves = _write_saves_tree(tmp_path / "game", slot0=b"LIVE")
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    archive = tmp_path / "saves.zip"
    backed = manager.backup_saves(archive, source=saves)
    assert backed.file_count == 3
    (saves / "slot0.save").write_bytes(b"CHANGED")
    safety = tmp_path / "auto.zip"
    restored = manager.restore_saves(archive, dest=saves, safety_dest=safety)
    assert restored.dest == saves
    assert saves.joinpath("slot0.save").read_bytes() == b"LIVE"
    assert safety.is_file()
    with zipfile.ZipFile(safety) as zf:
        assert zf.read("Sailwind/slot0.save") == b"CHANGED"
