from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ImportPluginsDialog(QDialog):
    """Name + plugins-folder chooser for "Import game plugins".

    Replaces the old two-step QInputDialog + QFileDialog flow with a single
    dialog: the folder is typed or picked with Browse, and its existence is
    validated on OK — a missing folder shows a warning and keeps the dialog
    open so the user can correct it.
    """

    def __init__(
        self,
        default_path: str = "",
        *,
        default_name: str = "Current game",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import game plugins")

        hint = QLabel(
            "Import a ModPack from the plugins that are already installed in the game. "
            "Choose the game's BepInEx/plugins folder."
        )
        hint.setWordWrap(True)

        self._name = QLineEdit(default_name)
        self._name.selectAll()

        self._path = QLineEdit(default_path)
        self._path.setPlaceholderText("game/BepInEx/plugins")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)

        path_row = QHBoxLayout()
        path_row.addWidget(self._path, 1)
        path_row.addWidget(browse)

        form = QFormLayout()
        form.addRow("ModPack name:", self._name)
        form.addRow("Plugins folder:", path_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setFixedSize(620, 180)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select plugins folder", self._path.text().strip())
        if folder:
            self._path.setText(folder)

    def _on_ok(self) -> None:
        name = self._name.text().strip()
        text = self._path.text().strip()
        if not name:
            QMessageBox.warning(self, "No name", "Enter a name for the new ModPack.")
            self._name.setFocus()
            self._name.selectAll()
            return
        if not text:
            QMessageBox.warning(self, "No folder selected", "Choose the BepInEx/plugins folder to import.")
            self._path.setFocus()
            return
        folder = Path(text)
        if not folder.is_dir():
            QMessageBox.warning(
                self,
                "Folder not found",
                f"The plugins folder does not exist:\n{folder}\n\n"
                "Choose an existing BepInEx/plugins folder.",
            )
            self._path.setFocus()
            self._path.selectAll()
            return
        super().accept()

    def pack_name(self) -> str:
        return self._name.text().strip()

    def plugins_dir(self) -> Path:
        return Path(self._path.text().strip())