from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.models import CatalogEntry, ModPack, PinnedMod, is_newer
from sailwind_mod_sync.ui.links import repo_or_find_button
from sailwind_mod_sync.ui.tables import (
    enable_column_resize,
    enable_column_sort,
    sortable_item,
    sorting_paused,
    version_sort_key,
)
from sailwind_mod_sync.ui.version_dialog import BROWSE_VERSIONS, pack_version_items


class _VersionCombo(QComboBox):
    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


class PackView(QWidget):
    toggle_enabled = Signal(str, bool)
    update_requested = Signal(str)
    import_requested = Signal(str)
    find_repo_requested = Signal(str)
    remove_requested = Signal(str)
    version_requested = Signal(str, str, str)
    browse_versions_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = QLabel("No pack selected")
        self.subtitle = QLabel("")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["On", "Mod", "GUID", "Version", "Latest", ""])
        enable_column_resize(self.table, [48, 180, 220, 140, 110, 360])
        enable_column_sort(self.table, default_column=None)
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
        library_versions: dict[str, list[tuple[str, str]]] | None = None,
        display_names: dict[str, str] | None = None,
    ) -> None:
        if pack is None:
            self.title.setText("No pack selected")
            self.subtitle.setText("")
            with sorting_paused(self.table):
                self.table.setRowCount(0)
            return
        missing = missing_guids or set()
        versions = library_versions or {}
        latest_by_guid = {}
        latest_version_by_guid = {}
        names = {}
        repo_by_guid = {}
        for entry in catalog:
            names[entry.primary_guid] = entry.name
            for guid in entry.guids:
                latest_by_guid[guid] = entry.latest_raw or ""
                latest_version_by_guid[guid] = entry.latest_version
                names.setdefault(guid, entry.name)
                repo_by_guid.setdefault(guid, entry.repo)
        self.title.setText(pack.name)
        missing_count = sum(1 for pinned in pack.mods if pinned.guid in missing)
        subtitle = f"{len(pack.mods)} mods · BepInEx {pack.bepinex or '—'}"
        if missing_count:
            subtitle += f" · {missing_count} missing"
        self.subtitle.setText(subtitle)
        with sorting_paused(self.table):
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
                self.table.setItem(index, 0, sortable_item("", 1 if pinned.enabled else 0))
                self.table.setCellWidget(index, 0, wrap)

                name = (display_names or {}).get(pinned.guid) or names.get(pinned.guid, pinned.guid.split(".")[-1])
                self.table.setItem(index, 1, sortable_item(name))
                self.table.setItem(index, 2, sortable_item(pinned.guid))
                self.table.setItem(index, 3, sortable_item(pinned.version_raw or pinned.version, version_sort_key(pinned.version)))
                self.table.setCellWidget(
                    index,
                    3,
                    self._version_combo(
                        pinned,
                        versions.get(guid, []),
                        catalog_latest_raw=latest_by_guid.get(guid, ""),
                        catalog_latest_version=latest_version_by_guid.get(guid),
                        has_repo=bool(pinned.repo or repo_by_guid.get(guid, "")),
                        missing=guid in missing,
                    ),
                )
                latest = latest_by_guid.get(pinned.guid, "")
                is_missing = guid in missing
                latest_label = "Missing" if is_missing else latest
                latest_key = (1, version_sort_key(None)) if is_missing else (0, version_sort_key(latest))
                latest_item = sortable_item(latest_label, latest_key)
                if is_missing:
                    latest_item.setToolTip("This version is not in the library. Import a .dll or .zip to add it.")
                elif latest and is_newer(latest, pinned.version):
                    latest_item.setText(f"{latest} (update)")
                self.table.setItem(index, 4, latest_item)
                self.table.setItem(index, 5, sortable_item(""))

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

    def _version_combo(
        self,
        pinned: PinnedMod,
        library_versions: list[tuple[str, str]],
        *,
        catalog_latest_raw: str,
        catalog_latest_version: str | None,
        has_repo: bool,
        missing: bool,
    ) -> QComboBox:
        combo = _VersionCombo()
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setToolTip("Choose which version this pack uses")
        combo.setProperty("pinned_version", pinned.version)
        current_id = pinned.version
        current_index = 0
        for index, (label, data) in enumerate(
            pack_version_items(
                pinned,
                library_versions,
                catalog_latest_raw=catalog_latest_raw,
                catalog_latest_version=catalog_latest_version,
                has_repo=has_repo,
                missing=missing,
            )
        ):
            combo.addItem(label, data)
            if isinstance(data, tuple) and data and data[0] == current_id:
                current_index = index
        combo.blockSignals(True)
        combo.setCurrentIndex(current_index)
        combo.blockSignals(False)
        guid = pinned.guid
        combo.currentIndexChanged.connect(
            lambda index, widget=combo, value=guid: self._on_version_chosen(value, widget, index)
        )
        return combo

    def _on_version_chosen(self, guid: str, combo: QComboBox, index: int) -> None:
        if index < 0:
            return
        data = combo.itemData(index)
        if data == BROWSE_VERSIONS:
            self._restore_combo(combo)
            self.browse_versions_requested.emit(guid)
            return
        if not isinstance(data, tuple) or len(data) != 2:
            return
        version, version_raw = str(data[0]), str(data[1])
        self.version_requested.emit(guid, version, version_raw)

    def _restore_combo(self, combo: QComboBox) -> None:
        pinned_version = combo.property("pinned_version")
        combo.blockSignals(True)
        for index in range(combo.count()):
            data = combo.itemData(index)
            if isinstance(data, tuple) and data and data[0] == pinned_version:
                combo.setCurrentIndex(index)
                break
        combo.blockSignals(False)
