from __future__ import annotations

import logging
from pathlib import Path

from sailwind_mod_sync.catalog.github import fetch_release, pick_release_asset, release_version
from sailwind_mod_sync.catalog.thunderstore import download_bepinex_pack, latest_bepinex_version
from sailwind_mod_sync.constants import DEFAULT_BEPINEX_VERSION
from sailwind_mod_sync.http_util import HttpClient, ProgressFn
from sailwind_mod_sync.library.special_mods import artifact_needs_refetch, known_repo_for
from sailwind_mod_sync.library.store import LibraryStore
from sailwind_mod_sync.models import ArtifactMeta

log = logging.getLogger(__name__)


def ensure_mod_artifact(
    store: LibraryStore,
    http: HttpClient,
    *,
    guid: str,
    repo: str,
    version: str | None = None,
    version_raw: str | None = None,
    plugin_folders: list[str] | None = None,
    progress: ProgressFn | None = None,
) -> ArtifactMeta:
    repo = (repo or "").strip() or (known_repo_for(guid) or "")
    log.info("ensure_mod_artifact guid=%s version=%s repo=%s", guid, version, repo)
    if version:
        cached = _reuse_or_filter_cache(store, guid, version, repo, plugin_folders)
        if cached is not None:
            return cached
    if version and artifact_needs_refetch(store, guid, version):
        log.info("Cached %s %s is incomplete; re-fetching official zip", guid, version)

    release = _fetch_needed_release(http, store, repo, version, version_raw, progress)
    remote_version = release_version(release) or version
    if not remote_version:
        raise RuntimeError(f"Could not parse version from {repo} tag {release.tag!r}")

    cached = _reuse_or_filter_cache(store, guid, remote_version, repo, plugin_folders)
    if cached is not None:
        log.info("Using cached artifact %s %s after release check", guid, remote_version)
        return cached

    repo_name = repo.rstrip("/").split("/")[-1]
    asset = pick_release_asset(release.assets, guid, repo_name, extra_hints=plugin_folders or ())
    log.info("Selected asset %s for %s from %s", asset.name, guid, repo)
    dest_dir = store.mod_dir(guid, remote_version)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / asset.name
    if progress:
        progress(f"Downloading {asset.name}…")
    http.download(asset.download_url, dest, progress=progress)
    version_raw = release.tag or remote_version
    if asset.name.lower().endswith(".dll"):
        return store.ingest_plugin_paths(
            guid,
            remote_version,
            [dest],
            version_raw=version_raw,
            repo=repo,
            source_url=asset.download_url,
        )
    return store.ingest_mod_zip(
        guid,
        remote_version,
        dest,
        version_raw=version_raw,
        repo=repo,
        source_url=asset.download_url,
        filename=asset.name,
        keep_folders=plugin_folders,
    )


def ensure_bepinex(
    store: LibraryStore,
    http: HttpClient,
    version: str | None = None,
    progress: ProgressFn | None = None,
) -> tuple[str, Path]:
    resolved = version or DEFAULT_BEPINEX_VERSION
    if version is None:
        if progress:
            progress("Resolving BepInExPack…")
        try:
            resolved = latest_bepinex_version(http)
        except Exception:
            resolved = DEFAULT_BEPINEX_VERSION
    if not store.has_bepinex(resolved):
        log.info("BepInEx %s not in library; downloading", resolved)
        zip_path = store.bepinex_zip_path(resolved)
        download_bepinex_pack(http, zip_path, resolved, progress=progress)
        store.ingest_bepinex_zip(resolved, zip_path)
    else:
        log.info("Using cached BepInEx %s", resolved)
    return resolved, store.bepinex_extracted(resolved)


def _cached_artifact_usable(
    store: LibraryStore,
    guid: str,
    version: str,
    plugin_folders: list[str] | None = None,
) -> bool:
    if not store.has_mod(guid, version) or artifact_needs_refetch(store, guid, version):
        return False
    if not plugin_folders:
        return True
    meta = store.read_mod_meta(guid, version)
    if meta is None:
        return False
    have = {name.lower() for name in meta.plugin_folders}
    want = {name.lower() for name in plugin_folders if name}
    return bool(want) and have == want


def _reuse_or_filter_cache(
    store: LibraryStore,
    guid: str,
    version: str,
    repo: str,
    plugin_folders: list[str] | None,
) -> ArtifactMeta | None:
    if _cached_artifact_usable(store, guid, version, plugin_folders):
        existing = store.read_mod_meta(guid, version)
        if existing:
            log.info("Using cached artifact %s %s", guid, version)
            return existing
    if not plugin_folders or artifact_needs_refetch(store, guid, version):
        return None
    zip_path = store.mod_zip_path(guid, version)
    meta = store.read_mod_meta(guid, version)
    if meta is None or not zip_path.exists() or zip_path.suffix.lower() != ".zip":
        return None
    log.info("Re-extracting %s %s to keep folders %s", guid, version, plugin_folders)
    return store.ingest_mod_zip(
        guid,
        version,
        zip_path,
        version_raw=meta.version_raw,
        repo=repo or meta.repo,
        source_url=meta.source_url,
        filename=meta.filename,
        keep_folders=plugin_folders,
    )


def _fetch_needed_release(http, store, repo, version, version_raw, progress):
    if not version:
        return fetch_release(http, repo, tag=None, paths=store.paths, progress=progress)

    tags: list[str] = []
    if version_raw:
        tags.append(version_raw)
    if not version.lower().startswith("v"):
        tags.append(f"v{version}")
    tags.append(version)
    seen: set[str] = set()
    last_error: Exception | None = None
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        try:
            return fetch_release(http, repo, tag=tag, paths=store.paths, progress=progress)
        except Exception as exc:
            log.info("No release for %s tag %s: %s", repo, tag, exc)
            last_error = exc
    raise last_error or RuntimeError(f"No GitHub/GitLab release for {repo} {version}")
