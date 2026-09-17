from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_build():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build.py"
    spec = importlib.util.spec_from_file_location("sailwind_mod_sync_build", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_build_runs_pyinstaller() -> None:
    build = _load_build()
    args = build.parse_args([])
    assert args.release is False
    freeze = build.pyinstaller_args(windowed=True, clean=False)
    assert "--clean" not in freeze
    assert "--noupx" in freeze
    assert "--noconfirm" in freeze
    pairs = list(zip(freeze, freeze[1:]))
    assert ("--paths", str(build.REPO_ROOT / "src")) in pairs
    assert ("--hidden-import", "sailwind_mod_sync.app") in pairs
    assert ("--hidden-import", "logging.handlers") in pairs
    assert ("--exclude-module", "sailwind_mod_sync") not in pairs
    assert any(str(build.FREEZE_ENTRY) == item for item in freeze)
    assert not any("sms-src" in item for item in freeze)


def test_release_build_cleans_cache() -> None:
    build = _load_build()
    args = build.parse_args(["--release", "--skip-shortcut"])
    assert args.release is True
    freeze = build.pyinstaller_args(windowed=True, clean=True)
    assert "--clean" in freeze
    assert "--noupx" in freeze
    assert freeze.count("--clean") == 1


def test_release_implies_sign() -> None:
    build = _load_build()
    args = build.parse_args(["--release", "--skip-shortcut"])
    assert args.sign is True
    skipped = build.parse_args(["--release", "--skip-sign"])
    assert skipped.sign is False
    default = build.parse_args([])
    assert default.sign is False
    ignored_full = build.parse_args(["--full"])
    assert ignored_full.release is False
    explicit = build.parse_args(["--sign"])
    assert explicit.sign is True


def test_sign_and_skip_sign_conflict() -> None:
    build = _load_build()
    try:
        build.parse_args(["--sign", "--skip-sign"])
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("expected parse_args to reject --sign with --skip-sign")


def test_load_signing_metadata(tmp_path: Path) -> None:
    build = _load_build()
    path = tmp_path / "metadata.json"
    try:
        build.load_signing_metadata(path)
        raise AssertionError("expected missing metadata to fail")
    except SystemExit:
        pass
    path.write_text('{"Endpoint": "https://eus.codesigning.azure.net"}', encoding="utf-8")
    try:
        build.load_signing_metadata(path)
        raise AssertionError("expected incomplete metadata to fail")
    except SystemExit:
        pass
    path.write_text(
        '{"Endpoint": "https://eus.codesigning.azure.net",'
        '"CodeSigningAccountName": "acct",'
        '"CertificateProfileName": "prof"}',
        encoding="utf-8",
    )
    data = build.load_signing_metadata(path)
    assert data["CodeSigningAccountName"] == "acct"


def test_kit_version_and_signtool_discovery(tmp_path: Path, monkeypatch) -> None:
    build = _load_build()
    assert build.kit_version_tuple("10.0.26100.0") == (10, 0, 26100)
    assert build.kit_version_tuple("bin") is None
    kits = tmp_path / "Windows Kits" / "10" / "bin"
    old = kits / "10.0.20348.0" / "x64"
    old.mkdir(parents=True)
    (old / "signtool.exe").write_bytes(b"MZ")
    newest = kits / "10.0.26100.0" / "x64"
    newest.mkdir(parents=True)
    (newest / "signtool.exe").write_bytes(b"MZ")
    mid = kits / "10.0.22621.0" / "x64"
    mid.mkdir(parents=True)
    (mid / "signtool.exe").write_bytes(b"MZ")
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))
    monkeypatch.delenv("SMS_SIGNTOOL", raising=False)
    found = build.find_signtool()
    assert found == newest / "signtool.exe"


def test_binaries_to_sign(tmp_path: Path) -> None:
    build = _load_build()
    exe = tmp_path / "SailwindModSynchronizer.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "python3.dll").write_bytes(b"MZ")
    (tmp_path / "readme.txt").write_text("no", encoding="utf-8")
    nested = tmp_path / "PySide6"
    nested.mkdir()
    (nested / "Qt6Core.dll").write_bytes(b"MZ")
    names = {path.name for path in build.binaries_to_sign(tmp_path)}
    assert names == {"SailwindModSynchronizer.exe", "python3.dll", "Qt6Core.dll"}


def test_sign_files_batches(tmp_path: Path, monkeypatch) -> None:
    build = _load_build()
    calls: list[list[str]] = []

    def fake_call(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr(build.subprocess, "check_call", fake_call)
    files = [tmp_path / f"f{i}.dll" for i in range(20)]
    for path in files:
        path.write_bytes(b"MZ")
    signtool = tmp_path / "signtool.exe"
    dlib = tmp_path / "Azure.CodeSigning.Dlib.dll"
    metadata = tmp_path / "metadata.json"
    build.sign_files(signtool, dlib, metadata, files)
    assert len(calls) == 2
    assert calls[0][0] == str(signtool)
    assert "/dlib" in calls[0]
    assert str(dlib) in calls[0]
    assert str(metadata) in calls[0]
    assert str(files[0]) in calls[0]
    assert str(files[-1]) in calls[1]


def test_skip_collect_path_drops_qml_and_translations() -> None:
    build = _load_build()
    assert build.skip_collect_path("PySide6/Qt6Qml.dll") is True
    assert build.skip_collect_path("PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll") is True
    assert build.skip_collect_path("PySide6/translations/qt_en.qm") is True
    assert build.skip_collect_path("PySide6/Qt6Widgets.dll") is False
    assert build.skip_collect_path("PySide6/Qt6Core.dll") is False


def test_freeze_entry_loads_app_directly() -> None:
    text = (Path(__file__).resolve().parents[1] / "scripts" / "freeze_entry.py").read_text(encoding="utf-8")
    assert "from sailwind_mod_sync.app import main" in text
    assert "OverlayFinder" not in text
