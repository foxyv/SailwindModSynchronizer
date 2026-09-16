from pathlib import Path

from PySide6.QtWidgets import QApplication

from sailwind_mod_sync.resources import icon_path, load_icon_pixmap, raster_icon_path


def test_icon_path_finds_repo_png() -> None:
    found = icon_path()
    assert found is not None
    assert found.name in {"icon.ico", "icon.png"}
    assert found.is_file()
    assert found.stat().st_size > 0
    repo_assets = Path(__file__).resolve().parents[1] / "assets"
    assert found.parent == repo_assets


def test_raster_icon_path_prefers_png() -> None:
    found = raster_icon_path()
    assert found is not None
    assert found.name == "icon.png"
    assert found.parent == Path(__file__).resolve().parents[1] / "assets"


def test_load_icon_pixmap_downscales_png() -> None:
    app = QApplication.instance() or QApplication([])
    pix = load_icon_pixmap(72, 1.0)
    assert pix is not None
    assert not pix.isNull()
    assert pix.width() == 72
    assert pix.height() == 72
    hidpi = load_icon_pixmap(72, 2.0)
    assert hidpi is not None
    assert hidpi.width() == 144
    assert hidpi.devicePixelRatio() == 2.0
    app.processEvents()
