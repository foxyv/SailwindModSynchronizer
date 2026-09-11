from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.catalog.github import canonicalize_repo_url


class RepoUrlDialog(QDialog):
    def __init__(
        self,
        guid: str,
        parent: QWidget | None = None,
        initial: str = "",
        *,
        title: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or "Find repository")
        self._normalized = ""
        self.edit = QLineEdit(initial)
        self.edit.setPlaceholderText("https://github.com/owner/repo")
        self.edit.selectAll()

        if hint is None:
            if guid:
                hint = (
                    f"Paste the GitHub or GitLab URL for {guid}. "
                    "owner/repo also works."
                )
            else:
                hint = (
                    "Paste a GitHub or GitLab repository URL. "
                    "owner/repo also works. The latest release is checked and added to the catalog."
                )
        label = QLabel(hint)
        label.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.edit)
        layout.addWidget(buttons)
        self.resize(520, 140)

    def accept(self) -> None:
        try:
            self._normalized = canonicalize_repo_url(self.edit.text())
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid URL",
                "Use a GitHub or GitLab repository URL, like https://github.com/owner/repo",
            )
            self.edit.setFocus()
            self.edit.selectAll()
            return
        super().accept()

    def repo_url(self) -> str:
        return self._normalized
