from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.models import CatalogEntry, ModPack, is_newer
from sailwind_mod_sync.ui.links import repo_or_find_button
from sailwind_mod_sync.ui.tables import enable_column_resize


class PackView(QWidget):
    toggle_enabled = Signal(str, bool)
    update_requested = Signal(str)
    import_requested = Signal(str)
    find_repo_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = QLabel("No pack selected")
        self.subtitle = QLabel("")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["On", "Mod", "GUID", "Pinned", "Latest", ""])
        enable_column_resize(self.table, [48, 180, 220, 90, 110, 360])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.table)

    def set_pack(
        self,
        pack: ModPack | None,
        catalog: list[CatalogEntry],
        missing_guids: set[str] | None = None,
    ) -> None:
        if pack is None:
            self.title.setText("No pack selected")
            self.subtitle.setText("")
            self.table.setRowCount(0)
            return
        missing = missing_guids or set()
        latest_by_guid = {}
        names = {}
        repo_by_guid = {}
        for entry in catalog:
            names[entry.primary_guid] = entry.name
            for guid in entry.guids:
                latest_by_guid[guid] = entry.latest_raw or ""
                names.setdefault(guid, entry.name)
                repo_by_guid.setdefault(guid, entry.repo)
        self.title.setText(pack.name)
        missing_count = sum(1 for pinned in pack.mods if pinned.guid in missing)
        subtitle = f"{len(pack.mods)} mods · BepInEx {pack.bepinex or '—'}"
        if missing_count:
            subtitle += f" · {missing_count} missing"
        self.subtitle.setText(subtitle)
        self.table.setRowCount(len(pack.mods))
        for index, pinned in enumerate(pack.mods):
            checkbox = QCheckBox()
            checkbox.setChecked(pinned.enabled)
            guid = pinned.guid
            checkbox.toggled.connect(lambda checked, value=guid: self.toggle_enabled.emit(value, checked))
            wrap = QWidget()
            wrap_layout = QHBoxLayout(wrap)
            wrap_layout.setContentsMargins(8, 0, 0, 0)
            wrap_layout.addWidget(checkbox)
            wrap_layout.addStretch()
            self.table.setCellWidget(index, 0, wrap)

            name = names.get(pinned.guid, pinned.guid.split(".")[-1])
            self.table.setItem(index, 1, QTableWidgetItem(name))
            self.table.setItem(index, 2, QTableWidgetItem(pinned.guid))
            self.table.setItem(index, 3, QTableWidgetItem(pinned.version_raw or pinned.version))
            latest = latest_by_guid.get(pinned.guid, "")
            is_missing = guid in missing
            latest_item = QTableWidgetItem("Missing" if is_missing else latest)
            if is_missing:
                latest_item.setToolTip("This version is not in the library. Import a .dll or .zip to add it.")
            elif latest and is_newer(latest, pinned.version):
                latest_item.setText(f"{latest} (update)")
            self.table.setItem(index, 4, latest_item)

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 0, 4, 0)
            actions_layout.addWidget(
                repo_or_find_button(
                    pinned.repo or repo_by_guid.get(guid, ""),
                    actions,
                    lambda value=guid: self.find_repo_requested.emit(value),
                )
            )
            if is_missing:
                import_btn = QPushButton("Import")
                import_btn.setToolTip("Import a .dll or .zip for this missing mod")
                import_btn.clicked.connect(lambda _=False, value=guid: self.import_requested.emit(value))
                actions_layout.addWidget(import_btn)
            else:
                update_btn = QPushButton("Update")
                update_btn.setEnabled(bool(latest and is_newer(latest, pinned.version)))
                update_btn.clicked.connect(lambda _=False, value=guid: self.update_requested.emit(value))
                actions_layout.addWidget(update_btn)
            remove_btn = QPushButton("Remove")
            remove_btn.clicked.connect(lambda _=False, value=guid: self.remove_requested.emit(value))
            actions_layout.addWidget(remove_btn)
            self.table.setCellWidget(index, 5, actions)
