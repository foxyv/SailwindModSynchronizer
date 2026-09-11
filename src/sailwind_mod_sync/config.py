from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from sailwind_mod_sync.constants import CONFIG_FILENAME
from sailwind_mod_sync.paths import AppPaths


@dataclass
class AppConfig:
    game_path: str = ""
    github_token: str = ""
    last_pack_id: str = ""
    warn_missing_mods: bool = True
    check_for_updates: bool = True
    last_update_check: str = ""
    skipped_update_version: str = ""

    def token(self) -> str:
        return self.github_token.strip() or os.environ.get("GITHUB_TOKEN", "").strip()


def load_config(paths: AppPaths) -> AppConfig:
    path = paths.config_file
    if not path.exists():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppConfig()
    if not isinstance(data, dict):
        return AppConfig()
    return AppConfig(
        game_path=str(data.get("game_path") or ""),
        github_token=str(data.get("github_token") or ""),
        last_pack_id=str(data.get("last_pack_id") or ""),
        warn_missing_mods=_as_bool(data.get("warn_missing_mods"), True),
        check_for_updates=_as_bool(data.get("check_for_updates"), True),
        last_update_check=str(data.get("last_update_check") or ""),
        skipped_update_version=str(data.get("skipped_update_version") or ""),
    )


def save_config(paths: AppPaths, config: AppConfig) -> None:
    paths.ensure()
    payload = asdict(config)
    _atomic_write_json(paths.config_file, payload)


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=CONFIG_FILENAME, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        Path(tmp_name).replace(path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
