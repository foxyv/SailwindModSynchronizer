from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.models import CatalogEntry, ModPack, is_newer
from sailwind_mod_sync.ui.links import repo_button
from sailwind_mod_sync.ui.tables import enable_column_resize


class CatalogView(QWidget):
    install_requested = Signal(str)
    remove_custom_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[CatalogEntry] = []
        self._pack: ModPack | None = None
        self._library_versions: dict[str, set[str]] = {}
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter catalog…")
        self._filter.textChanged.connect(self._apply_filter)

        refresh = QPushButton("Refresh catalog")
        self.refresh_clicked = refresh.clicked
        add_repo = QPushButton("Add GitHub repo")
        add_repo.setToolTip("Add a GitHub or GitLab repository that is not in ModVersionChecker")
        self.add_repo_clicked = add_repo.clicked

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "GUID", "Latest", "Status", ""])
        enable_column_resize(self.table, [180, 240, 90, 120, 320])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        top = QHBoxLayout()
        top.addWidget(self._filter)
        top.addWidget(add_repo)
        top.addWidget(refresh)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)

    def set_data(
        self,
        entries: list[CatalogEntry],
        pack: ModPack | None,
        library_versions: dict[str, set[str]] | None = None,
    ) -> None:
        self._entries = entries
        self._pack = pack
        self._library_versions = library_versions or {}
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._filter.text().strip().lower()
        rows = [
            entry
            for entry in self._entries
            if not query
            or query in entry.name.lower()
            or query in entry.primary_guid.lower()
            or query in entry.repo.lower()
            or any(query in guid.lower() for guid in entry.guids)
        ]
        self.table.setRowCount(len(rows))
        for index, entry in enumerate(rows):
            status = _catalog_status(entry, self._pack)
            self.table.setItem(index, 0, QTableWidgetItem(entry.name))
            guid_item = QTableWidgetItem(entry.guid_label)
            guid_item.setToolTip("\n".join(entry.guids))
            self.table.setItem(index, 1, guid_item)
            latest = entry.latest_raw or ("none" if not entry.available else "")
            self.table.setItem(index, 2, QTableWidgetItem(latest))
            self.table.setItem(index, 3, QTableWidgetItem(status))
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 0, 4, 0)
            actions_layout.addWidget(repo_button(entry.repo, actions))
            label, tip = catalog_library_button(entry, self._library_versions)
            button = QPushButton(label)
            button.setEnabled(entry.available)
            button.setToolTip(tip)
            guid = entry.primary_guid
            button.clicked.connect(lambda _=False, value=guid: self.install_requested.emit(value))
            actions_layout.addWidget(button)
            if entry.custom:
                remove = QPushButton("Remove")
                remove.setToolTip("Remove this repository from your catalog")
                remove.clicked.connect(
                    lambda _=False, value=guid: self.remove_custom_requested.emit(value)
                )
                actions_layout.addWidget(remove)
            self.table.setCellWidget(index, 4, actions)


def catalog_library_button(
    entry: CatalogEntry,
    library_versions: dict[str, set[str]] | None,
) -> tuple[str, str]:
    owned: list[str] = []
    for guid in entry.guids:
        owned.extend((library_versions or {}).get(guid, ()))
    if not owned:
        return (
            "Add to library",
            "Download into the library and add it to the selected pack",
        )
    if entry.latest_raw and any(is_newer(entry.latest_raw, version) for version in owned):
        return (
            "Update",
            "A newer version is available. Download it into the library and add it to the selected pack",
        )
    return (
        "In library",
        "This mod is already in the library. Click to add it to the selected pack.",
    )


def _catalog_status(entry: CatalogEntry, pack: ModPack | None) -> str:
    if not entry.available:
        return "Unavailable"
    if pack is None:
        return "Custom" if entry.custom else "Available"
    pinned = None
    for guid in entry.guids:
        pinned = pack.find_mod(guid)
        if pinned:
            break
    if pinned is None:
        return "Custom" if entry.custom else "Available"
    if entry.latest_raw and is_newer(entry.latest_raw, pinned.version):
        return "Update"
    return f"Installed {pinned.version}"
