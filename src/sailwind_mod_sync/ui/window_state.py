from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget

DEFAULT_SIZE = (1200, 760)


def _settings(paths: Any) -> QSettings:
    return QSettings(str(paths.root / "geometry.ini"), QSettings.Format.IniFormat)


def save_window_state(
    window: QMainWindow,
    splitter: QSplitter | None = None,
    *,
    paths: Any | None = None,
    settings: QSettings | None = None,
) -> None:
    storage = settings if settings is not None else _settings(paths)
    storage.setValue("geometry", window.saveGeometry())
    storage.setValue("window_state", window.saveState())
    if splitter is not None:
        storage.setValue("splitter", splitter.saveState())
    storage.setValue("maximized", window.isMaximized())
    storage.sync()


def _wants_maximized(storage: QSettings) -> bool:
    value = storage.value("maximized")
    if value is True:
        return True
    return isinstance(value, str) and value.strip().lower() == "true"


def restore_window_state(
    window: QMainWindow,
    splitter: QSplitter | None = None,
    *,
    paths: Any | None = None,
    default_size: tuple[int, int] = DEFAULT_SIZE,
    settings: QSettings | None = None,
) -> bool:
    """Restore saved geometry/splitter state, refusing anything off-screen.

    If the saved geometry no longer intersects any monitor (fewer screens,
    changed resolution, unplugged display) it is discarded and the window is
    reset to ``default_size`` and centered on the primary screen, so the window
    can never be lost.
    """
    storage = settings if settings is not None else _settings(paths)
    geometry = storage.value("geometry")
    restored = geometry is not None and window.restoreGeometry(geometry)
    state = storage.value("window_state")
    if state is not None:
        window.restoreState(state)
    if splitter is not None:
        splitter_state = storage.value("splitter")
        if splitter_state is not None:
            splitter.restoreState(splitter_state)
    if restored and not _is_on_screen(window):
        restored = False
    if not restored:
        window.resize(*default_size)
        _center(window)
    if _wants_maximized(storage):
        window.showMaximized()
    return restored


def _is_on_screen(window: QWidget) -> bool:
    screens = QGuiApplication.screens()
    if not screens:
        return False
    frame = window.frameGeometry()
    return any(_rects_intersect(frame, screen.availableGeometry()) for screen in screens)


def _rects_intersect(left, right) -> bool:
    return (
        left.left() <= right.right()
        and right.left() <= left.right()
        and left.top() <= right.bottom()
        and right.top() <= left.bottom()
    )


def _center(window: QWidget) -> None:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    area = screen.availableGeometry()
    window.move(
        area.x() + (area.width() - window.width()) // 2,
        area.y() + (area.height() - window.height()) // 2,
    )