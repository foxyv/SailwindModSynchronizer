from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.catalog.custom import same_repo
from sailwind_mod_sync.catalog.github import repo_page_url
from sailwind_mod_sync.models import CatalogEntry, ModPack, PinnedMod, is_newer
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
    import_file_clicked = Signal()
    find_repo_requested = Signal(str)
    show_in_catalog_requested = Signal(str)
    remove_requested = Signal(str)
    version_requested = Signal(str, str, str)
    browse_versions_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = QLabel("No pack selected")
        self.subtitle = QLabel("")
        self.import_file = QPushButton("Import Mod DLL/ZIP")
        self.import_file.setToolTip("Import a .dll or .zip into the library and add it to this pack")
        self.import_file.setEnabled(False)
        self.import_file.clicked.connect(self.import_file_clicked.emit)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["On", "Mod", "GUID", "Version", "Latest", ""])
        enable_column_resize(self.table, [48, 180, 220, 140, 110, 220])
        enable_column_sort(self.table, default_column=None)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        self._row_state: dict[str, tuple[str, bool, bool, bool]] = {}

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        header.addWidget(self.import_file)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
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
            self.import_file.setEnabled(False)
            self._row_state = {}
            with sorting_paused(self.table):
                self.table.setRowCount(0)
            return
        self.import_file.setEnabled(True)
        missing = missing_guids or set()
        versions = library_versions or {}
        latest_by_guid = {}
        latest_version_by_guid = {}
        names = {}
        repo_by_guid = {}
        catalog_guids: set[str] = set()
        for entry in catalog:
            names[entry.primary_guid] = entry.name
            catalog_guids.add(entry.primary_guid)
            catalog_guids.update(entry.guids)
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
        self._row_state = {}
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
                self._enable_row_context_menu(wrap, guid)
                self.table.setItem(index, 0, sortable_item("", 1 if pinned.enabled else 0))
                self.table.setCellWidget(index, 0, wrap)

                name = (display_names or {}).get(pinned.guid) or names.get(pinned.guid, pinned.guid.split(".")[-1])
                self.table.setItem(index, 1, sortable_item(name))
                self.table.setItem(index, 2, sortable_item(pinned.guid))
                self.table.setItem(index, 3, sortable_item(pinned.version_raw or pinned.version, version_sort_key(pinned.version)))
                version_combo = self._version_combo(
                    pinned,
                    versions.get(guid, []),
                    catalog_latest_raw=latest_by_guid.get(guid, ""),
                    catalog_latest_version=latest_version_by_guid.get(guid),
                    has_repo=bool(pinned.repo or repo_by_guid.get(guid, "")),
                    missing=guid in missing,
                )
                self._enable_row_context_menu(version_combo, guid)
                self.table.setCellWidget(index, 3, version_combo)
                latest = latest_by_guid.get(pinned.guid, "")
                is_missing = guid in missing
                can_update = bool(latest and is_newer(latest, pinned.version))
                repo = pinned.repo or repo_by_guid.get(guid, "")
                in_catalog = guid in catalog_guids or any(
                    same_repo(entry.repo, repo) for entry in catalog if repo
                )
                self._row_state[guid] = (repo, is_missing, can_update, in_catalog)
                latest_label = "Missing" if is_missing else latest
                latest_key = (1, version_sort_key(None)) if is_missing else (0, version_sort_key(latest))
                latest_item = sortable_item(latest_label, latest_key)
                if is_missing:
                    latest_item.setToolTip("This version is not in the library. Import a .dll or .zip to add it.")
                elif can_update:
                    latest_item.setText(f"{latest} (update)")
                self.table.setItem(index, 4, latest_item)
                self.table.setItem(index, 5, sortable_item(""))

                actions = QWidget()
                actions_layout = QHBoxLayout(actions)
                actions_layout.setContentsMargins(4, 0, 4, 0)
                if is_missing:
                    import_btn = QPushButton("Import")
                    import_btn.setToolTip("Import a .dll or .zip for this missing mod")
                    import_btn.clicked.connect(lambda _=False, value=guid: self.import_requested.emit(value))
                    actions_layout.addWidget(import_btn)
                else:
                    update_btn = QPushButton("Update")
                    update_btn.setEnabled(can_update)
                    update_btn.clicked.connect(lambda _=False, value=guid: self.update_requested.emit(value))
                    actions_layout.addWidget(update_btn)
                remove_btn = QPushButton("Remove")
                remove_btn.clicked.connect(lambda _=False, value=guid: self.remove_requested.emit(value))
                actions_layout.addWidget(remove_btn)
                self._enable_row_context_menu(actions, guid)
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

    def _enable_row_context_menu(self, widget: QWidget, guid: str) -> None:
        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda pos, value=guid, host=widget: self._popup_menu_for_guid(value, host.mapToGlobal(pos))
        )

    def _show_table_context_menu(self, pos) -> None:
        row = self.table.indexAt(pos).row()
        item = self.table.item(row, 2)
        if item is None:
            return
        self.table.selectRow(row)
        self._popup_menu_for_guid(item.text(), self.table.viewport().mapToGlobal(pos))

    def _popup_menu_for_guid(self, guid: str, global_pos) -> None:
        menu = self._menu_for_guid(guid)
        if menu is None:
            return
        menu.exec(global_pos)

    def _menu_for_guid(self, guid: str) -> QMenu | None:
        state = self._row_state.get(guid)
        if state is None:
            return None
        repo, missing, can_update, in_catalog = state
        menu = QMenu(self)
        page = repo_page_url(repo)
        if page:
            label = "Open GitLab in Browser" if "gitlab.com" in page.lower() else "Open GitHub in Browser"
            open_repo = menu.addAction(label)
            open_repo.setToolTip(page)
            open_repo.triggered.connect(lambda _=False, url=page: QDesktopServices.openUrl(QUrl(url)))
        else:
            add_repo = menu.addAction("Add Repository")
            add_repo.triggered.connect(lambda _=False, value=guid: self.find_repo_requested.emit(value))
        if in_catalog:
            show_catalog = menu.addAction("Show in Catalog")
            show_catalog.triggered.connect(
                lambda _=False, value=guid: self.show_in_catalog_requested.emit(value)
            )
        menu.addSeparator()
        if missing:
            import_action = menu.addAction("Import")
            import_action.triggered.connect(lambda _=False, value=guid: self.import_requested.emit(value))
        else:
            update_action = menu.addAction("Update")
            update_action.setEnabled(can_update)
            update_action.triggered.connect(lambda _=False, value=guid: self.update_requested.emit(value))
        menu.addAction("Remove").triggered.connect(lambda _=False, value=guid: self.remove_requested.emit(value))
        return menu
