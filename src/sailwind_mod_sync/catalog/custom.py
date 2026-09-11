from __future__ import annotations

import json
import logging

from sailwind_mod_sync.catalog.github import canonicalize_repo_url
from sailwind_mod_sync.models import CatalogEntry, parse_mod_version
from sailwind_mod_sync.paths import AppPaths

log = logging.getLogger(__name__)


def load_custom_catalog(paths: AppPaths) -> list[CatalogEntry]:
    path = paths.custom_catalog_file
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    entries: list[CatalogEntry] = []
    for item in data:
        entry = _entry_from_dict(item)
        if entry is not None:
            entries.append(entry)
    return entries


def save_custom_catalog(paths: AppPaths, entries: list[CatalogEntry]) -> None:
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    payload = [_entry_to_dict(entry) for entry in entries]
    paths.custom_catalog_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def upsert_custom_entry(entries: list[CatalogEntry], incoming: CatalogEntry) -> list[CatalogEntry]:
    out: list[CatalogEntry] = []
    replaced = False
    for entry in entries:
        if same_repo(entry.repo, incoming.repo):
            out.append(incoming)
            replaced = True
        else:
            out.append(entry)
    if not replaced:
        out.append(incoming)
    return out


def remove_custom_entry(entries: list[CatalogEntry], guid: str) -> list[CatalogEntry]:
    wanted = (guid or "").strip()
    return [
        entry
        for entry in entries
        if wanted not in entry.guids and entry.primary_guid != wanted
    ]


def merge_with_custom(mvc: list[CatalogEntry], custom: list[CatalogEntry]) -> list[CatalogEntry]:
    repos = {_repo_key(entry.repo) for entry in mvc}
    guids = {guid for entry in mvc for guid in entry.guids}
    extra: list[CatalogEntry] = []
    for entry in custom:
        entry.custom = True
        if _repo_key(entry.repo) in repos:
            continue
        if any(guid in guids for guid in entry.guids):
            continue
        extra.append(entry)
    combined = list(mvc) + extra
    combined.sort(key=lambda item: item.name.lower())
    return combined


def same_repo(left: str, right: str) -> bool:
    return _repo_key(left) == _repo_key(right) and bool(_repo_key(left))


def _repo_key(repo: str) -> str:
    text = (repo or "").strip().rstrip("/")
    if not text:
        return ""
    try:
        text = canonicalize_repo_url(text)
    except ValueError:
        pass
    return text.lower()


def _entry_from_dict(data: object) -> CatalogEntry | None:
    if not isinstance(data, dict):
        return None
    repo = str(data.get("repo") or "").strip()
    guids_raw = data.get("guids") or []
    if not isinstance(guids_raw, list):
        guids_raw = []
    guids = [str(item).strip() for item in guids_raw if str(item).strip()]
    primary = str(data.get("primary_guid") or "").strip() or (guids[0] if guids else "")
    if not repo or not primary:
        return None
    if primary not in guids:
        guids.insert(0, primary)
    raw = data.get("latest_raw")
    raw_text = None if raw is None else str(raw).strip()
    version = parse_mod_version(str(data.get("latest_version") or raw_text or ""))
    name = str(data.get("name") or "").strip() or repo.rstrip("/").split("/")[-1]
    return CatalogEntry(
        repo=repo,
        guids=guids,
        primary_guid=primary,
        name=name,
        latest_raw=raw_text,
        latest_version=version,
        available=bool(version),
        custom=True,
    )


def _entry_to_dict(entry: CatalogEntry) -> dict:
    return {
        "repo": entry.repo,
        "guids": list(entry.guids),
        "primary_guid": entry.primary_guid,
        "name": entry.name,
        "latest_raw": entry.latest_raw,
        "latest_version": entry.latest_version,
    }
