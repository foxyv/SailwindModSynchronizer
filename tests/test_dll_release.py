from __future__ import annotations

import zipfile
from pathlib import Path

from sailwind_mod_sync.http_util import HttpClient
from sailwind_mod_sync.library.download import ensure_mod_artifact
from sailwind_mod_sync.library.special_mods import (
    COOP_GUID,
    COOP_REPO,
    artifact_needs_refetch,
    artifact_ready,
    known_repo_for,
)
from sailwind_mod_sync.library.store import LibraryStore
from sailwind_mod_sync.models import ReleaseAsset, RemoteRelease
from sailwind_mod_sync.paths import AppPaths


class _FakeHttp(HttpClient):
    def __init__(self, payload: bytes) -> None:
        self.token = ""
        self._owns_client = False
        self._client = None
        self._payload = payload

    def close(self) -> None:
        return None

    def download(self, url: str, dest: Path, progress=None) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self._payload)


def test_installs_dll_only_github_release(paths: AppPaths, tmp_path: Path, monkeypatch) -> None:
    store = LibraryStore(paths)
    http = _FakeHttp(b"MZ" + b"\0" * 16)

    def fake_fetch(*args, **kwargs):
        return RemoteRelease(
            tag="v0.3.2",
            name="SaveCleaner",
            assets=[ReleaseAsset("SaveCleaner.dll", "https://example/SaveCleaner.dll")],
        )

    monkeypatch.setattr("sailwind_mod_sync.library.download.fetch_release", fake_fetch)
    meta = ensure_mod_artifact(
        store,
        http,
        guid="com.nandbrew.savecleaner",
        repo="https://github.com/NANDbrew/SaveCleaner",
        version="0.3.2",
        version_raw="v0.3.2",
    )
    assert meta.version == "0.3.2"
    assert store.has_mod("com.nandbrew.savecleaner", "0.3.2")
    extracted = store.mod_extracted("com.nandbrew.savecleaner", "0.3.2")
    assert (extracted / "SaveCleaner" / "SaveCleaner.dll").exists()


def test_known_repo_for_coop() -> None:
    assert known_repo_for("com.sailwindcoop.mod") == COOP_REPO
    assert known_repo_for("COM.SAILWINDCOOP.MOD") == COOP_REPO
    assert known_repo_for("com.dizzy.sailwind.gamma") is None


def test_refetches_incomplete_coop_artifact(paths: AppPaths, tmp_path: Path, monkeypatch) -> None:
    store = LibraryStore(paths)
    plugin_dir = tmp_path / "SailwindCoop"
    plugin_dir.mkdir()
    (plugin_dir / "SailwindCoop.dll").write_bytes(b"MZ")
    (plugin_dir / "Facepunch.Steamworks.Win64.dll").write_bytes(b"MZ")
    store.ingest_plugin_paths(
        COOP_GUID,
        "0.3.2",
        [plugin_dir],
        version_raw="0.3.2",
        repo="",
        source_url="game-plugins",
    )
    assert store.has_mod(COOP_GUID, "0.3.2")
    assert artifact_needs_refetch(store, COOP_GUID, "0.3.2")
    assert not artifact_ready(store, COOP_GUID, "0.3.2")

    overlay = tmp_path / "SailwindCoop-v0.3.2.zip"
    with zipfile.ZipFile(overlay, "w") as zf:
        zf.writestr("steam_api64.dll", b"steam-api")
        zf.writestr("winhttp.dll", b"doorstop")
        zf.writestr("BepInEx/plugins/SailwindCoop/SailwindCoop.dll", b"MZ" + b"\0" * 16)
        zf.writestr("BepInEx/plugins/SailwindCoop/Facepunch.Steamworks.Win64.dll", b"MZ")

    http = _FakeHttp(overlay.read_bytes())

    def fake_fetch(*args, **kwargs):
        return RemoteRelease(
            tag="v0.3.2",
            name="v0.3.2",
            assets=[ReleaseAsset("SailwindCoop-v0.3.2.zip", "https://example/coop.zip")],
        )

    monkeypatch.setattr("sailwind_mod_sync.library.download.fetch_release", fake_fetch)
    meta = ensure_mod_artifact(
        store,
        http,
        guid=COOP_GUID,
        repo="",
        version="0.3.2",
        version_raw="v0.3.2",
    )
    assert meta.repo == COOP_REPO
    plugin = store.mod_extracted(COOP_GUID, "0.3.2") / "SailwindCoop"
    assert (plugin / "steam_api64.dll").read_bytes() == b"steam-api"
    assert artifact_ready(store, COOP_GUID, "0.3.2")
