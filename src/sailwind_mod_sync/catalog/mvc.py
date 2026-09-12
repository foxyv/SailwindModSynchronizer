from __future__ import annotations

import json

from sailwind_mod_sync.catalog.custom import load_custom_catalog, merge_with_custom
from sailwind_mod_sync.constants import (
    GITHUB_RAW_MODLIST,
    GITHUB_RAW_VERSIONS,
    JSDELIVR_MODLIST,
    JSDELIVR_VERSIONS,
)
from sailwind_mod_sync.http_util import HttpClient, HttpError, ProgressFn
from sailwind_mod_sync.models import CatalogEntry, catalog_mod_name, guid_family, parse_mod_version
from sailwind_mod_sync.paths import AppPaths


def refresh_catalog(
    paths: AppPaths,
    http: HttpClient,
    progress: ProgressFn | None = None,
) -> list[CatalogEntry]:
    if progress:
        progress("Fetching ModVersionChecker catalog…")
    mod_list = _fetch_json_list(http, JSDELIVR_MODLIST, GITHUB_RAW_MODLIST)
    versions = _fetch_json_list(http, JSDELIVR_VERSIONS, GITHUB_RAW_VERSIONS)
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    paths.modlist_file.write_text(json.dumps(mod_list, indent=2), encoding="utf-8")
    paths.versions_file.write_text(json.dumps(versions, indent=2), encoding="utf-8")
    mvc = merge_catalog(mod_list, versions)
    return merge_with_custom(mvc, load_custom_catalog(paths))


def load_mvc_entries(paths: AppPaths) -> list[CatalogEntry]:
    if not paths.modlist_file.exists() or not paths.versions_file.exists():
        return []
    try:
        mod_list = json.loads(paths.modlist_file.read_text(encoding="utf-8"))
        versions = json.loads(paths.versions_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(mod_list, list) or not isinstance(versions, list):
        return []
    return merge_catalog(mod_list, versions)


def load_cached_catalog(paths: AppPaths) -> list[CatalogEntry] | None:
    mvc = load_mvc_entries(paths)
    custom = load_custom_catalog(paths)
    if not mvc and not custom:
        return None
    return merge_with_custom(mvc, custom)


def merge_catalog(mod_list: list, versions: list) -> list[CatalogEntry]:
    version_by_guid: dict[str, str] = {}
    for item in versions:
        if not isinstance(item, dict):
            continue
        guid = str(item.get("guid") or "").strip()
        raw = item.get("version")
        if guid:
            version_by_guid[guid] = "" if raw is None else str(raw).strip()

    by_key: dict[tuple[str, str], dict] = {}
    families_for_repo: dict[str, set[str]] = {}
    for item in mod_list:
        if not isinstance(item, dict):
            continue
        guid = str(item.get("guid") or "").strip()
        repo = str(item.get("repo") or "").strip().rstrip("/")
        if not guid or not repo:
            continue
        family = guid_family(guid)
        bucket = by_key.setdefault(
            (repo, family),
            {"guids": [], "raw": None, "unavailable": False},
        )
        families_for_repo.setdefault(repo, set()).add(family)
        if guid not in bucket["guids"]:
            bucket["guids"].append(guid)
        raw = version_by_guid.get(guid)
        if raw is None:
            continue
        if raw.lower() == "none":
            if bucket["raw"] is None:
                bucket["unavailable"] = True
            continue
        if raw:
            bucket["raw"] = raw
            bucket["unavailable"] = False

    entries: list[CatalogEntry] = []
    for (repo, _family), bucket in by_key.items():
        guids: list[str] = bucket["guids"]
        primary = _pick_primary_guid(guids)
        raw = bucket["raw"]
        normalized = parse_mod_version(raw)
        available = bool(normalized) and not bucket["unavailable"]
        split_repo = len(families_for_repo.get(repo, ())) > 1
        entries.append(
            CatalogEntry(
                repo=repo,
                guids=list(guids),
                primary_guid=primary,
                name=_name_from_guid(primary) if split_repo else _name_from_repo(repo),
                latest_raw=raw,
                latest_version=normalized,
                available=available,
            )
        )
    entries.sort(key=lambda entry: entry.name.lower())
    return entries


def find_entry(entries: list[CatalogEntry], guid: str) -> CatalogEntry | None:
    for entry in entries:
        if guid in entry.guids or entry.primary_guid == guid:
            return entry
    return None


def _fetch_json_list(http: HttpClient, primary: str, fallback: str) -> list:
    try:
        data, _, _ = http.get_json(primary)
    except HttpError:
        data, _, _ = http.get_json(fallback)
    if not isinstance(data, list):
        raise HttpError("Catalog JSON was not a list")
    return data


def _name_from_repo(repo: str) -> str:
    return repo.rstrip("/").split("/")[-1] or repo


def _name_from_guid(guid: str) -> str:
    return catalog_mod_name(guid)


def _pick_primary_guid(guids: list[str]) -> str:
    if not guids:
        return ""
    ranked = sorted(guids, key=lambda g: (0 if "82" in g else 1, -len(g), g))
    return ranked[0]
