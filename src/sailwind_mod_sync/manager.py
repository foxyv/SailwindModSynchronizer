from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from sailwind_mod_sync.catalog.custom import (
    load_custom_catalog,
    merge_with_custom,
    remove_custom_entry,
    save_custom_catalog,
    same_repo,
    upsert_custom_entry,
)
from sailwind_mod_sync.catalog.github import (
    canonicalize_repo_url,
    fetch_readme,
    fetch_release,
    list_releases,
    parse_repo_url,
    release_version,
)
from sailwind_mod_sync.catalog.mvc import find_entry, load_cached_catalog, load_mvc_entries, refresh_catalog
from sailwind_mod_sync.config import AppConfig, load_config, save_config
from sailwind_mod_sync.constants import DEFAULT_BEPINEX_VERSION
from sailwind_mod_sync.game.backup import BackupResult, RestoreResult, backup_bepinex_folder, inspect_bepinex_zip, restore_bepinex_folder
from sailwind_mod_sync.game.bepinex import doorstop_installed, install_doorstop, write_doorstop_config
from sailwind_mod_sync.game.detect import detect_game_path, resolve_game_dir
from sailwind_mod_sync.game.launch import launch_modded, launch_vanilla
from sailwind_mod_sync.game.scan_plugins import discover_local_file, scan_plugins_dir
from sailwind_mod_sync.http_util import HttpClient, ProgressFn
from sailwind_mod_sync.library.aliases import load_aliases, save_aliases
from sailwind_mod_sync.library.download import ensure_bepinex, ensure_mod_artifact
from sailwind_mod_sync.library.special_mods import artifact_ready, coop_dll_search_path, known_repo_for
from sailwind_mod_sync.library.store import LibraryStore
from sailwind_mod_sync.logutil import log_duration, setup_logging
from sailwind_mod_sync.models import (
    CatalogEntry,
    ModDetails,
    ModPack,
    PinnedMod,
    RemoteModInfo,
    catalog_mod_name,
    display_mod_name,
    parse_mod_version,
    version_key,
)
from sailwind_mod_sync.packs.instance import (
    ensure_instance_bepinex,
    install_pinned_into_plugins,
    remove_plugin_folders,
    sync_pack_plugins,
)
from sailwind_mod_sync.packs.modpack import PackStore
from sailwind_mod_sync.paths import AppPaths

log = logging.getLogger(__name__)


class Manager:
    def __init__(
        self,
        paths: AppPaths | None = None,
        config: AppConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.paths = paths or AppPaths()
        self.paths.ensure()
        self._setup_logging()
        self.config = config or load_config(self.paths)
        if not self.config.game_path:
            detected = detect_game_path()
            if detected:
                self.config.game_path = str(detected)
                self.save_config()
        self._owns_http = http is None
        self.http = http or HttpClient(self.config.token())
        self.library = LibraryStore(self.paths)
        self.packs = PackStore(self.paths)
        self.aliases = load_aliases(self.paths)
        self.catalog: list[CatalogEntry] = load_cached_catalog(self.paths) or []
        default_pack = self.packs.ensure_default()
        if not self.config.last_pack_id or not self.packs.exists(self.config.last_pack_id):
            self.config.last_pack_id = default_pack.id
            self.save_config()

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def save_config(self) -> None:
        save_config(self.paths, self.config)

    def reload_http(self) -> None:
        if self._owns_http:
            self.http.close()
            self.http = HttpClient(self.config.token())

    def game_dir(self) -> Path | None:
        return resolve_game_dir(self.config.game_path)

    def resolve_bepinex_folder(self, pack_id: str | None = None) -> tuple[Path, str]:
        game = self.game_dir()
        if game is not None:
            game_bepinex = game / "BepInEx"
            if game_bepinex.is_dir() and any(game_bepinex.iterdir()):
                return game_bepinex, "game"
        if pack_id and self.packs.exists(pack_id):
            pack_bepinex = self.packs.instance_dir(pack_id) / "BepInEx"
            if pack_bepinex.is_dir() and any(pack_bepinex.iterdir()):
                return pack_bepinex, "pack"
        raise FileNotFoundError(
            "No BepInEx folder found in the Sailwind directory or the selected ModPack."
        )

    def backup_bepinex(
        self,
        dest: Path,
        pack_id: str | None = None,
        source: Path | None = None,
        progress: ProgressFn | None = None,
    ) -> BackupResult:
        if source is None:
            source, _kind = self.resolve_bepinex_folder(pack_id)
        if progress:
            progress(f"Zipping {source}…")
        return backup_bepinex_folder(source, dest, progress=progress)

    def resolve_bepinex_restore_target(self, pack_id: str | None = None) -> tuple[Path, str]:
        game = self.game_dir()
        if game is not None:
            return game / "BepInEx", "game"
        if pack_id and self.packs.exists(pack_id):
            return self.packs.instance_dir(pack_id) / "BepInEx", "pack"
        raise FileNotFoundError("Set the Sailwind folder in Settings, or select a ModPack.")

    def restore_bepinex(
        self,
        archive: Path,
        pack_id: str | None = None,
        dest: Path | None = None,
        progress: ProgressFn | None = None,
    ) -> RestoreResult:
        inspect_bepinex_zip(archive)
        if dest is None:
            dest, _kind = self.resolve_bepinex_restore_target(pack_id)
        return restore_bepinex_folder(archive, dest, progress=progress)

    def refresh_catalog(self, progress: ProgressFn | None = None) -> list[CatalogEntry]:
        self.catalog = refresh_catalog(self.paths, self.http, progress=progress)
        return self.catalog

    def scan_updates(self, live: bool = False, progress: ProgressFn | None = None) -> dict[str, str]:
        if not self.catalog:
            self.refresh_catalog(progress=progress)
        latest: dict[str, str] = {}
        for entry in self.catalog:
            if entry.latest_raw:
                latest[entry.primary_guid] = entry.latest_raw
                for guid in entry.guids:
                    latest[guid] = entry.latest_raw
        if not live:
            return latest

        seen_repos: set[str] = set()
        for entry in self.catalog:
            if entry.repo in seen_repos:
                continue
            seen_repos.add(entry.repo)
            try:
                parse_repo_url(entry.repo)
            except ValueError:
                continue
            try:
                release = fetch_release(
                    self.http,
                    entry.repo,
                    tag=None,
                    paths=self.paths,
                    progress=progress,
                )
            except Exception as exc:
                log.warning("Live update check failed for %s: %s", entry.repo, exc)
                continue
            raw = release.tag or release_version(release)
            if not raw:
                continue
            latest[entry.primary_guid] = raw
            for guid in entry.guids:
                latest[guid] = raw
            entry.latest_raw = raw
            entry.latest_version = parse_mod_version(raw)
            entry.available = bool(entry.latest_version)
        custom = [entry for entry in self.catalog if entry.custom]
        if custom:
            save_custom_catalog(self.paths, custom)
        return latest

    def add_catalog_repo(self, repo_url: str, progress: ProgressFn | None = None) -> list[CatalogEntry]:
        repo = canonicalize_repo_url(repo_url)
        ref = parse_repo_url(repo)
        if progress:
            progress(f"Checking {ref.full_path}…")
        release = fetch_release(self.http, repo, tag=None, paths=self.paths, progress=progress)
        version_raw = release.tag or release_version(release)
        version = parse_mod_version(version_raw)
        assets = [
            asset
            for asset in release.assets
            if asset.name
            and asset.download_url
            and asset.name.lower().endswith((".zip", ".dll"))
            and "source" not in asset.name.lower()
        ]
        if not assets:
            names = ", ".join(asset.name for asset in release.assets if asset.name) or "none"
            raise FileNotFoundError(
                f"Release has no zip or dll download (files: {names}). "
                "This GitHub release only has source code, or no files at all."
            )
        discovered = []
        with tempfile.TemporaryDirectory(prefix="sms-catalog-") as tmp:
            for index, asset in enumerate(assets):
                dest = Path(tmp) / (asset.name or f"artifact-{index}")
                if progress:
                    progress(f"Reading {asset.name}…")
                self.http.download(asset.download_url, dest, progress=progress)
                discovered.extend(discover_local_file(dest, catalog=self.catalog))
        custom = load_custom_catalog(self.paths)
        added: list[CatalogEntry] = []
        seen: set[str] = set()
        for unit in discovered:
            guid = (getattr(unit, "guid", None) or "").strip()
            if not guid or guid in seen:
                continue
            existing = find_entry(self.catalog, guid)
            if existing is not None and not existing.custom:
                continue
            seen.add(guid)
            folder = (getattr(unit, "name", None) or "").strip()
            entry = CatalogEntry(
                repo=repo,
                guids=[guid],
                primary_guid=guid,
                name=folder or catalog_mod_name(guid),
                latest_raw=version_raw,
                latest_version=version,
                available=bool(version),
                custom=True,
                plugin_folders=[folder] if folder else [],
            )
            custom = upsert_custom_entry(custom, entry)
            added.append(entry)
        if not added and not discovered:
            fallback = _guids_from_discovered([], ref)
            guid = fallback[0]
            entry = CatalogEntry(
                repo=repo,
                guids=fallback,
                primary_guid=guid,
                name=ref.repo,
                latest_raw=version_raw,
                latest_version=version,
                available=bool(version),
                custom=True,
            )
            custom = upsert_custom_entry(custom, entry)
            added.append(entry)
        if not added:
            raise ValueError(f"All plugins from {repo} are already in the catalog")
        save_custom_catalog(self.paths, custom)
        self.catalog = merge_with_custom(load_mvc_entries(self.paths), custom)
        resolved: list[CatalogEntry] = []
        for entry in added:
            found = find_entry(self.catalog, entry.primary_guid)
            resolved.append(found or entry)
        log.info("Added %s catalog plugin(s) from %s", len(resolved), repo)
        return resolved

    def remove_catalog_repo(self, guid: str) -> None:
        custom = remove_custom_entry(load_custom_catalog(self.paths), guid)
        save_custom_catalog(self.paths, custom)
        self.catalog = merge_with_custom(load_mvc_entries(self.paths), custom)
        log.info("Removed custom catalog entry %s", guid)

    def mod_display_name(
        self,
        guid: str,
        *,
        alias: str | None = None,
        plugin_folders: list[str] | None = None,
        repo: str = "",
    ) -> str:
        catalog = find_entry(self.catalog, guid)
        folders = plugin_folders
        repo_url = repo
        if folders is None or not repo_url:
            for entry in self.library.list_mods():
                if entry.guid != guid:
                    continue
                if folders is None:
                    folders = list(entry.meta.plugin_folders)
                repo_url = repo_url or entry.meta.repo
                break
        if not repo_url:
            for pack in self.packs.list_packs():
                pinned = pack.find_mod(guid)
                if pinned is None:
                    continue
                if folders is None:
                    folders = list(pinned.plugin_folders)
                repo_url = repo_url or pinned.repo
                break
        return display_mod_name(
            guid,
            alias=self.aliases.get(guid, "") if alias is None else alias,
            catalog_name=catalog.name if catalog else "",
            catalog_shared=bool(catalog and len(catalog.guids) > 1),
            plugin_folders=folders,
            repo=repo_url or (catalog.repo if catalog else ""),
        )

    def set_mod_alias(self, guid: str, alias: str) -> str:
        guid = (guid or "").strip()
        if not guid:
            raise ValueError("Mod GUID is empty")
        text = (alias or "").strip()
        default = self.mod_display_name(guid, alias="")
        if not text or text == default:
            self.aliases.pop(guid, None)
        else:
            self.aliases[guid] = text
        save_aliases(self.paths, self.aliases)
        log.info("Set display alias for %s to %r", guid, self.aliases.get(guid, ""))
        return self.mod_display_name(guid)

    def local_mod_details(self, guid: str, version: str) -> ModDetails:
        meta = self.library.read_mod_meta(guid, version)
        if meta is None:
            raise FileNotFoundError(f"{guid} {version} is not in the library")
        installed = sorted(
            {entry.version for entry in self.library.list_mods() if entry.guid == guid},
            key=version_key,
            reverse=True,
        )
        catalog = find_entry(self.catalog, guid)
        name = self.mod_display_name(
            guid,
            plugin_folders=list(meta.plugin_folders),
            repo=meta.repo or (catalog.repo if catalog else ""),
        )
        pack_pins: list[tuple[str, str]] = []
        for pack in self.packs.list_packs():
            pinned = pack.find_mod(guid)
            if pinned:
                pack_pins.append((pack.name, pinned.version))
        size = 0
        for entry in self.library.list_mods():
            if entry.guid == guid and entry.version == version:
                size = entry.size_bytes
                break
        return ModDetails(
            guid=guid,
            version=version,
            name=name,
            repo=meta.repo or (catalog.repo if catalog else ""),
            source_url=meta.source_url,
            filename=meta.filename,
            sha256=meta.sha256,
            downloaded_at=meta.downloaded_at,
            plugin_folders=list(meta.plugin_folders),
            size_bytes=size,
            installed_versions=installed,
            catalog_latest=(catalog.latest_raw if catalog else None),
            pack_pins=pack_pins,
        )

    def catalog_mod_details(self, guid: str) -> ModDetails:
        catalog = find_entry(self.catalog, guid)
        if catalog is None:
            raise FileNotFoundError(f"{guid} is not in the catalog")
        guids = set(catalog.guids) | {catalog.primary_guid, guid}
        matches = [item for item in self.library.list_mods() if item.guid in guids]
        if matches:
            newest = max(matches, key=lambda item: version_key(item.version))
            return self.local_mod_details(newest.guid, newest.version)
        pack_pins: list[tuple[str, str]] = []
        for pack in self.packs.list_packs():
            pinned = None
            for candidate in catalog.guids:
                pinned = pack.find_mod(candidate)
                if pinned is not None:
                    break
            if pinned:
                pack_pins.append((pack.name, pinned.version))
        return ModDetails(
            guid=catalog.primary_guid,
            version=catalog.latest_version or catalog.latest_raw or "",
            name=self.mod_display_name(catalog.primary_guid, repo=catalog.repo),
            repo=catalog.repo,
            source_url="",
            filename="",
            sha256="",
            downloaded_at="",
            plugin_folders=[],
            size_bytes=0,
            installed_versions=[],
            catalog_latest=catalog.latest_raw,
            pack_pins=pack_pins,
        )

    def fetch_remote_mod_info(self, repo: str, progress: ProgressFn | None = None) -> RemoteModInfo:
        info = RemoteModInfo()
        try:
            releases = list_releases(self.http, repo, limit=12, progress=progress)
            tags = [item.tag or item.name for item in releases if item.tag or item.name]
            info.release_tags = tags
            info.latest_tag = tags[0] if tags else ""
        except Exception as exc:
            log.warning("Could not list releases for %s: %s", repo, exc)
            info.releases_error = str(exc).strip() or repr(exc)
        try:
            info.readme = fetch_readme(self.http, repo, progress=progress)
        except Exception as exc:
            log.warning("Could not fetch README for %s: %s", repo, exc)
            info.readme_error = str(exc).strip() or repr(exc)
        return info

    def install_mod(
        self,
        pack_id: str,
        guid: str,
        repo: str | None = None,
        version: str | None = None,
        version_raw: str | None = None,
        progress: ProgressFn | None = None,
    ) -> PinnedMod:
        entry = find_entry(self.catalog, guid)
        repo = repo or (entry.repo if entry else "") or (known_repo_for(guid) or "")
        if not repo:
            raise ValueError(f"No repository known for {guid}")
        if version is None and entry:
            version = entry.latest_version
            version_raw = version_raw or entry.latest_raw
        if not version and version_raw:
            version = parse_mod_version(version_raw)
        if progress:
            progress(f"Fetching {guid} from {repo}…")
        folders = list(entry.plugin_folders) if entry and entry.plugin_folders else None
        meta = ensure_mod_artifact(
            self.library,
            self.http,
            guid=guid,
            repo=repo,
            version=version,
            version_raw=version_raw,
            plugin_folders=folders,
            progress=progress,
        )
        return self.add_library_mod_to_pack(
            pack_id,
            guid,
            meta.version,
            repo=repo,
            progress=progress,
        )

    def list_remote_mod_versions(
        self,
        repo: str,
        progress: ProgressFn | None = None,
    ) -> list[tuple[str, str]]:
        releases = list_releases(self.http, repo, limit=40, progress=progress)
        rows: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in releases:
            raw = (item.tag or item.name or "").strip()
            version = parse_mod_version(raw)
            if not version or version in seen:
                continue
            seen.add(version)
            rows.append((version, raw))
        return rows

    def set_pack_mod_version(
        self,
        pack_id: str,
        guid: str,
        version: str,
        version_raw: str | None = None,
        progress: ProgressFn | None = None,
    ) -> PinnedMod:
        pack = self.packs.get(pack_id)
        pinned = pack.find_mod(guid)
        repo = (pinned.repo if pinned else "") or None
        if self.library.has_mod(guid, version):
            return self.add_library_mod_to_pack(
                pack_id,
                guid,
                version,
                repo=repo,
                progress=progress,
            )
        return self.install_mod(
            pack_id,
            guid,
            repo=repo,
            version=version,
            version_raw=version_raw or version,
            progress=progress,
        )

    def add_library_mod_to_pack(
        self,
        pack_id: str,
        guid: str,
        version: str,
        *,
        repo: str | None = None,
        progress: ProgressFn | None = None,
    ) -> PinnedMod:
        meta = self.library.read_mod_meta(guid, version)
        if meta is None:
            raise FileNotFoundError(f"{guid} {version} is not in the library")
        if progress:
            progress(f"Adding {guid} {meta.version} to the pack…")
        pack = self.packs.get(pack_id)
        previous = pack.find_mod(guid)
        if previous:
            remove_plugin_folders(self.packs.plugins_dir(pack_id), previous.plugin_folders)
        pinned = PinnedMod(
            guid=guid,
            version=meta.version,
            repo=repo or meta.repo,
            enabled=previous.enabled if previous else True,
            plugin_folders=list(meta.plugin_folders),
            version_raw=meta.version_raw,
        )
        folders = install_pinned_into_plugins(
            pinned,
            self.library.mod_extracted(guid, meta.version),
            self.packs.plugins_dir(pack_id),
        )
        pinned.plugin_folders = folders
        if not pinned.enabled:
            remove_plugin_folders(self.packs.plugins_dir(pack_id), pinned.plugin_folders)
        self.packs.upsert_mod(pack_id, pinned)
        return pinned

    def set_mod_repo(self, guid: str, repo: str) -> str:
        page = canonicalize_repo_url(repo)
        for pack in self.packs.list_packs():
            pinned = pack.find_mod(guid)
            if pinned is None:
                continue
            pinned.repo = page
            self.packs.save(pack)
        for entry in self.library.list_mods():
            if entry.guid != guid:
                continue
            meta = self.library.read_mod_meta(entry.guid, entry.version)
            if meta is None:
                continue
            meta.repo = page
            self.library.write_mod_meta(meta)
        return page

    def associate_mod(
        self,
        guid: str,
        version: str,
        *,
        catalog_entry: CatalogEntry | None = None,
        repo: str = "",
    ) -> str:
        entry = catalog_entry
        page = ""
        if entry is None and repo:
            page = canonicalize_repo_url(repo)
            entry = next((item for item in self.catalog if same_repo(item.repo, page)), None)
            if entry is None:
                return self.set_mod_repo(guid, page)
        if entry is None:
            raise ValueError("No catalog entry or repository to associate")
        page = canonicalize_repo_url(entry.repo)
        new_guid = guid if guid in entry.guids or guid == entry.primary_guid else entry.primary_guid
        if self.library.has_mod(guid, version):
            self.library.rekey_mod(guid, version, new_guid, repo=page)
        elif self.library.has_mod(new_guid, version):
            meta = self.library.read_mod_meta(new_guid, version)
            if meta is not None:
                meta.repo = page
                self.library.write_mod_meta(meta)
        else:
            self.set_mod_repo(guid, page)
        if new_guid != guid and guid in self.aliases:
            self.aliases[new_guid] = self.aliases.pop(guid)
            save_aliases(self.paths, self.aliases)
        for pack in self.packs.list_packs():
            pinned = pack.find_mod(guid)
            if pinned is None:
                continue
            if new_guid == guid:
                pinned.repo = page
                self.packs.save(pack)
                continue
            existing = pack.find_mod(new_guid)
            remaining = [mod for mod in pack.mods if mod.guid != guid]
            pinned.guid = new_guid
            pinned.repo = page
            if existing is None:
                remaining.append(pinned)
            else:
                remaining = [mod for mod in remaining if mod.guid != new_guid]
                existing.version = pinned.version
                existing.version_raw = pinned.version_raw or existing.version_raw
                existing.repo = page
                existing.enabled = pinned.enabled
                existing.plugin_folders = list(pinned.plugin_folders or existing.plugin_folders)
                remaining.append(existing)
            remaining.sort(key=lambda mod: mod.guid.lower())
            pack.mods = remaining
            self.packs.save(pack)
        return new_guid

    def missing_mods(self, pack: ModPack | None) -> list[PinnedMod]:
        if pack is None:
            return []
        return [mod for mod in pack.mods if not artifact_ready(self.library, mod.guid, mod.version)]

    def import_local_mod(
        self,
        path: Path,
        pack_id: str,
        progress: ProgressFn | None = None,
        *,
        guid: str | None = None,
    ) -> PinnedMod:
        path = Path(path)
        if progress:
            progress(f"Reading {path.name}…")
        found = discover_local_file(path, self.catalog)
        if not found:
            raise ValueError(f"No plugin DLL found in {path.name}")
        plugin = found[0]
        pack = self.packs.get(pack_id)
        use_guid = guid or plugin.guid
        use_version = plugin.version
        use_raw = plugin.version_raw or plugin.version
        previous = pack.find_mod(use_guid)
        if previous and (not use_version or use_version in ("0", "0.0.0")):
            use_version = previous.version
            use_raw = previous.version_raw or previous.version
        source = str(path)
        if path.suffix.lower() == ".dll":
            if progress:
                progress(f"Importing {use_guid} {use_version}…")
            meta = self.library.ingest_plugin_paths(
                use_guid,
                use_version,
                [path],
                version_raw=use_raw,
                repo=plugin.repo or (previous.repo if previous else ""),
                source_url=source,
            )
        elif path.suffix.lower() == ".zip":
            if progress:
                progress(f"Importing {use_guid} {use_version}…")
            meta = self.library.ingest_mod_zip(
                use_guid,
                use_version,
                path,
                version_raw=use_raw,
                repo=plugin.repo or (previous.repo if previous else ""),
                source_url=source,
                filename=path.name,
            )
        else:
            raise ValueError(f"Unsupported file type: {path.suffix}. Use a .dll or .zip.")
        if previous:
            remove_plugin_folders(self.packs.plugins_dir(pack_id), previous.plugin_folders)
        pinned = PinnedMod(
            guid=meta.guid,
            version=meta.version,
            repo=meta.repo,
            enabled=previous.enabled if previous else True,
            plugin_folders=list(meta.plugin_folders),
            version_raw=meta.version_raw,
        )
        folders = install_pinned_into_plugins(
            pinned,
            self.library.mod_extracted(meta.guid, meta.version),
            self.packs.plugins_dir(pack_id),
        )
        pinned.plugin_folders = folders
        self.packs.upsert_mod(pack_id, pinned)
        return pinned

    def update_mod(self, pack_id: str, guid: str, progress: ProgressFn | None = None) -> PinnedMod:
        pack = self.packs.get(pack_id)
        pinned = pack.find_mod(guid)
        entry = find_entry(self.catalog, guid)
        repo = (pinned.repo if pinned else "") or (entry.repo if entry else "")
        version_raw = entry.latest_raw if entry else None
        version = entry.latest_version if entry else None
        return self.install_mod(
            pack_id,
            guid,
            repo=repo,
            version=version,
            version_raw=version_raw,
            progress=progress,
        )

    def set_mod_enabled(self, pack_id: str, guid: str, enabled: bool) -> ModPack:
        pack = self.packs.get(pack_id)
        pinned = pack.find_mod(guid)
        if pinned is None:
            raise FileNotFoundError(guid)
        pinned.enabled = enabled
        self.packs.save(pack)
        plugins = self.packs.plugins_dir(pack_id)
        if enabled and self.library.has_mod(pinned.guid, pinned.version):
            install_pinned_into_plugins(
                pinned,
                self.library.mod_extracted(pinned.guid, pinned.version),
                plugins,
            )
        else:
            remove_plugin_folders(plugins, pinned.plugin_folders)
        return pack

    def prepare_pack(self, pack_id: str, progress: ProgressFn | None = None) -> Path:
        pack = self.packs.get(pack_id)
        with log_duration(log, f"prepare pack {pack_id} ({pack.name})"):
            if progress:
                progress("Preparing BepInEx…")
            bx_version, bx_extracted = ensure_bepinex(
                self.library,
                self.http,
                version=pack.bepinex or DEFAULT_BEPINEX_VERSION,
                progress=progress,
            )
            if pack.bepinex != bx_version:
                pack.bepinex = bx_version
                self.packs.save(pack)
            if progress:
                progress("Installing BepInEx into the pack…")
            instance = self.packs.instance_dir(pack_id)
            preloader = ensure_instance_bepinex(instance, bx_extracted)
            self.resolve_pack_artifacts(pack_id, progress=progress)
            return preloader

    def resolve_pack_artifacts(self, pack_id: str, progress: ProgressFn | None = None) -> None:
        pack = self.packs.get(pack_id)
        total = len(pack.mods)
        missing = 0
        log.info("Resolving %s mod(s) for pack %s (%s)", total, pack_id, pack.name)
        for index, pinned in enumerate(pack.mods, start=1):
            if progress:
                progress(f"Resolving {pinned.guid} ({index}/{total})…")
            if not pinned.repo:
                entry = find_entry(self.catalog, pinned.guid)
                if entry:
                    pinned.repo = entry.repo
                    log.info("Filled repo for %s from catalog: %s", pinned.guid, pinned.repo)
                else:
                    known = known_repo_for(pinned.guid)
                    if known:
                        pinned.repo = known
                        log.info("Filled repo for %s from known mods: %s", pinned.guid, pinned.repo)
            if artifact_ready(self.library, pinned.guid, pinned.version):
                log.info("Library hit %s %s", pinned.guid, pinned.version)
                meta = self.library.read_mod_meta(pinned.guid, pinned.version)
                if meta and not pinned.plugin_folders:
                    pinned.plugin_folders = list(meta.plugin_folders)
                continue
            if not pinned.repo:
                missing += 1
                log.warning(
                    "Leaving %s %s as missing: not in the library and no repo",
                    pinned.guid,
                    pinned.version,
                )
                if progress:
                    progress(f"Missing {pinned.guid} — import a file later")
                continue
            try:
                log.info(
                    "Fetching %s %s from %s",
                    pinned.guid,
                    pinned.version,
                    pinned.repo,
                )
                ensure_mod_artifact(
                    self.library,
                    self.http,
                    guid=pinned.guid,
                    repo=pinned.repo,
                    version=pinned.version,
                    version_raw=pinned.version_raw or pinned.version,
                    progress=progress,
                )
            except Exception as exc:
                missing += 1
                log.warning(
                    "Leaving %s %s as missing: %s",
                    pinned.guid,
                    pinned.version,
                    exc,
                )
                if progress:
                    progress(f"Missing {pinned.guid} — import a file later")
                continue
            meta = self.library.read_mod_meta(pinned.guid, pinned.version)
            if meta and not pinned.plugin_folders:
                pinned.plugin_folders = list(meta.plugin_folders)
        self.packs.save(pack)
        plugins = self.packs.plugins_dir(pack_id)
        plugins.mkdir(parents=True, exist_ok=True)
        sync_pack_plugins(pack, plugins, self.library)
        log.info("Resolved pack %s: %s missing of %s", pack_id, missing, total)

    def play(self, pack_id: str, progress: ProgressFn | None = None):
        game_dir = self.game_dir()
        if game_dir is None:
            raise FileNotFoundError("Sailwind.exe not found. Set the game path in Settings.")
        log.info("Play pack %s from %s", pack_id, game_dir)
        preloader = self.prepare_pack(pack_id, progress=progress)
        pack = self.packs.get(pack_id)
        _, bx_extracted = ensure_bepinex(
            self.library,
            self.http,
            version=pack.bepinex or DEFAULT_BEPINEX_VERSION,
            progress=progress,
        )
        search_path = coop_dll_search_path(pack, self.packs.plugins_dir(pack_id))
        if progress:
            progress("Installing Doorstop into the game folder…")
        if not doorstop_installed(game_dir):
            install_doorstop(game_dir, bx_extracted, preloader, dll_search_path=search_path)
        else:
            write_doorstop_config(game_dir, preloader, dll_search_path=search_path)
        if progress:
            progress("Launching Sailwind…")
        self.config.last_pack_id = pack_id
        self.save_config()
        log.info("Launching Sailwind with pack %s preloader %s", pack_id, preloader)
        return launch_modded(game_dir, preloader, dll_search_path=search_path)

    def play_vanilla(self):
        game_dir = self.game_dir()
        if game_dir is None:
            raise FileNotFoundError("Sailwind.exe not found. Set the game path in Settings.")
        log.info("Launching vanilla Sailwind from %s", game_dir)
        return launch_vanilla(game_dir)

    def export_pack(self, pack_id: str, dest: Path, bundle: bool = False) -> Path:
        if bundle:
            return self.packs.export_bundle(pack_id, dest, self.library)
        return self.packs.export_json(pack_id, dest)

    def import_pack(self, path: Path, progress: ProgressFn | None = None) -> ModPack:
        path = Path(path)
        with log_duration(log, f"import pack {path}"):
            if progress:
                progress("Reading pack file…")
            pack = self.packs.import_file(path, self.library)
            log.info(
                "Imported recipe %s (%s) with %s mod(s) from %s",
                pack.id,
                pack.name,
                len(pack.mods),
                path,
            )
            if progress:
                progress(f"Resolving {len(pack.mods)} mods…")
            self.resolve_pack_artifacts(pack.id, progress=progress)
            return self.packs.get(pack.id)

    def import_game_plugins(
        self,
        pack_name: str = "Current game",
        plugins_dir: Path | None = None,
        progress: ProgressFn | None = None,
    ) -> ModPack:
        game_dir = self.game_dir()
        if plugins_dir is None:
            if game_dir is None:
                raise FileNotFoundError("Sailwind.exe not found. Set the game path in Settings.")
            plugins_dir = game_dir / "BepInEx" / "plugins"
        if not plugins_dir.is_dir():
            raise FileNotFoundError(f"No plugins folder at {plugins_dir}")
        if not self.catalog:
            self.catalog = load_cached_catalog(self.paths) or []
        log_path = plugins_dir.parent / "LogOutput.log"
        if progress:
            progress(f"Scanning {plugins_dir}…")
        discovered = scan_plugins_dir(plugins_dir, catalog=self.catalog, log_path=log_path)
        if not discovered:
            raise FileNotFoundError(f"No BepInEx plugins found in {plugins_dir}")
        pack = self.packs.create(pack_name)
        for plugin in discovered:
            if progress:
                progress(f"Importing {plugin.name} ({plugin.guid} {plugin.version})…")
            if not self.library.has_mod(plugin.guid, plugin.version):
                self.library.ingest_plugin_paths(
                    plugin.guid,
                    plugin.version,
                    plugin.plugin_paths,
                    version_raw=plugin.version_raw,
                    repo=plugin.repo,
                    source_url=plugin.source,
                )
            meta = self.library.read_mod_meta(plugin.guid, plugin.version)
            folders = list(meta.plugin_folders) if meta else [path.name for path in plugin.plugin_paths]
            self.packs.upsert_mod(
                pack.id,
                PinnedMod(
                    guid=plugin.guid,
                    version=plugin.version,
                    repo=plugin.repo,
                    enabled=True,
                    plugin_folders=folders,
                    version_raw=plugin.version_raw,
                ),
            )
        self.prepare_pack(pack.id, progress=progress)
        if game_dir is not None:
            _copy_matching_configs(
                game_dir / "BepInEx" / "config",
                self.packs.instance_dir(pack.id) / "BepInEx" / "config",
                {plugin.guid for plugin in discovered},
            )
        self.config.last_pack_id = pack.id
        self.save_config()
        return self.packs.get(pack.id)

    def prune_library(self) -> int:
        pinned: set[tuple[str, str]] = set()
        for pack in self.packs.list_packs():
            for mod in pack.mods:
                pinned.add((mod.guid, mod.version))
        return self.library.prune_unused(pinned)

    def _setup_logging(self) -> None:
        setup_logging(self.paths.log_file)


def _copy_matching_configs(source: Path, dest: Path, guids: set[str]) -> None:
    if not source.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    bepinex_cfg = source / "BepInEx.cfg"
    if bepinex_cfg.exists():
        shutil.copy2(bepinex_cfg, dest / "BepInEx.cfg")
    wanted = {guid.lower() for guid in guids}
    for cfg in source.glob("*.cfg"):
        stem = cfg.stem.lower()
        if stem in wanted:
            shutil.copy2(cfg, dest / cfg.name)


def _guids_from_discovered(discovered, ref) -> list[str]:
    guids: list[str] = []
    for unit in discovered:
        guid = (getattr(unit, "guid", None) or "").strip()
        if guid and guid not in guids:
            guids.append(guid)
    real = [guid for guid in guids if not guid.lower().startswith("local.")]
    if real:
        return real
    if guids:
        return guids
    host = "github" if getattr(ref, "is_github", True) else "gitlab"
    return [f"{host}.{ref.full_path.replace('/', '.')}"]

