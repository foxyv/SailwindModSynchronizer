from __future__ import annotations

from pathlib import Path

import pytest

from sailwind_mod_sync.paths import AppPaths


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    root.mkdir()
    return root


@pytest.fixture
def paths(data_root: Path) -> AppPaths:
    app_paths = AppPaths(data_root)
    app_paths.ensure()
    return app_paths
