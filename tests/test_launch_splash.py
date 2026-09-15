from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit

from sailwind_mod_sync.game.wait_window import process_has_visible_window
from sailwind_mod_sync.ui.launch_splash import LaunchSplash
from sailwind_mod_sync.ui.progress_dialog import BusyDialog


class _FakeProcess:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode


def test_process_has_visible_window_rejects_invalid_pid() -> None:
    assert process_has_visible_window(0) is False
    assert process_has_visible_window(-1) is False


def test_launch_splash_shows_heading_and_log(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    log_path = tmp_path / "LogOutput.log"
    dialog = LaunchSplash(
        None,
        _FakeProcess(),
        heading="Starting Sailwind — Crew",
        log_paths=[log_path],
        has_window=lambda _pid: False,
    )
    try:
        assert dialog.windowTitle() == "Starting Sailwind"
        labels = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert "Starting Sailwind — Crew" in labels
        assert "Waiting for the Sailwind window" in labels
        assert dialog.findChildren(QPlainTextEdit)
        log_path.write_text("[Info   :   BepInEx] Chainloader started\n", encoding="utf-8")
        dialog._offsets[log_path] = 0
        dialog._read_logs()
        assert "Chainloader started" in dialog._log.toPlainText()
    finally:
        dialog._timer.stop()
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_launch_splash_reports_failed_exit() -> None:
    app = QApplication.instance() or QApplication([])
    proc = _FakeProcess()
    dialog = LaunchSplash(None, proc, heading="Starting Sailwind", has_window=lambda _pid: False)
    try:
        proc.returncode = 1
        dialog._tick()
        assert "exit code 1" in dialog._status.text()
        assert not dialog._timer.isActive()
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_launch_splash_closes_when_window_appears() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = LaunchSplash(
        None,
        _FakeProcess(),
        heading="Starting Sailwind",
        has_window=lambda _pid: True,
    )
    try:
        assert dialog._opened is True
        assert "Sailwind is open" in dialog._status.text()
    finally:
        dialog._timer.stop()
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_launch_splash_without_process_uses_window_probe() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = LaunchSplash(None, None, heading="Starting Sailwind", window_probe=lambda: True)
    try:
        assert dialog._opened is True
        assert "Sailwind is open" in dialog._status.text()
    finally:
        dialog._timer.stop()
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_launch_splash_without_process_polls_probe() -> None:
    app = QApplication.instance() or QApplication([])
    clock = SimpleNamespace(now=0.0)

    def now() -> float:
        return clock.now

    dialog = LaunchSplash(
        None,
        None,
        heading="Starting Sailwind",
        window_probe=lambda: False,
        clock=now,
    )
    try:
        assert dialog._opened is False
        assert "Waiting for Steam to open Sailwind" in dialog._status.text()
        clock.now = 120
        dialog._tick()
        assert "taking a long time" in dialog._status.text()
        assert dialog._timer.isActive()
    finally:
        dialog._timer.stop()
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_busy_dialog_still_exists() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = BusyDialog(None, "Working", "Preparing ModPack…")
    try:
        assert "Preparing ModPack" in dialog._label.text()
        dialog.allow_close()
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_launch_splash_timeout_message() -> None:
    app = QApplication.instance() or QApplication([])
    clock = SimpleNamespace(now=0.0)

    def now() -> float:
        return clock.now

    dialog = LaunchSplash(
        None,
        _FakeProcess(),
        heading="Starting Sailwind",
        has_window=lambda _pid: False,
        clock=now,
    )
    try:
        clock.now = 120
        dialog._tick()
        assert "taking a long time" in dialog._status.text()
        assert dialog._timer.isActive()
    finally:
        dialog._timer.stop()
        dialog.close()
        dialog.deleteLater()
    app.processEvents()
