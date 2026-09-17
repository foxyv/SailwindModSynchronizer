from __future__ import annotations

import sys

from sailwind_mod_sync.constants import APP_NAME, APP_USER_MODEL_ID, APP_VERSION
from sailwind_mod_sync.manager import Manager
from sailwind_mod_sync.resources import icon_path
from sailwind_mod_sync.ui.windows_shell import clear_jump_list


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    _set_windows_app_id()
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from sailwind_mod_sync.ui.main_window import MainWindow

    app = QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    icon_file = icon_path()
    if icon_file is not None:
        app.setWindowIcon(QIcon(str(icon_file)))
    manager = Manager()
    window = MainWindow(manager)
    if icon_file is not None:
        window.setWindowIcon(QIcon(str(icon_file)))
    clear_jump_list()
    window.show()
    try:
        return app.exec()
    finally:
        manager.close()
