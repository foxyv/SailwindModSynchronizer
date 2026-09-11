from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.constants import APP_NAME, APP_VERSION
from sailwind_mod_sync.updater import AppUpdate

UPDATE = 1
SKIP = 2
LATER = 0
OPEN = 3


class UpdateDialog(QDialog):
    def __init__(self, update: AppUpdate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._choice = LATER
        self.setWindowTitle("Update available")
        self.resize(520, 360)

        summary = QLabel(
            f"{APP_NAME} {update.version_raw} is available.\nYou have {APP_VERSION}."
        )
        summary.setWordWrap(True)

        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        body = update.notes.strip() or "No release notes."
        notes.setPlainText(body)

        buttons = QDialogButtonBox()
        later = buttons.addButton("Later", QDialogButtonBox.ButtonRole.RejectRole)
        skip = buttons.addButton("Skip this version", QDialogButtonBox.ButtonRole.DestructiveRole)
        if update.installable:
            install = buttons.addButton("Update", QDialogButtonBox.ButtonRole.AcceptRole)
            install.setDefault(True)
            install.clicked.connect(self._choose_update)
        else:
            open_page = buttons.addButton("Open GitHub", QDialogButtonBox.ButtonRole.AcceptRole)
            open_page.setDefault(True)
            open_page.clicked.connect(self._choose_open)
        later.clicked.connect(self._choose_later)
        skip.clicked.connect(self._choose_skip)

        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        notes_label = QLabel("Release notes")
        notes_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(notes_label)
        layout.addWidget(notes, 1)
        if not update.installable:
            hint = QLabel(
                "Automatic install is available for the desktop app. "
                "This copy can open the GitHub release instead."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color: palette(mid);")
            layout.addWidget(hint)
        layout.addWidget(buttons)

    def choice(self) -> int:
        return self._choice

    def _choose_update(self) -> None:
        self._choice = UPDATE
        self.accept()

    def _choose_open(self) -> None:
        self._choice = OPEN
        self.accept()

    def _choose_skip(self) -> None:
        self._choice = SKIP
        self.accept()

    def _choose_later(self) -> None:
        self._choice = LATER
        self.reject()
