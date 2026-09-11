from __future__ import annotations

import zipfile
from pathlib import Path

from sailwind_mod_sync.library.store import LibraryStore
from sailwind_mod_sync.paths import AppPaths


def test_ingest_and_list_mod(paths: AppPaths, tmp_path: Path) -> None:
    archive = tmp_path / "mod.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Dizzy.Gamma/Dizzy.Gamma.dll", b"MZ" + b"\0" * 32)
    store = LibraryStore(paths)
    meta = store.ingest_mod_zip(
        "com.dizzy.sailwind.gamma",
        "0.3.3",
        archive,
        version_raw="v0.3.3",
        repo="https://github.com/foxyv/dizzy_sailwind_mods",
        source_url="https://example/gamma.zip",
        filename="Dizzy.Gamma-0.3.3.zip",
    )
    assert meta.plugin_folders == ["Dizzy.Gamma"]
    assert store.has_mod("com.dizzy.sailwind.gamma", "0.3.3")
    entries = store.list_mods()
    assert len(entries) == 1
    assert entries[0].guid == "com.dizzy.sailwind.gamma"
    store.delete_mod("com.dizzy.sailwind.gamma", "0.3.3")
    assert store.list_mods() == []


def test_has_mod_accepts_extracted_dll_without_zip(paths: AppPaths) -> None:
    store = LibraryStore(paths)
    extracted = store.mod_extracted("com.example.local", "1.0.0")
    folder = extracted / "LocalMod"
    folder.mkdir(parents=True)
    (folder / "LocalMod.dll").write_bytes(b"MZ")
    assert store.has_mod("com.example.local", "1.0.0")


def test_prune_keeps_pinned(paths: AppPaths, tmp_path: Path) -> None:
    store = LibraryStore(paths)
    for version in ("1.0.0", "1.1.0"):
        archive = tmp_path / f"{version}.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("Mod/Mod.dll", b"MZ")
        store.ingest_mod_zip(
            "com.example.mod",
            version,
            archive,
            version_raw=version,
            repo="https://github.com/example/mod",
            source_url="https://example/mod.zip",
        )
    removed = store.prune_unused({("com.example.mod", "1.1.0")})
    assert removed == 1
    assert store.has_mod("com.example.mod", "1.1.0")
    assert not store.has_mod("com.example.mod", "1.0.0")
