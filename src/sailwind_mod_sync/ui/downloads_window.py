from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from sailwind_mod_sync.ui.library_view import LibraryView


class DownloadsWindow(QMainWindow):
    """Separate window for cached mod downloads (the former Library tab)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Download Management")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.resize(1100, 640)
        self.view = LibraryView()

        hint = QLabel(
            "Cached mod downloads. Add mods from the Catalog to a pack and they download "
            "here automatically. You can also import a .dll or .zip, prune unused files, "
            "or add a downloaded version to the selected pack."
        )
        hint.setWordWrap(True)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(hint)
        layout.addWidget(self.view, 1)
        self.setCentralWidget(central)
        self._allow_close = False

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()
