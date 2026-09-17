"""PyInstaller entry script."""

from __future__ import annotations

import certifi  # noqa: F401
import httpx  # noqa: F401
import packaging.version  # noqa: F401
from PySide6.QtCore import Qt  # noqa: F401
from PySide6.QtGui import QGuiApplication  # noqa: F401
from PySide6.QtWidgets import QApplication  # noqa: F401

from sailwind_mod_sync.app import main


if __name__ == "__main__":
    raise SystemExit(main())
