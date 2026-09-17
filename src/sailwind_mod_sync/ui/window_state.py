from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget

DEFAULT_SIZE = (1200, 760)
MIN_SAVED_SIZE = (400, 250)


def _settings(paths: Any) -> QSettings:
    return QSettings(str(paths.root / "geometry.ini"), QSettings.Format.IniFormat)


def screen_signature() -> str:
    """Stable fingerprint of attached display resolutions."""
    screens = QGuiApplication.screens()
    return ";".join(f"{screen.size().width()}x{screen.size().height()}" for screen in screens)


def save_window_state(
    window: QMainWindow,
    splitter: QSplitter | None = None,
    *,
    paths: Any | None = None,
    settings: QSettings | None = None,
    screen: str | None = None,
) -> None:
    storage = settings if settings is not None else _settings(paths)
    normal = window.normalGeometry()
    storage.setValue("geometry", window.saveGeometry())
    storage.setValue("window_state", window.saveState())
    storage.setValue("width", normal.width())
    storage.setValue("height", normal.height())
    storage.setValue("screen", screen if screen is not None else screen_signature())
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
    screen: str | None = None,
) -> bool:
    """Restore saved size/geometry unless the display setup changed.

    Saved width/height are reused when the attached screen resolutions match
    the last session. A resolution or monitor-layout change discards that size
    so the window is not restored larger than (or for) a different desktop.
    Geometry that no longer intersects a monitor is also discarded.
    """
    storage = settings if settings is not None else _settings(paths)
    current_screen = screen if screen is not None else screen_signature()
    screen_ok = _screen_matches(storage, current_screen)
    restored = False
    if screen_ok:
        geometry = storage.value("geometry")
        restored = geometry is not None and window.restoreGeometry(geometry)
        if restored and not _is_on_screen(window):
            restored = False
        if not restored:
            restored = _restore_saved_size(window, storage)
    state = storage.value("window_state")
    if state is not None:
        window.restoreState(state)
    if splitter is not None:
        splitter_state = storage.value("splitter")
        if splitter_state is not None:
            splitter.restoreState(splitter_state)
    if not restored:
        window.resize(*default_size)
        _center(window)
    if _wants_maximized(storage):
        window.showMaximized()
    return restored


def _screen_matches(storage: QSettings, current: str) -> bool:
    saved = storage.value("screen")
    if saved is None:
        return True
    text = str(saved).strip()
    if not text:
        return True
    return text == current


def _restore_saved_size(window: QWidget, storage: QSettings) -> bool:
    width = _as_int(storage.value("width"))
    height = _as_int(storage.value("height"))
    if width < MIN_SAVED_SIZE[0] or height < MIN_SAVED_SIZE[1]:
        return False
    window.resize(*_clamp_to_screen(width, height))
    _center(window)
    return True


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _clamp_to_screen(width: int, height: int) -> tuple[int, int]:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return width, height
    area = screen.availableGeometry()
    return max(MIN_SAVED_SIZE[0], min(width, area.width())), max(
        MIN_SAVED_SIZE[1], min(height, area.height())
    )


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
