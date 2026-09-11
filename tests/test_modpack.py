from __future__ import annotations

import json
import zipfile
from pathlib import Path

from sailwind_mod_sync.library.store import LibraryStore
from sailwind_mod_sync.models import PinnedMod
from sailwind_mod_sync.packs.modpack import PackStore
from sailwind_mod_sync.paths import AppPaths


def test_create_export_import_json(paths: AppPaths) -> None:
    store = PackStore(paths)
    pack = store.create("Dizzy Sailing")
    store.upsert_mod(
        pack.id,
        PinnedMod(
            guid="com.dizzy.sailwind.gamma",
            version="0.3.3",
            repo="https://github.com/foxyv/dizzy_sailwind_mods",
        ),
    )
    dest = paths.root / "export.json"
    store.export_json(pack.id, dest)
    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["name"] == "Dizzy Sailing"
    assert payload["mods"][0]["guid"] == "com.dizzy.sailwind.gamma"
    imported = store.import_file(dest, LibraryStore(paths))
    assert imported.id != pack.id
    assert imported.name == "Dizzy Sailing"
    assert imported.mods[0].version == "0.3.3"


def test_export_import_bundle(paths: AppPaths, tmp_path: Path) -> None:
    library = LibraryStore(paths)
    archive = tmp_path / "mod.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Dizzy.Gamma/Dizzy.Gamma.dll", b"MZ")
    library.ingest_mod_zip(
        "com.dizzy.sailwind.gamma",
        "0.3.3",
        archive,
        version_raw="v0.3.3",
        repo="https://github.com/foxyv/dizzy_sailwind_mods",
        source_url="https://example/gamma.zip",
        filename="Dizzy.Gamma-0.3.3.zip",
    )
    packs = PackStore(paths)
    pack = packs.create("Bundle Pack")
    packs.upsert_mod(
        pack.id,
        PinnedMod(guid="com.dizzy.sailwind.gamma", version="0.3.3", repo="https://github.com/foxyv/dizzy_sailwind_mods"),
    )
    dest = tmp_path / "pack.zip"
    packs.export_bundle(pack.id, dest, library)
    packs.delete(pack.id)
    library.delete_mod("com.dizzy.sailwind.gamma", "0.3.3")
    imported = packs.import_file(dest, library)
    assert imported.mods[0].guid == "com.dizzy.sailwind.gamma"
    assert library.has_mod("com.dizzy.sailwind.gamma", "0.3.3")


def test_duplicate_and_delete(paths: AppPaths) -> None:
    store = PackStore(paths)
    original = store.create("Alpha")
    copy = store.duplicate(original.id, "Alpha Two")
    assert copy.id != original.id
    assert copy.name == "Alpha Two"
    store.delete(original.id)
    ids = {pack.id for pack in store.list_packs()}
    assert original.id not in ids
    assert copy.id in ids


def test_rename_keeps_id(paths: AppPaths) -> None:
    store = PackStore(paths)
    pack = store.create("Old Name")
    pack_id = pack.id
    renamed = store.rename(pack_id, "New Name")
    assert renamed.id == pack_id
    assert renamed.name == "New Name"
    assert store.get(pack_id).name == "New Name"
