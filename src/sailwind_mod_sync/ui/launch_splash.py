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

from sailwind_mod_sync.game.wait_window import process_has_visible_window
from sailwind_mod_sync.resources import icon_path

POLL_MS = 250
OPENED_GRACE_MS = 400
GIVE_UP_SECONDS = 90


class LaunchSplash(QDialog):
    """Stays visible after Popen until Sailwind shows a window, exits, or the user hides it."""

    def __init__(
        self,
        parent: QWidget | None,
        process: subprocess.Popen,
        *,
        heading: str,
        log_paths: list[Path] | None = None,
        has_window: Callable[[int], bool] | None = None,
        clock: Callable[[], float] | None = None,
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
        self._clock = clock or time.monotonic
        self._started = self._clock()
        self._opened = False
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
        self._status = QLabel("Waiting for the Sailwind window…")
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
        if pid and self._has_window(pid):
            self._opened = True
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
