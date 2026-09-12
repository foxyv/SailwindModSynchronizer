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


def test_default_build_is_incremental() -> None:
    build = _load_build()
    args = build.parse_args([])
    assert args.release is False
    freeze = build.pyinstaller_args(windowed=True, clean=False)
    assert "--clean" not in freeze
    assert "--noupx" in freeze
    assert "--noconfirm" in freeze


def test_release_build_cleans_cache() -> None:
    build = _load_build()
    args = build.parse_args(["--release", "--skip-shortcut"])
    assert args.release is True
    freeze = build.pyinstaller_args(windowed=True, clean=True)
    assert "--clean" in freeze
    assert "--noupx" in freeze
    assert freeze.count("--clean") == 1
