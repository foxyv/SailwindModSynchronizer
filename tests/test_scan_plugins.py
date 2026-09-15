from __future__ import annotations

import zipfile
from pathlib import Path

from sailwind_mod_sync.catalog.mvc import merge_catalog
from sailwind_mod_sync.game.scan_plugins import (
    apply_catalog_identity,
    discover_local_file,
    parse_load_versions,
    rank_catalog_matches,
    scan_plugins_dir,
)
from sailwind_mod_sync.library.main_dll import pick_main_dll


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


# --- pick_main_dll tests (main-DLL selection algorithm) ---


def test_pick_main_dll_single_dll(tmp_path: Path) -> None:
    dll = tmp_path / "SoloMod.dll"
    dll.write_bytes(b"MZ")
    assert pick_main_dll([dll]) == dll


def test_pick_main_dll_empty() -> None:
    assert pick_main_dll([]) is None


def test_pick_main_dll_all_dependencies(tmp_path: Path) -> None:
    system = tmp_path / "System.Net.Http.dll"
    unity = tmp_path / "UnityEngine.CoreModule.dll"
    system.write_bytes(b"MZ")
    unity.write_bytes(b"MZ")
    picked = pick_main_dll([unity, system])
    assert picked == system  # name-sorted: system < unity


def test_pick_main_dll_filters_dependency(tmp_path: Path) -> None:
    dep = tmp_path / "Newtonsoft.Json.dll"
    main = tmp_path / "SailwindModdingHelper.dll"
    dep.write_bytes(b"MZ")
    main.write_bytes(b"MZ")
    picked = pick_main_dll([dep, main], hints=("SailwindModdingHelper",))
    assert picked == main


def test_pick_main_dll_bepinex_check(tmp_path: Path) -> None:
    plain = tmp_path / "Utils.dll"
    mod = tmp_path / "SomeVehicleMod.dll"
    plain.write_bytes(b"MZ plain bytes")
    mod.write_bytes(b"MZ BepInEx reference")
    picked = pick_main_dll([plain, mod])
    assert picked == mod


def test_pick_main_dll_bepinex_both_uses_tokens(tmp_path: Path) -> None:
    first = tmp_path / "DeckCleaner.dll"
    second = tmp_path / "DeckHardpointApi.dll"
    first.write_bytes(b"MZ BepInEx")
    second.write_bytes(b"MZ BepInEx")
    picked = pick_main_dll([first, second], hints=("DeckCleaner",))
    assert picked == first


def test_pick_main_dll_token_match_no_bepinex(tmp_path: Path) -> None:
    helper = tmp_path / "SailwindModdingHelper.dll"
    utils = tmp_path / "RandomUtils.dll"
    helper.write_bytes(b"MZ")
    utils.write_bytes(b"MZ")
    picked = pick_main_dll([utils, helper], hints=("AppSailwindMods/SailwindModdingHelper",))
    assert picked == helper


def test_pick_main_dll_deterministic_fallback(tmp_path: Path) -> None:
    alpha = tmp_path / "AlphaPatch.dll"
    beta = tmp_path / "BetaTools.dll"
    alpha.write_bytes(b"MZ")
    beta.write_bytes(b"MZ")
    first = pick_main_dll([beta, alpha])
    second = pick_main_dll([alpha, beta])
    assert first == second == alpha  # name-sorted, order-independent


def test_pick_main_dll_no_hints_uses_bepinex(tmp_path: Path) -> None:
    # Generic "plugins" folder, two non-dependency DLLs, only one is a mod.
    mod = tmp_path / "CompassFix.dll"
    lib = tmp_path / "CommonShipyard.dll"
    mod.write_bytes(b"MZ BepInEx")
    lib.write_bytes(b"MZ")
    picked = pick_main_dll([lib, mod])
    assert picked == mod


def test_sailwindmoddinghelper_regression(tmp_path: Path) -> None:
    """Real archive layout of AppSailwindMods/SailwindModdingHelper 2.1.1.

    plugins/Newtonsoft.Json.dll + plugins/SailwindModdingHelper.dll. Before the
    main-DLL fix, the loose junk GUID from Newtonsoft won; now the author GUID
    com.app24.sailwindmoddinghelper must win.
    """
    zip_path = tmp_path / "SailwindModdingHelper_2.1.1.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "plugins/Newtonsoft.Json.dll",
            b"MZ BepInEx Newtonsoft.Json.Schema v1.0.0",
        )
        zf.writestr(
            "plugins/SailwindModdingHelper.dll",
            b"MZ BepInEx com.app24.sailwindmoddinghelper",
        )
    found = discover_local_file(
        zip_path,
        hints=("https://github.com/AppSailwindMods/SailwindModdingHelper",
               "SailwindModdingHelper_2.1.1.zip"),
    )
    assert len(found) == 1
    assert found[0].guid == "com.app24.sailwindmoddinghelper"
    assert found[0].guid != "bNewtonsoft.Json.Schema"


def test_author_guid_wins_over_dll_collapsed_name(tmp_path: Path) -> None:
    """Assembly-name strings ("SeaLifeMod.dll") must not beat a real com.* GUID.

    Loose scanning of the binary can yield "SeaLifeMod.dll" (the assembly
    name string), which matches the mod name perfectly (+90). The real
    com.* GUID must still win.
    """
    zip_path = tmp_path / "SeaLifeMod_v0.0.1.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "plugins/SeaLifeMod.dll",
            b"MZ BepInEx com.yourname.sailwind.sealifeplugin SeaLifeMod.dll",
        )
    found = discover_local_file(zip_path)
    assert len(found) == 1
    assert found[0].guid == "com.yourname.sailwind.sealifeplugin"
    assert found[0].guid != "SeaLifeMod.dll"


def test_from_unit_order_independent(tmp_path: Path) -> None:
    """Same GUID whether the dependency DLL comes first or last in rglob order."""
    plugins = tmp_path / "plugins"
    folder = plugins / "plugins"
    folder.mkdir(parents=True)
    (folder / "Newtonsoft.Json.dll").write_bytes(
        b"MZ\0" + b"Newtonsoft.Json.Schema v"
    )
    (folder / "SailwindModdingHelper.dll").write_bytes(
        b"MZ\0" + b"com.app24.sailwindmoddinghelper"
    )
    found = scan_plugins_dir(plugins)
    assert len(found) == 1
    assert found[0].guid == "com.app24.sailwindmoddinghelper"
