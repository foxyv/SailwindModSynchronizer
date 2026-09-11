from pathlib import Path

from sailwind_mod_sync.resources import icon_path


def test_icon_path_finds_repo_png() -> None:
    found = icon_path()
    assert found is not None
    assert found.name in {"icon.ico", "icon.png"}
    assert found.is_file()
    assert found.stat().st_size > 0
    repo_assets = Path(__file__).resolve().parents[1] / "assets"
    assert found.parent == repo_assets
