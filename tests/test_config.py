from __future__ import annotations

import json

from sailwind_mod_sync.config import AppConfig, load_config, save_config
from sailwind_mod_sync.paths import AppPaths


def test_load_config_defaults_warn_missing_mods(paths: AppPaths) -> None:
    config = load_config(paths)
    assert config.warn_missing_mods is True


def test_save_and_load_warn_missing_mods(paths: AppPaths) -> None:
    save_config(paths, AppConfig(warn_missing_mods=False))
    loaded = load_config(paths)
    assert loaded.warn_missing_mods is False
    payload = json.loads(paths.config_file.read_text(encoding="utf-8"))
    assert payload["warn_missing_mods"] is False


def test_old_config_without_flag_warns_by_default(paths: AppPaths) -> None:
    paths.config_file.write_text(
        json.dumps({"game_path": "D:/Sailwind", "github_token": "", "last_pack_id": "a"}),
        encoding="utf-8",
    )
    loaded = load_config(paths)
    assert loaded.warn_missing_mods is True
    assert loaded.game_path == "D:/Sailwind"
