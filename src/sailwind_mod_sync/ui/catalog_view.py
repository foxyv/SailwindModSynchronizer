from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.catalog.custom import same_repo
from sailwind_mod_sync.models import CatalogEntry, ModPack, PinnedMod, is_newer
from sailwind_mod_sync.ui.links import repo_button
from sailwind_mod_sync.ui.tables import (
    enable_column_resize,
    enable_column_sort,
    sortable_item,
    sorting_paused,
    version_sort_key,
)


class CatalogView(QWidget):
    install_requested = Signal(str)
    remove_custom_requested = Signal(str)
    details_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[CatalogEntry] = []
        self._pack: ModPack | None = None
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter catalog…")
        self._filter.textChanged.connect(self._apply_filter)
        self.hide_in_pack = QCheckBox("Hide mods in pack")
        self.hide_in_pack.setToolTip("Hide catalog rows that are already pinned on the selected pack")
        self.hide_in_pack.toggled.connect(self._apply_filter)

        refresh = QPushButton("Refresh catalog")
        self.refresh_clicked = refresh.clicked
        add_repo = QPushButton("Add GitHub repo")
        add_repo.setToolTip("Add a GitHub or GitLab repository that is not in ModVersionChecker")
        self.add_repo_clicked = add_repo.clicked

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "GUID", "Latest", "Status", ""])
        enable_column_resize(self.table, [180, 240, 90, 120, 320])
        enable_column_sort(self.table, default_column=0)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setToolTip("Double-click a mod for details")
        self.table.cellDoubleClicked.connect(self._on_double_click)

        top = QHBoxLayout()
        top.addWidget(self._filter, 1)
        top.addWidget(self.hide_in_pack)
        top.addWidget(add_repo)
        top.addWidget(refresh)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)

    def set_data(self, entries: list[CatalogEntry], pack: ModPack | None) -> None:
        self._entries = entries
        self._pack = pack
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._filter.text().strip().lower()
        hide_in_pack = self.hide_in_pack.isChecked()
        rows = [
            entry
            for entry in self._entries
            if _entry_matches_filter(entry, query)
            and not (hide_in_pack and _pinned_for_entry(entry, self._pack) is not None)
        ]
        in_pack_bg = _in_pack_row_background(self.table)
        with sorting_paused(self.table):
            self.table.setRowCount(len(rows))
            for index, entry in enumerate(rows):
                status = _catalog_status(entry, self._pack)
                self.table.setItem(index, 0, sortable_item(entry.name))
                guid_item = sortable_item(entry.guid_label, entry.primary_guid.casefold())
                guid_item.setToolTip("\n".join(entry.guids))
                self.table.setItem(index, 1, guid_item)
                latest = entry.latest_raw or ("none" if not entry.available else "")
                latest_key = (0 if entry.available else 1, version_sort_key(entry.latest_raw))
                self.table.setItem(index, 2, sortable_item(latest, latest_key))
                self.table.setItem(index, 3, sortable_item(status))
                self.table.setItem(index, 4, sortable_item(""))
                actions = QWidget()
                actions_layout = QHBoxLayout(actions)
                actions_layout.setContentsMargins(4, 0, 4, 0)
                actions_layout.addWidget(repo_button(entry.repo, actions))
                label, tip = catalog_pack_button(entry, self._pack)
                button = QPushButton(label)
                button.setEnabled(entry.available and self._pack is not None)
                if self._pack is None:
                    button.setToolTip("Select a ModPack first")
                else:
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
                if _pinned_for_entry(entry, self._pack) is not None:
                    _paint_row(self.table, index, in_pack_bg, actions)

    def reveal_mod(self, guid: str, repo: str = "") -> bool:
        target = None
        for entry in self._entries:
            if guid and (guid == entry.primary_guid or guid in entry.guids):
                target = entry
                break
        if target is None and repo:
            for entry in self._entries:
                if same_repo(entry.repo, repo):
                    target = entry
                    break
        if target is None:
            return False
        if self.hide_in_pack.isChecked() and _pinned_for_entry(target, self._pack) is not None:
            self.hide_in_pack.setChecked(False)
        if self._filter.text():
            self._filter.clear()
        key = target.primary_guid.casefold()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item is None:
                continue
            stored = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if stored == key or target.primary_guid in item.toolTip().splitlines():
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                self.table.setCurrentCell(row, 0)
                return True
        return False

    def _on_double_click(self, row: int, _column: int) -> None:
        guid = self._guid_at_row(row)
        if guid:
            self.details_requested.emit(guid)

    def _guid_at_row(self, row: int) -> str:
        item = self.table.item(row, 1)
        if item is None:
            return ""
        key = str(item.data(Qt.ItemDataRole.UserRole) or "")
        for entry in self._entries:
            if entry.primary_guid.casefold() == key:
                return entry.primary_guid
            if entry.primary_guid in item.toolTip().splitlines():
                return entry.primary_guid
        return ""


def catalog_pack_button(entry: CatalogEntry, pack: ModPack | None) -> tuple[str, str]:
    pinned = _pinned_for_entry(entry, pack)
    if pinned is None:
        return (
            "Add to pack",
            "Download this mod and add it to the selected pack. You can choose a version.",
        )
    if entry.latest_raw and is_newer(entry.latest_raw, pinned.version):
        return (
            "Update",
            "A newer version is available. Choose a version to download and pin on the pack.",
        )
    return (
        "In pack",
        f"Already in the pack at {pinned.version_raw or pinned.version}. Click to choose a different version.",
    )


def _pinned_for_entry(entry: CatalogEntry, pack: ModPack | None) -> PinnedMod | None:
    if pack is None:
        return None
    for guid in entry.guids:
        pinned = pack.find_mod(guid)
        if pinned is not None:
            return pinned
    return None


def _catalog_status(entry: CatalogEntry, pack: ModPack | None) -> str:
    if not entry.available:
        return "Unavailable"
    if pack is None:
        return "Custom" if entry.custom else "Available"
    pinned = _pinned_for_entry(entry, pack)
    if pinned is None:
        return "Custom" if entry.custom else "Available"
    if entry.latest_raw and is_newer(entry.latest_raw, pinned.version):
        return "Update"
    return f"Installed {pinned.version}"


def _entry_matches_filter(entry: CatalogEntry, query: str) -> bool:
    if not query:
        return True
    return (
        query in entry.name.lower()
        or query in entry.primary_guid.lower()
        or query in entry.repo.lower()
        or any(query in guid.lower() for guid in entry.guids)
    )


def _in_pack_row_background(widget: QWidget) -> QColor:
    base = widget.palette().color(QPalette.ColorRole.Base)
    tint = base.lighter(118)
    if tint == base:
        tint = base.darker(104)
    return tint


def _paint_row(table: QTableWidget, row: int, color: QColor, actions: QWidget) -> None:
    brush = QBrush(color)
    for column in range(table.columnCount()):
        item = table.item(row, column)
        if item is not None:
            item.setBackground(brush)
    actions.setAutoFillBackground(True)
    palette = actions.palette()
    palette.setColor(QPalette.ColorRole.Window, color)
    actions.setPalette(palette)
