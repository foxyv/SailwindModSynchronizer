from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.models import LibraryEntry, ModPack
from sailwind_mod_sync.ui.links import repo_or_find_button
from sailwind_mod_sync.ui.tables import enable_column_resize


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class LibraryView(QWidget):
    add_to_pack_requested = Signal(str, str)
    find_repo_requested = Signal(str, str)
    details_requested = Signal(str, str)
    delete_requested = Signal(str, str)
    prune_requested = Signal()
    import_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["GUID", "Version", "Size", "Source", ""])
        enable_column_resize(self.table, [220, 90, 80, 220, 340])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self._entries: list[LibraryEntry] = []

        import_btn = QPushButton("Import file…")
        import_btn.setToolTip("Add a .dll or .zip you downloaded (for example from Discord)")
        import_btn.clicked.connect(self.import_clicked.emit)
        prune = QPushButton("Prune unused")
        prune.clicked.connect(self.prune_requested.emit)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(import_btn)
        top.addStretch()
        top.addWidget(prune)
        layout.addLayout(top)
        layout.addWidget(self.table)

    def set_entries(self, entries: list[LibraryEntry], pack: ModPack | None = None) -> None:
        self._entries = list(entries)
        self.table.setRowCount(len(entries))
        pack_name = pack.name if pack else ""
        for index, entry in enumerate(entries):
            self.table.setItem(index, 0, QTableWidgetItem(entry.guid))
            self.table.setItem(index, 1, QTableWidgetItem(entry.version))
            self.table.setItem(index, 2, QTableWidgetItem(format_size(entry.size_bytes)))
            self.table.setItem(index, 3, QTableWidgetItem(entry.meta.source_url or entry.meta.repo))
            guid, version = entry.guid, entry.version
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 0, 4, 0)
            actions_layout.addWidget(
                repo_or_find_button(
                    entry.meta.repo,
                    actions,
                    lambda g=guid, v=version: self.find_repo_requested.emit(g, v),
                )
            )
            add_btn = QPushButton("Add to pack")
            pinned = pack.find_mod(guid) if pack else None
            if pack is None:
                add_btn.setEnabled(False)
                add_btn.setToolTip("Select a ModPack first")
            elif pinned and pinned.version == version:
                add_btn.setEnabled(False)
                add_btn.setText("In pack")
                add_btn.setToolTip(f"Already in {pack_name}")
            else:
                if pinned:
                    add_btn.setToolTip(
                        f"Replace {pinned.version} with {version} on {pack_name}"
                    )
                else:
                    add_btn.setToolTip(f"Add this version to {pack_name}")
                add_btn.clicked.connect(
                    lambda _=False, g=guid, v=version: self.add_to_pack_requested.emit(g, v)
                )
            actions_layout.addWidget(add_btn)
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda _=False, g=guid, v=version: self.delete_requested.emit(g, v))
            actions_layout.addWidget(delete)
            self.table.setCellWidget(index, 4, actions)

    def _on_double_click(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._entries):
            return
        entry = self._entries[row]
        self.details_requested.emit(entry.guid, entry.version)
