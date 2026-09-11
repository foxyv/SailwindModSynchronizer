from __future__ import annotations

import zipfile
from pathlib import Path

from unittest.mock import MagicMock, patch

from sailwind_mod_sync.config import AppConfig
from sailwind_mod_sync.http_util import HttpClient
from sailwind_mod_sync.library.special_mods import COOP_GUID
from sailwind_mod_sync.manager import Manager
from sailwind_mod_sync.models import PinnedMod
from sailwind_mod_sync.paths import AppPaths


class _NoHttp(HttpClient):
    def __init__(self) -> None:
        self.token = ""
        self._owns_client = False
        self._client = None

    def close(self) -> None:
        return None

    def get_json(self, *args, **kwargs):
        raise AssertionError("HTTP should not be used when artifacts are cached")

    def download(self, *args, **kwargs):
        raise AssertionError("HTTP should not be used when artifacts are cached")


def _zip_with(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def test_prepare_pack_from_library(paths: AppPaths, tmp_path: Path) -> None:
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    bepinex_zip = _zip_with(
        tmp_path / "bx.zip",
        {
            "BepInExPack/winhttp.dll": b"dll",
            "BepInExPack/BepInEx/core/BepInEx.Preloader.dll": b"MZ",
            "BepInExPack/BepInEx/patchers/.keep": b"",
        },
    )
    manager.library.ingest_bepinex_zip("5.4.2305", bepinex_zip)
    mod_zip = _zip_with(tmp_path / "gamma.zip", {"Dizzy.Gamma/Dizzy.Gamma.dll": b"MZ"})
    manager.library.ingest_mod_zip(
        "com.dizzy.sailwind.gamma",
        "0.3.3",
        mod_zip,
        version_raw="v0.3.3",
        repo="https://github.com/foxyv/dizzy_sailwind_mods",
        source_url="https://example/gamma.zip",
    )
    pack = manager.packs.list_packs()[0]
    pack.bepinex = "5.4.2305"
    manager.packs.save(pack)
    manager.packs.upsert_mod(
        pack.id,
        PinnedMod(
            guid="com.dizzy.sailwind.gamma",
            version="0.3.3",
            repo="https://github.com/foxyv/dizzy_sailwind_mods",
            plugin_folders=["Dizzy.Gamma"],
        ),
    )
    preloader = manager.prepare_pack(pack.id)
    assert preloader.exists()
    assert (manager.packs.plugins_dir(pack.id) / "Dizzy.Gamma" / "Dizzy.Gamma.dll").exists()
    manager.close()


def _ingest_bepinex(manager: Manager, tmp_path: Path) -> None:
    bepinex_zip = _zip_with(
        tmp_path / "bx.zip",
        {
            "BepInExPack/winhttp.dll": b"dll",
            "BepInExPack/BepInEx/core/BepInEx.Preloader.dll": b"MZ",
            "BepInExPack/BepInEx/patchers/.keep": b"",
        },
    )
    manager.library.ingest_bepinex_zip("5.4.2305", bepinex_zip)


def test_prepare_pack_leaves_unknown_mod_missing(paths: AppPaths, tmp_path: Path) -> None:
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    _ingest_bepinex(manager, tmp_path)
    pack = manager.packs.list_packs()[0]
    pack.bepinex = "5.4.2305"
    manager.packs.save(pack)
    manager.packs.upsert_mod(
        pack.id,
        PinnedMod(guid="local.discord.mystery", version="1.0.0", repo=""),
    )
    preloader = manager.prepare_pack(pack.id)
    assert preloader.exists()
    refreshed = manager.packs.get(pack.id)
    missing = manager.missing_mods(refreshed)
    assert [mod.guid for mod in missing] == ["local.discord.mystery"]
    manager.close()


def test_prepare_pack_leaves_unfetchable_repo_missing(paths: AppPaths, tmp_path: Path) -> None:
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    _ingest_bepinex(manager, tmp_path)
    pack = manager.packs.list_packs()[0]
    pack.bepinex = "5.4.2305"
    manager.packs.save(pack)
    manager.packs.upsert_mod(
        pack.id,
        PinnedMod(
            guid="com.example.offline",
            version="1.0.0",
            repo="https://github.com/example/offline-mod",
        ),
    )
    preloader = manager.prepare_pack(pack.id)
    assert preloader.exists()
    assert [mod.guid for mod in manager.missing_mods(manager.packs.get(pack.id))] == [
        "com.example.offline"
    ]
    manager.close()


def test_import_pack_does_not_abort_on_missing_mod(paths: AppPaths, tmp_path: Path) -> None:
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    _ingest_bepinex(manager, tmp_path)
    source = manager.packs.create("Shared Pack")
    manager.packs.upsert_mod(
        source.id,
        PinnedMod(guid="local.discord.mystery", version="2.0.0", repo=""),
    )
    dest = tmp_path / "shared.json"
    manager.export_pack(source.id, dest, bundle=False)
    manager.packs.delete(source.id)
    imported = manager.import_pack(dest)
    assert imported.name == "Shared Pack"
    assert imported.mods[0].guid == "local.discord.mystery"
    assert manager.missing_mods(imported)[0].guid == "local.discord.mystery"
    manager.close()


def test_import_pack_json_does_not_need_bepinex(paths: AppPaths, tmp_path: Path) -> None:
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    source = manager.packs.create("Recipe Only")
    manager.packs.upsert_mod(
        source.id,
        PinnedMod(guid="Fake.Mod", version="1.1.6", repo=""),
    )
    dest = tmp_path / "importtest.json"
    manager.export_pack(source.id, dest, bundle=False)
    manager.packs.delete(source.id)
    imported = manager.import_pack(dest)
    assert imported.name == "Recipe Only"
    assert [mod.guid for mod in manager.missing_mods(imported)] == ["Fake.Mod"]
    manager.close()


def test_add_library_mod_to_pack(paths: AppPaths, tmp_path: Path) -> None:
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    mod_zip = _zip_with(tmp_path / "gamma.zip", {"Dizzy.Gamma/Dizzy.Gamma.dll": b"MZ"})
    manager.library.ingest_mod_zip(
        "com.dizzy.sailwind.gamma",
        "0.3.3",
        mod_zip,
        version_raw="v0.3.3",
        repo="https://github.com/foxyv/dizzy_sailwind_mods",
        source_url="https://example/gamma.zip",
    )
    pack = manager.packs.create("From Library")
    pinned = manager.add_library_mod_to_pack(pack.id, "com.dizzy.sailwind.gamma", "0.3.3")
    assert pinned.guid == "com.dizzy.sailwind.gamma"
    assert pinned.version == "0.3.3"
    refreshed = manager.packs.get(pack.id)
    assert refreshed.find_mod(pinned.guid).version == "0.3.3"
    assert (manager.packs.plugins_dir(pack.id) / "Dizzy.Gamma" / "Dizzy.Gamma.dll").exists()
    manager.close()


def test_add_library_mod_replaces_other_version(paths: AppPaths, tmp_path: Path) -> None:
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    for version in ("0.3.3", "0.4.0"):
        archive = _zip_with(tmp_path / f"gamma-{version}.zip", {"Dizzy.Gamma/Dizzy.Gamma.dll": version.encode()})
        manager.library.ingest_mod_zip(
            "com.dizzy.sailwind.gamma",
            version,
            archive,
            version_raw=f"v{version}",
            repo="https://github.com/foxyv/dizzy_sailwind_mods",
            source_url=f"https://example/gamma-{version}.zip",
        )
    pack = manager.packs.create("Swap")
    manager.add_library_mod_to_pack(pack.id, "com.dizzy.sailwind.gamma", "0.3.3")
    pinned = manager.add_library_mod_to_pack(pack.id, "com.dizzy.sailwind.gamma", "0.4.0")
    assert pinned.version == "0.4.0"
    refreshed = manager.packs.get(pack.id)
    assert [mod.version for mod in refreshed.mods if mod.guid == pinned.guid] == ["0.4.0"]
    plugin = manager.packs.plugins_dir(pack.id) / "Dizzy.Gamma" / "Dizzy.Gamma.dll"
    assert plugin.read_bytes() == b"0.4.0"
    manager.close()


def test_set_mod_repo_updates_pack_and_library(paths: AppPaths, tmp_path: Path) -> None:
    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    archive = _zip_with(tmp_path / "mod.zip", {"Mod/Mod.dll": b"MZ"})
    manager.library.ingest_mod_zip(
        "local.discord.mystery",
        "1.0.0",
        archive,
        version_raw="1.0.0",
        repo="",
        source_url="discord",
    )
    pack = manager.packs.create("Repo Pack")
    manager.packs.upsert_mod(
        pack.id,
        PinnedMod(guid="local.discord.mystery", version="1.0.0", repo=""),
    )
    page = manager.set_mod_repo(
        "local.discord.mystery",
        "https://github.com/example/mystery/releases/tag/v1.0.0",
    )
    assert page == "https://github.com/example/mystery"
    assert manager.packs.get(pack.id).find_mod("local.discord.mystery").repo == page
    meta = manager.library.read_mod_meta("local.discord.mystery", "1.0.0")
    assert meta is not None
    assert meta.repo == page
    manager.close()


def test_play_coop_pack_sets_dll_search_path(paths: AppPaths, tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    (game / "Sailwind.exe").write_bytes(b"MZ")
    manager = Manager(paths=paths, config=AppConfig(game_path=str(game)), http=_NoHttp())
    _ingest_bepinex(manager, tmp_path)
    overlay = _zip_with(
        tmp_path / "coop.zip",
        {
            "steam_api64.dll": b"steam-api",
            "winhttp.dll": b"doorstop",
            "BepInEx/plugins/SailwindCoop/SailwindCoop.dll": b"MZ",
            "BepInEx/plugins/SailwindCoop/Facepunch.Steamworks.Win64.dll": b"MZ",
        },
    )
    manager.library.ingest_mod_zip(
        COOP_GUID,
        "0.3.2",
        overlay,
        version_raw="v0.3.2",
        repo="https://github.com/DiamondMiner99/sailwind-coop",
        source_url="https://example/coop.zip",
    )
    pack = manager.packs.list_packs()[0]
    pack.bepinex = "5.4.2305"
    manager.packs.save(pack)
    manager.packs.upsert_mod(
        pack.id,
        PinnedMod(
            guid=COOP_GUID,
            version="0.3.2",
            repo="https://github.com/DiamondMiner99/sailwind-coop",
            plugin_folders=["SailwindCoop"],
        ),
    )
    with patch("sailwind_mod_sync.manager.launch_modded") as launch:
        launch.return_value = MagicMock()
        manager.play(pack.id)
    search = manager.packs.plugins_dir(pack.id) / "SailwindCoop"
    assert launch.call_args.kwargs["dll_search_path"] == search
    config = (game / "doorstop_config.ini").read_text(encoding="utf-8")
    assert f"dll_search_path_override = {search}" in config
    assert (search / "steam_api64.dll").exists()
    assert not (game / "steam_api64.dll").exists()
    manager.close()


def test_play_non_coop_pack_clears_dll_search_path(paths: AppPaths, tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    game.mkdir()
    (game / "Sailwind.exe").write_bytes(b"MZ")
    manager = Manager(paths=paths, config=AppConfig(game_path=str(game)), http=_NoHttp())
    _ingest_bepinex(manager, tmp_path)
    mod_zip = _zip_with(tmp_path / "gamma.zip", {"Dizzy.Gamma/Dizzy.Gamma.dll": b"MZ"})
    manager.library.ingest_mod_zip(
        "com.dizzy.sailwind.gamma",
        "0.3.3",
        mod_zip,
        version_raw="v0.3.3",
        repo="https://github.com/foxyv/dizzy_sailwind_mods",
        source_url="https://example/gamma.zip",
    )
    pack = manager.packs.list_packs()[0]
    pack.bepinex = "5.4.2305"
    manager.packs.save(pack)
    manager.packs.upsert_mod(
        pack.id,
        PinnedMod(
            guid="com.dizzy.sailwind.gamma",
            version="0.3.3",
            repo="https://github.com/foxyv/dizzy_sailwind_mods",
            plugin_folders=["Dizzy.Gamma"],
        ),
    )
    with patch("sailwind_mod_sync.manager.launch_modded") as launch:
        launch.return_value = MagicMock()
        manager.play(pack.id)
    assert launch.call_args.kwargs["dll_search_path"] is None
    config = (game / "doorstop_config.ini").read_text(encoding="utf-8")
    assert "dll_search_path_override = \n" in config
    manager.close()


def test_add_catalog_repo_is_kept_after_reload(paths: AppPaths, tmp_path: Path, monkeypatch) -> None:
    from sailwind_mod_sync.catalog.mvc import find_entry, load_cached_catalog
    from sailwind_mod_sync.models import ReleaseAsset, RemoteRelease

    archive = tmp_path / "CoolMod.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("CoolMod/CoolMod.dll", b"MZ" + b"\0" * 16 + b"com.example.coolmod\0")

    class _Http(_NoHttp):
        def download(self, url, dest, progress=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read_bytes())

    def fake_fetch(*args, **kwargs):
        return RemoteRelease(
            tag="v1.2.0",
            name="v1.2.0",
            assets=[ReleaseAsset("CoolMod.zip", "https://example/CoolMod.zip")],
        )

    monkeypatch.setattr("sailwind_mod_sync.manager.fetch_release", fake_fetch)
    manager = Manager(paths=paths, config=AppConfig(), http=_Http())
    entry = manager.add_catalog_repo("https://github.com/example/coolmod")
    assert entry.custom
    assert entry.primary_guid == "com.example.coolmod"
    assert entry.latest_version == "1.2.0"
    assert entry.repo == "https://github.com/example/coolmod"
    manager.close()

    reloaded = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    found = find_entry(reloaded.catalog, "com.example.coolmod")
    assert found is not None
    assert found.custom
    assert found.latest_raw == "v1.2.0"
    cached = load_cached_catalog(paths)
    assert cached is not None
    assert find_entry(cached, "com.example.coolmod") is not None
    reloaded.remove_catalog_repo("com.example.coolmod")
    assert find_entry(reloaded.catalog, "com.example.coolmod") is None
    reloaded.close()


def test_add_catalog_repo_rejects_mvc_duplicate(paths: AppPaths) -> None:
    from sailwind_mod_sync.models import CatalogEntry

    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    manager.catalog = [
        CatalogEntry(
            repo="https://github.com/NANDbrew/StickyFix",
            guids=["com.nandbrew.stickyfix"],
            primary_guid="com.nandbrew.stickyfix",
            name="StickyFix",
            latest_raw="v1.0.0",
            latest_version="1.0.0",
            available=True,
        )
    ]
    try:
        manager.add_catalog_repo("https://github.com/NANDbrew/StickyFix")
        raise AssertionError("expected duplicate catalog repo to fail")
    except ValueError as exc:
        assert "ModVersionChecker" in str(exc)
    manager.close()


def test_local_mod_details_lists_installed_versions(paths: AppPaths, tmp_path: Path) -> None:
    from sailwind_mod_sync.models import CatalogEntry

    manager = Manager(paths=paths, config=AppConfig(), http=_NoHttp())
    for version in ("1.0.0", "1.1.0"):
        archive = _zip_with(tmp_path / f"{version}.zip", {"Mod/Mod.dll": version.encode()})
        manager.library.ingest_mod_zip(
            "com.example.mod",
            version,
            archive,
            version_raw=f"v{version}",
            repo="https://github.com/example/mod",
            source_url=f"https://example/{version}.zip",
        )
    manager.catalog = [
        CatalogEntry(
            repo="https://github.com/example/mod",
            guids=["com.example.mod"],
            primary_guid="com.example.mod",
            name="Example Mod",
            latest_raw="v1.2.0",
            latest_version="1.2.0",
            available=True,
        )
    ]
    pack = manager.packs.create("Crew")
    manager.packs.upsert_mod(
        pack.id,
        PinnedMod(guid="com.example.mod", version="1.1.0", repo="https://github.com/example/mod"),
    )
    details = manager.local_mod_details("com.example.mod", "1.1.0")
    assert details.name == "Example Mod"
    assert details.installed_versions == ["1.1.0", "1.0.0"]
    assert details.catalog_latest == "v1.2.0"
    assert details.pack_pins == [("Crew", "1.1.0")]
    manager.close()
