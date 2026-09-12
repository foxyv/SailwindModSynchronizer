from __future__ import annotations

from pathlib import Path

from sailwind_mod_sync.catalog.mvc import merge_catalog
from sailwind_mod_sync.config import AppConfig
from sailwind_mod_sync.http_util import HttpClient
from sailwind_mod_sync.manager import Manager
from sailwind_mod_sync.paths import AppPaths


class _NoHttp(HttpClient):
    def __init__(self) -> None:
        self.token = ""
        self._owns_client = False
        self._client = None

    def close(self) -> None:
        return None

    def get_json(self, *args, **kwargs):
        raise AssertionError("HTTP should not be used for local plugin import")

    def download(self, *args, **kwargs):
        raise AssertionError("HTTP should not be used for local plugin import")


def test_import_game_plugins(paths: AppPaths, tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    plugins = game / "BepInEx" / "plugins" / "Dizzy.Gamma"
    plugins.mkdir(parents=True)
    (plugins / "Dizzy.Gamma.dll").write_bytes(b"MZ" + b"com.dizzy.sailwind.gamma")
    (game / "Sailwind.exe").write_bytes(b"MZ")
    (game / "BepInEx" / "LogOutput.log").write_text(
        "[Info   :   BepInEx] Loading [Dizzy Gamma 0.3.3]\n",
        encoding="utf-8",
    )
    (game / "BepInEx" / "config").mkdir(parents=True)
    (game / "BepInEx" / "config" / "com.dizzy.sailwind.gamma.cfg").write_text("gamma=1\n", encoding="utf-8")
    bx = tmp_path / "bx.zip"
    import zipfile

    with zipfile.ZipFile(bx, "w") as zf:
        zf.writestr("BepInExPack/winhttp.dll", b"dll")
        zf.writestr("BepInExPack/BepInEx/core/BepInEx.Preloader.dll", b"MZ")
        zf.writestr("BepInExPack/BepInEx/patchers/.keep", b"")

    manager = Manager(paths=paths, config=AppConfig(game_path=str(game)), http=_NoHttp())
    manager.library.ingest_bepinex_zip("5.4.2305", bx)
    pack = manager.import_game_plugins("From game", plugins_dir=game / "BepInEx" / "plugins")
    assert pack.name == "From game"
    assert len(pack.mods) == 1
    assert pack.mods[0].guid == "com.dizzy.sailwind.gamma"
    assert pack.mods[0].version == "0.3.3"
    assert (manager.packs.plugins_dir(pack.id) / "Dizzy.Gamma" / "Dizzy.Gamma.dll").exists()
    assert (manager.packs.instance_dir(pack.id) / "BepInEx" / "config" / "com.dizzy.sailwind.gamma.cfg").exists()
    manager.close()


def test_import_game_plugins_links_catalog_by_folder_name(paths: AppPaths, tmp_path: Path) -> None:
    game = tmp_path / "Sailwind"
    plugins = game / "BepInEx" / "plugins" / "Dizzy.Gamma"
    plugins.mkdir(parents=True)
    (plugins / "Dizzy.Gamma.dll").write_bytes(b"MZ" + b"\0" * 64)
    (game / "Sailwind.exe").write_bytes(b"MZ")
    (game / "BepInEx" / "LogOutput.log").write_text(
        "[Info   :   BepInEx] Loading [Dizzy Gamma 0.3.3]\n",
        encoding="utf-8",
    )
    bx = tmp_path / "bx.zip"
    import zipfile

    with zipfile.ZipFile(bx, "w") as zf:
        zf.writestr("BepInExPack/winhttp.dll", b"dll")
        zf.writestr("BepInExPack/BepInEx/core/BepInEx.Preloader.dll", b"MZ")
        zf.writestr("BepInExPack/BepInEx/patchers/.keep", b"")

    manager = Manager(paths=paths, config=AppConfig(game_path=str(game)), http=_NoHttp())
    manager.catalog = merge_catalog(
        [{"guid": "com.dizzy.sailwind.gamma", "repo": "https://github.com/foxyv/dizzy_sailwind_mods"}],
        [{"guid": "com.dizzy.sailwind.gamma", "repo": "https://github.com/foxyv/dizzy_sailwind_mods", "version": "v0.3.3"}],
    )
    manager.library.ingest_bepinex_zip("5.4.2305", bx)
    pack = manager.import_game_plugins("From game", plugins_dir=game / "BepInEx" / "plugins")
    assert pack.mods[0].guid == "com.dizzy.sailwind.gamma"
    assert pack.mods[0].repo.endswith("dizzy_sailwind_mods")
    assert manager.library.has_mod("com.dizzy.sailwind.gamma", "0.3.3")
    manager.close()
