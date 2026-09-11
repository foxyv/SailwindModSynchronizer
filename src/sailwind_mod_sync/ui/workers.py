from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from sailwind_mod_sync.http_util import ProgressFn

log = logging.getLogger(__name__)


class TaskBridge(QObject):
    """Lives on the GUI thread. Background threads only emit these signals."""

    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)


def run_background(fn: Callable[[ProgressFn], object], bridge: TaskBridge) -> threading.Thread:
    def body() -> None:
        log.info("Background task started")
        try:
            result = fn(_progress(bridge))
        except Exception as exc:
            log.exception("Background task failed")
            detail = str(exc).strip() or repr(exc)
            bridge.failed.emit(f"{type(exc).__name__}: {detail}")
            return
        log.info("Background task finished")
        bridge.finished.emit(result)

    thread = threading.Thread(target=body, name="sailwind-mod-sync-task", daemon=True)
    thread.start()
    return thread


def _progress(bridge: TaskBridge) -> ProgressFn:
    def emit(message: str) -> None:
        text = str(message)
        log.info("%s", text)
        bridge.progress.emit(text)

    return emit
