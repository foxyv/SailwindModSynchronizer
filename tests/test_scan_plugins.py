from __future__ import annotations

from pathlib import Path

from sailwind_mod_sync.catalog.mvc import merge_catalog
from sailwind_mod_sync.game.scan_plugins import apply_catalog_identity, parse_load_versions, rank_catalog_matches, scan_plugins_dir


def test_parse_bepinex_load_lines(tmp_path: Path) -> None:
    log = tmp_path / "LogOutput.log"
    log.write_text(
        "[Info   :   BepInEx] Loading [Dizzy Gamma 0.3.3]\n"
        "[Info   :   BepInEx] Loading [HMS Leopard 1.5.3]\n",
        encoding="utf-8",
    )
    versions = parse_load_versions(log)
    assert versions["Dizzy Gamma"] == "0.3.3"
    assert versions["HMS Leopard"] == "1.5.3"


def test_scan_matches_guid_and_catalog(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    folder = plugins / "Dizzy.Gamma"
    folder.mkdir(parents=True)
    dll = folder / "Dizzy.Gamma.dll"
    dll.write_bytes(b"MZ" + b"\0" * 32 + b"com.dizzy.sailwind.gamma\0PluginVersion")
    log = tmp_path / "LogOutput.log"
    log.write_text("[Info   :   BepInEx] Loading [Dizzy Gamma 0.3.3]\n", encoding="utf-8")
    catalog = merge_catalog(
        [{"guid": "com.dizzy.sailwind.gamma", "repo": "https://github.com/foxyv/dizzy_sailwind_mods"}],
        [{"guid": "com.dizzy.sailwind.gamma", "repo": "https://github.com/foxyv/dizzy_sailwind_mods", "version": "v0.3.3"}],
    )
    found = scan_plugins_dir(plugins, catalog=catalog, log_path=log)
    assert len(found) == 1
    assert found[0].guid == "com.dizzy.sailwind.gamma"
    assert found[0].version == "0.3.3"
    assert found[0].repo.endswith("dizzy_sailwind_mods")


def test_picks_plugin_guid_not_dependency(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    folder = plugins / "SailwindCoop"
    folder.mkdir(parents=True)
    (folder / "SailwindCoop.dll").write_bytes(
        b"MZ"
        b"com.nandbrew.towableboats\0"
        b"com.nandbrew.nandtweaks\0"
        b"com.sailwindcoop.mod\0"
        b"com.nandbrew.shipyardexpansion\0"
    )
    log = tmp_path / "LogOutput.log"
    log.write_text("[Info   :   BepInEx] Loading [Sailwind Coop 0.3.2]\n", encoding="utf-8")
    found = scan_plugins_dir(plugins, log_path=log)
    assert found[0].guid == "com.sailwindcoop.mod"
    assert found[0].version == "0.3.2"


def test_shroud_small_uses_its_own_version(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    folder = plugins / "Shattered Seas Small"
    folder.mkdir(parents=True)
    (folder / "ShroudSmallPatcher.dll").write_bytes(b"MZ com.TheOriginOfAllEvil.riverSloop")
    log = tmp_path / "LogOutput.log"
    log.write_text(
        "[Info   :   BepInEx] Loading [Shattered Seas Shroud Small 1.2.1]\n"
        "[Info   :   BepInEx] Loading [Shattered Seas 0.1.3]\n",
        encoding="utf-8",
    )
    found = scan_plugins_dir(plugins, log_path=log)
    assert found[0].guid == "com.TheOriginOfAllEvil.riverSloop"
    assert found[0].version == "1.2.1"


def _gamma_catalog():
    return merge_catalog(
        [{"guid": "com.dizzy.sailwind.gamma", "repo": "https://github.com/foxyv/dizzy_sailwind_mods"}],
        [{"guid": "com.dizzy.sailwind.gamma", "repo": "https://github.com/foxyv/dizzy_sailwind_mods", "version": "v0.3.3"}],
    )


def test_rank_catalog_matches_folder_name() -> None:
    catalog = _gamma_catalog()
    ranked = rank_catalog_matches("Dizzy.Gamma", "local.dizzygamma", catalog)
    assert ranked
    assert ranked[0][1].primary_guid == "com.dizzy.sailwind.gamma"
    guid, entry = apply_catalog_identity("Dizzy.Gamma", "local.dizzygamma", catalog)
    assert guid == "com.dizzy.sailwind.gamma"
    assert entry is not None
    assert entry.repo.endswith("dizzy_sailwind_mods")


def test_apply_catalog_identity_keeps_unrelated_guid() -> None:
    catalog = _gamma_catalog()
    guid, entry = apply_catalog_identity("MysteryMod", "com.example.mystery", catalog)
    assert guid == "com.example.mystery"
    assert entry is None


def test_scan_associates_local_folder_with_catalog(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    folder = plugins / "Dizzy.Gamma"
    folder.mkdir(parents=True)
    (folder / "Dizzy.Gamma.dll").write_bytes(b"MZ" + b"\0" * 64)
    log = tmp_path / "LogOutput.log"
    log.write_text("[Info   :   BepInEx] Loading [Dizzy Gamma 0.3.3]\n", encoding="utf-8")
    found = scan_plugins_dir(plugins, catalog=_gamma_catalog(), log_path=log)
    assert found[0].guid == "com.dizzy.sailwind.gamma"
    assert found[0].repo.endswith("dizzy_sailwind_mods")
    assert found[0].version == "0.3.3"
