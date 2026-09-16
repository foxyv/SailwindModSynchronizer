from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.game.wait_window import (
    focus_window,
    process_has_visible_window,
    sailwind_window_hwnd,
    sailwind_window_visible,
    window_hwnd_for_pid,
)
from sailwind_mod_sync.resources import icon_path

POLL_MS = 250
OPENED_GRACE_MS = 400
FOCUS_AFTER_CLOSE_MS = 50
GIVE_UP_SECONDS = 90


class LaunchSplash(QDialog):
    """Stays visible until Sailwind shows a window, exits, or the user hides it.

    ``process`` may be None when the game was handed off to Steam; in that case a
    desktop-wide window probe recognizes Sailwind instead of tracking a pid.
    When the game window appears, the splash closes and focuses that window so
    the manager does not steal keyboard focus back.
    """

    def __init__(
        self,
        parent: QWidget | None,
        process: subprocess.Popen | None = None,
        *,
        heading: str,
        log_paths: list[Path] | None = None,
        has_window: Callable[[int], bool] | None = None,
        window_probe: Callable[[], bool] | None = None,
        find_hwnd: Callable[[], int | None] | None = None,
        focus_hwnd: Callable[[int], bool] | None = None,
        clock: Callable[[], float] | None = None,
        focus_delay_ms: int = FOCUS_AFTER_CLOSE_MS,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Starting Sailwind")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(560, 420)
        self._process = process
        self._has_window = has_window or process_has_visible_window
        self._window_probe = window_probe or sailwind_window_visible
        self._find_hwnd = find_hwnd
        self._use_native_hwnd = find_hwnd is None and has_window is None and window_probe is None
        self._focus_hwnd = focus_hwnd or focus_window
        self._focus_delay_ms = max(0, int(focus_delay_ms))
        self._clock = clock or time.monotonic
        self._started = self._clock()
        self._opened = False
        self._game_hwnd = 0
        self._log_paths = [Path(path) for path in log_paths or []]
        self._offsets = {
            path: path.stat().st_size if path.is_file() else 0 for path in self._log_paths
        }

        icon = QLabel()
        icon.setFixedSize(72, 72)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image = icon_path()
        if image is not None:
            pix = QPixmap(str(image)).scaled(
                72,
                72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon.setPixmap(pix)

        self._heading = QLabel(heading)
        self._heading.setStyleSheet("font-size: 16px; font-weight: 600;")
        self._heading.setWordWrap(True)
        self._status = QLabel(
            "Waiting for the Sailwind window…" if process is not None
            else "Waiting for Steam to open Sailwind…"
        )
        self._status.setWordWrap(True)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(self._heading)
        titles.addWidget(self._status)

        header = QHBoxLayout()
        header.addWidget(icon)
        header.addLayout(titles, 1)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(400)
        self._log.setPlaceholderText("BepInEx log will appear here as Sailwind starts…")
        font = QFont("Cascadia Mono")
        if not font.exactMatch():
            font = QFont("Consolas")
        font.setPointSize(9)
        self._log.setFont(font)

        hide = QPushButton("Hide")
        hide.setToolTip("Hide this window. Sailwind will keep starting.")
        hide.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addWidget(self._bar)
        layout.addWidget(self._log, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(hide)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(POLL_MS)
        self._tick()

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def append_log(self, text: str) -> None:
        chunk = text.replace("\r\n", "\n").replace("\r", "\n")
        if not chunk:
            return
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.insertPlainText(chunk)
        self._log.moveCursor(QTextCursor.MoveOperation.End)

    def _tick(self) -> None:
        if self._opened:
            return
        self._read_logs()
        opened = False
        if self._process is not None:
            code = self._process.poll()
            if code is not None:
                self._timer.stop()
                self._bar.setRange(0, 1)
                self._bar.setValue(1)
                if code == 0:
                    self.set_status("Sailwind exited before a window appeared.")
                else:
                    self.set_status(f"Sailwind failed to start (exit code {code}).")
                return
            pid = int(getattr(self._process, "pid", 0) or 0)
            opened = bool(pid) and self._has_window(pid)
        else:
            opened = self._window_probe()
        if opened:
            self._opened = True
            self._game_hwnd = self._resolve_hwnd()
            self._timer.stop()
            self._bar.setRange(0, 1)
            self._bar.setValue(1)
            self.set_status("Sailwind is open.")
            QTimer.singleShot(OPENED_GRACE_MS, self.accept)
            return
        elapsed = self._clock() - self._started
        if elapsed >= GIVE_UP_SECONDS:
            self.set_status(
                "Sailwind is taking a long time. You can hide this window; the game may still open."
            )

    def done(self, result: int) -> None:
        hwnd = self._game_hwnd if self._opened else 0
        self._game_hwnd = 0
        if hwnd:
            # Closing a child dialog would otherwise activate the manager.
            self.hide()
            self.setParent(None)
        super().done(result)
        if hwnd:
            QTimer.singleShot(self._focus_delay_ms, lambda h=hwnd: self._focus_hwnd(h))

    def _resolve_hwnd(self) -> int:
        if self._find_hwnd is not None:
            try:
                return int(self._find_hwnd() or 0)
            except (TypeError, ValueError):
                return 0
        if not self._use_native_hwnd:
            return 0
        if self._process is not None:
            pid = int(getattr(self._process, "pid", 0) or 0)
            return int(window_hwnd_for_pid(pid) or 0)
        return int(sailwind_window_hwnd() or 0)

    def _read_logs(self) -> None:
        for path in self._log_paths:
            try:
                if not path.is_file():
                    continue
                size = path.stat().st_size
                offset = self._offsets.get(path, 0)
                if size < offset:
                    offset = 0
                if size == offset:
                    continue
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(offset)
                    chunk = handle.read()
                    self._offsets[path] = handle.tell()
                self.append_log(chunk)
            except OSError:
                continue
