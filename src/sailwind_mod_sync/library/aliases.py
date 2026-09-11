from __future__ import annotations

import json
import logging

from sailwind_mod_sync.paths import AppPaths

log = logging.getLogger(__name__)


def load_aliases(paths: AppPaths) -> dict[str, str]:
    path = paths.aliases_file
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("Could not read mod aliases from %s", path)
        return {}
    if not isinstance(data, dict):
        return {}
    aliases: dict[str, str] = {}
    for key, value in data.items():
        guid = str(key).strip()
        name = str(value).strip()
        if guid and name:
            aliases[guid] = name
    return aliases


def save_aliases(paths: AppPaths, aliases: dict[str, str]) -> None:
    paths.aliases_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {guid: name for guid, name in sorted(aliases.items()) if guid and name}
    paths.aliases_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
