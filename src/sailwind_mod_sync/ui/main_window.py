from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.catalog.mvc import find_entry
from sailwind_mod_sync.constants import APP_NAME, APP_REPO, APP_VERSION
from sailwind_mod_sync.game.backup import BackupError, inspect_bepinex_zip
from sailwind_mod_sync.manager import Manager
from sailwind_mod_sync.models import parse_mod_version, version_key
from sailwind_mod_sync.ui.catalog_view import CatalogView
from sailwind_mod_sync.ui.library_view import LibraryView
from sailwind_mod_sync.ui.mod_details_dialog import ModDetailsDialog
from sailwind_mod_sync.ui.missing_mods_dialog import MissingModsWarningDialog
from sailwind_mod_sync.ui.pack_view import PackView
from sailwind_mod_sync.ui.progress_dialog import BusyDialog
from sailwind_mod_sync.ui.repo_dialog import RepoUrlDialog
from sailwind_mod_sync.ui.settings_dialog import SettingsDialog
from sailwind_mod_sync.ui.update_dialog import OPEN, SKIP, UPDATE, UpdateDialog
from sailwind_mod_sync.ui.version_dialog import SelectVersionDialog
from sailwind_mod_sync.ui.workers import TaskBridge, run_background
from sailwind_mod_sync.updater import (
    AppUpdate,
    download_and_stage_update,
    find_app_update,
    launch_apply_and_exit,
    update_check_due,
    utc_now_iso,
)

log = logging.getLogger(__name__)

PLAY_BUTTON_STYLE = """
QPushButton {
    background-color: #2e7d32;
    color: white;
    font-weight: 600;
    border: none;
    border-radius: 4px;
    padding: 8px 12px;
}
QPushButton:hover {
    background-color: #388e3c;
}
QPushButton:pressed {
    background-color: #1b5e20;
}
QPushButton:disabled {
    background-color: #81c784;
    color: #e8f5e9;
}
"""


class MainWindow(QMainWindow):
    def __init__(self, manager: Manager) -> None:
        super().__init__()
        self.manager = manager
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1200, 760)
        self._busy = False
        self._bridge: TaskBridge | None = None
        self._update_bridge: TaskBridge | None = None
        self._on_ok: Callable | None = None
        self._progress_dialog: BusyDialog | None = None

        self.pack_list = QListWidget()
        self.pack_list.currentItemChanged.connect(self._on_pack_selected)
        self.pack_list.itemDoubleClicked.connect(lambda _item: self._rename_pack())

        self.play_button = QPushButton("Play")
        self.play_button.setMinimumHeight(48)
        self.play_button.setStyleSheet(PLAY_BUTTON_STYLE)
        self.play_button.setToolTip("Launch Sailwind with the selected ModPack")
        self.play_button.clicked.connect(self._play)
        self.vanilla_button = QPushButton("Launch Vanilla")
        self.vanilla_button.setToolTip("Start Sailwind without mods (Doorstop disabled)")
        self.vanilla_button.clicked.connect(self._play_vanilla)

        new_btn = QPushButton("New")
        new_btn.clicked.connect(self._new_pack)
        dup_btn = QPushButton("Duplicate")
        dup_btn.clicked.connect(self._duplicate_pack)
        rename_btn = QPushButton("Rename")
        rename_btn.clicked.connect(self._rename_pack)
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self._delete_pack)
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._export_pack)
        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self._import_pack)

        pack_buttons = QHBoxLayout()
        pack_buttons.addWidget(new_btn)
        pack_buttons.addWidget(dup_btn)
        pack_buttons.addWidget(rename_btn)
        pack_buttons.addWidget(del_btn)

        io_buttons = QHBoxLayout()
        io_buttons.addWidget(export_btn)
        io_buttons.addWidget(import_btn)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("ModPacks"))
        left_layout.addWidget(self.pack_list, 1)
        left_layout.addLayout(pack_buttons)
        left_layout.addLayout(io_buttons)
        left_layout.addWidget(self.play_button)
        left_layout.addWidget(self.vanilla_button)

        self.pack_view = PackView()
        self.catalog_view = CatalogView()
        self.library_view = LibraryView()
        self.pack_view.toggle_enabled.connect(self._toggle_mod)
        self.pack_view.update_requested.connect(self._update_mod)
        self.pack_view.import_requested.connect(self._import_missing_mod)
        self.pack_view.find_repo_requested.connect(self._find_pack_repo)
        self.pack_view.remove_requested.connect(self._remove_mod)
        self.pack_view.version_requested.connect(self._set_pack_mod_version)
        self.pack_view.browse_versions_requested.connect(self._browse_pack_mod_versions)
        self.catalog_view.install_requested.connect(self._install_from_catalog)
        self.catalog_view.refresh_clicked.connect(self._refresh_catalog)
        self.catalog_view.add_repo_clicked.connect(self._add_catalog_repo)
        self.catalog_view.remove_custom_requested.connect(self._remove_custom_catalog)
        self.library_view.add_to_pack_requested.connect(self._add_library_mod)
        self.library_view.find_repo_requested.connect(self._find_library_repo)
        self.library_view.details_requested.connect(self._show_mod_details)
        self.library_view.delete_requested.connect(self._delete_artifact)
        self.library_view.rename_requested.connect(self._rename_library_mod)
        self.library_view.prune_requested.connect(self._prune_library)
        self.library_view.import_clicked.connect(self._import_local_mod)

        tabs = QTabWidget()
        tabs.addTab(self.pack_view, "Pack")
        tabs.addTab(self.catalog_view, "Catalog")
        tabs.addTab(self.library_view, "Library")

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 920])
        self.setCentralWidget(splitter)

        settings_action = self.menuBar().addAction("Settings")
        settings_action.triggered.connect(self._open_settings)
        scan_action = self.menuBar().addAction("Scan updates")
        scan_action.triggered.connect(self._scan_updates)
        import_game_action = self.menuBar().addAction("Import game plugins")
        import_game_action.triggered.connect(self._import_game_plugins)
        backup_menu = self.menuBar().addMenu("Backup")
        self.backup_action = backup_menu.addAction("Backup BepInEx")
        self.backup_action.setStatusTip(
            "Zip the current BepInEx folder (game install, or this pack if the game has none)"
        )
        self.backup_action.triggered.connect(self._backup_bepinex)
        self.restore_action = backup_menu.addAction("Restore BepInEx")
        self.restore_action.setStatusTip("Replace the current BepInEx folder from a backup zip")
        self.restore_action.triggered.connect(self._restore_bepinex)
        vanilla_action = self.menuBar().addAction("Launch vanilla")
        vanilla_action.triggered.connect(self._play_vanilla)
        import_mod_action = self.menuBar().addAction("Import mod file")
        import_mod_action.triggered.connect(self._import_local_mod)
        help_menu = self.menuBar().addMenu("Help")
        check_updates = help_menu.addAction("Check for updates…")
        check_updates.triggered.connect(self._check_for_updates)
        about = help_menu.addAction("About")
        about.triggered.connect(self._about)
        self.statusBar().showMessage("Ready")

        self._reload_packs()
        self._reload_views()
        if not self.manager.catalog:
            self._refresh_catalog()
        QTimer.singleShot(4000, self._maybe_check_updates)

    def current_pack_id(self) -> str | None:
        item = self.pack_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _reload_packs(self) -> None:
        current = self.current_pack_id() or self.manager.config.last_pack_id
        self.pack_list.blockSignals(True)
        self.pack_list.clear()
        selected = None
        for pack in self.manager.packs.list_packs():
            item = QListWidgetItem(pack.name)
            item.setData(Qt.ItemDataRole.UserRole, pack.id)
            self.pack_list.addItem(item)
            if pack.id == current:
                selected = item
        self.pack_list.blockSignals(False)
        if selected:
            self.pack_list.setCurrentItem(selected)
        elif self.pack_list.count():
            self.pack_list.setCurrentRow(0)

    def _reload_views(self) -> None:
        pack_id = self.current_pack_id()
        pack = self.manager.packs.get(pack_id) if pack_id else None
        missing = {mod.guid for mod in self.manager.missing_mods(pack)}
        library = self.manager.library.list_mods()
        library_versions: dict[str, set[str]] = {}
        library_version_rows: dict[str, list[tuple[str, str]]] = {}
        for item in library:
            library_versions.setdefault(item.guid, set()).add(item.version)
            library_version_rows.setdefault(item.guid, []).append(
                (item.version, item.meta.version_raw or item.version)
            )
        for rows in library_version_rows.values():
            rows.sort(key=lambda pair: version_key(pair[0]), reverse=True)
        display_names = {
            item.guid: self.manager.mod_display_name(
                item.guid,
                plugin_folders=list(item.meta.plugin_folders),
                repo=item.meta.repo,
            )
            for item in library
        }
        if pack:
            for pinned in pack.mods:
                display_names.setdefault(
                    pinned.guid,
                    self.manager.mod_display_name(
                        pinned.guid,
                        plugin_folders=list(pinned.plugin_folders),
                        repo=pinned.repo,
                    ),
                )
        self.pack_view.set_pack(pack, self.manager.catalog, missing, library_version_rows, display_names)
        self.catalog_view.set_data(self.manager.catalog, pack, library_versions)
        self.library_view.set_entries(library, pack, display_names)
        game = self.manager.game_dir()
        if game:
            self.statusBar().showMessage(f"Game: {game}")
        else:
            self.statusBar().showMessage("Set the Sailwind folder in Settings")

    def _on_pack_selected(self) -> None:
        pack_id = self.current_pack_id()
        if pack_id:
            self.manager.config.last_pack_id = pack_id
            self.manager.save_config()
        self._reload_views()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.manager.config, self.manager.paths, self)
        if dialog.exec():
            dialog.apply_to(self.manager.config)
            self.manager.save_config()
            self.manager.reload_http()
            self._reload_views()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About",
            (
                f"{APP_NAME} {APP_VERSION}\n\n"
                "Keeps Sailwind vanilla and launches isolated Doorstop ModPacks.\n\n"
                f"{APP_REPO}"
            ),
        )

    def _maybe_check_updates(self) -> None:
        config = self.manager.config
        if not config.check_for_updates:
            return
        if not update_check_due(config.last_update_check):
            return
        if self._busy:
            QTimer.singleShot(4000, self._maybe_check_updates)
            return
        self._start_silent_update_check()

    def _start_silent_update_check(self) -> None:
        if self._update_bridge is not None:
            return
        log.info("Checking GitHub for app updates")
        bridge = TaskBridge(self)
        self._update_bridge = bridge
        queued = Qt.ConnectionType.QueuedConnection
        bridge.finished.connect(self._silent_update_found, queued)
        bridge.failed.connect(self._silent_update_failed, queued)
        run_background(lambda progress: self._lookup_app_update(False, progress), bridge)

    def _lookup_app_update(self, ignore_skipped: bool, progress) -> object:
        return find_app_update(
            self.manager.http,
            current_version=APP_VERSION,
            skipped_version=self.manager.config.skipped_update_version,
            ignore_skipped=ignore_skipped,
            paths=self.manager.paths,
            progress=progress,
        )

    @Slot(object)
    def _silent_update_found(self, result: object) -> None:
        self._update_bridge = None
        self.manager.config.last_update_check = utc_now_iso()
        self.manager.save_config()
        if isinstance(result, AppUpdate):
            self._offer_app_update(result)

    @Slot(str)
    def _silent_update_failed(self, message: str) -> None:
        self._update_bridge = None
        log.warning("App update check failed: %s", message)

    def _check_for_updates(self) -> None:
        self._run(
            lambda progress: self._lookup_app_update(True, progress),
            self._manual_update_checked,
            "Checking for updates…",
        )

    def _manual_update_checked(self, result: object) -> None:
        self.manager.config.last_update_check = utc_now_iso()
        self.manager.save_config()
        if isinstance(result, AppUpdate):
            self._offer_app_update(result)
            return
        QMessageBox.information(
            self,
            "Up to date",
            f"{APP_NAME} {APP_VERSION} is the latest release on GitHub.",
        )

    def _offer_app_update(self, update) -> None:
        dialog = UpdateDialog(update, self)
        dialog.exec()
        choice = dialog.choice()
        if choice == SKIP:
            self.manager.config.skipped_update_version = update.version
            self.manager.save_config()
            self.statusBar().showMessage(f"Skipping {update.version_raw}")
            return
        if choice == OPEN:
            QDesktopServices.openUrl(QUrl(update.html_url))
            return
        if choice != UPDATE:
            return
        self._run(
            lambda progress: download_and_stage_update(
                self.manager.http, update, self.manager.paths, progress=progress
            ),
            self._install_app_update,
            f"Downloading {update.version_raw}…",
        )

    def _install_app_update(self, payload: object) -> None:
        if not isinstance(payload, Path):
            QMessageBox.warning(self, "Update failed", "The update payload was not a folder.")
            return
        try:
            launch_apply_and_exit(payload)
        except Exception as exc:
            QMessageBox.critical(self, "Update failed", str(exc))
            return
        self.statusBar().showMessage("Installing update…")
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(300, app.quit)

    def _new_pack(self) -> None:
        name, ok = QInputDialog.getText(self, "New ModPack", "Name:")
        if not ok or not name.strip():
            return
        pack = self.manager.packs.create(name.strip())
        self.manager.config.last_pack_id = pack.id
        self.manager.save_config()
        self._reload_packs()
        self._reload_views()

    def _duplicate_pack(self) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            return
        source = self.manager.packs.get(pack_id)
        name, ok = QInputDialog.getText(self, "Duplicate ModPack", "Name:", text=f"{source.name} copy")
        if not ok or not name.strip():
            return
        pack = self.manager.packs.duplicate(pack_id, name.strip())
        self.manager.config.last_pack_id = pack.id
        self.manager.save_config()
        self._reload_packs()
        self._reload_views()

    def _rename_pack(self) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            return
        pack = self.manager.packs.get(pack_id)
        name, ok = QInputDialog.getText(self, "Rename ModPack", "Name:", text=pack.name)
        if not ok:
            return
        new_name = name.strip()
        if not new_name or new_name == pack.name:
            return
        self.manager.packs.rename(pack_id, new_name)
        self._reload_packs()
        self._reload_views()
        self.statusBar().showMessage(f"Renamed to {new_name}")

    def _delete_pack(self) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            return
        pack = self.manager.packs.get(pack_id)
        if QMessageBox.question(self, "Delete ModPack", f"Delete {pack.name}?") != QMessageBox.StandardButton.Yes:
            return
        self.manager.packs.delete(pack_id)
        if not self.manager.packs.list_packs():
            created = self.manager.packs.ensure_default()
            self.manager.config.last_pack_id = created.id
        self.manager.save_config()
        self._reload_packs()
        self._reload_views()

    def _export_pack(self) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            return
        pack = self.manager.packs.get(pack_id)
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Export ModPack",
            f"{pack.id}.json",
            "ModPack JSON (*.json);;ModPack bundle (*.zip)",
        )
        if not path:
            return
        bundle = selected.startswith("ModPack bundle") or path.lower().endswith(".zip")
        dest = Path(path)
        if bundle and dest.suffix.lower() != ".zip":
            dest = dest.with_suffix(".zip")
        try:
            self.manager.export_pack(pack_id, dest, bundle=bundle)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.statusBar().showMessage(f"Exported {dest}")

    def _import_pack(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import ModPack",
            "",
            "ModPack (*.json *.zip)",
        )
        if not path:
            return
        log.info("User chose pack import %s", path)

        def work(progress):
            return self.manager.import_pack(Path(path), progress=progress)

        self._run(work, self._imported, "Importing ModPack…")

    def _imported(self, pack) -> None:
        self.manager.config.last_pack_id = pack.id
        self.manager.save_config()
        self._reload_packs()
        self._reload_views()
        missing = self.manager.missing_mods(pack)
        if missing:
            self.statusBar().showMessage(
                f"Imported {pack.name} · {len(missing)} missing mod(s) — use Import on the Pack tab"
            )
        else:
            self.statusBar().showMessage(f"Imported {pack.name}")

    def _import_game_plugins(self) -> None:
        name, ok = QInputDialog.getText(self, "Import game plugins", "ModPack name:", text="Current game")
        if not ok or not name.strip():
            return

        def work(progress):
            return self.manager.import_game_plugins(pack_name=name.strip(), progress=progress)

        self._run(work, self._imported, "Importing installed plugins…")

    def _backup_bepinex(self) -> None:
        pack_id = self.current_pack_id()
        try:
            source, kind = self.manager.resolve_bepinex_folder(pack_id)
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "No BepInEx folder", str(exc))
            return
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        label = "game" if kind == "game" else "pack"
        default = self.manager.paths.backups_dir / f"BepInEx-{label}-{stamp}.zip"
        self.manager.paths.backups_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Backup BepInEx folder",
            str(default),
            "Zip archive (*.zip)",
        )
        if not path:
            return
        dest = Path(path)
        if dest.suffix.lower() != ".zip":
            dest = dest.with_suffix(".zip")

        def work(progress):
            return self.manager.backup_bepinex(dest, pack_id=pack_id, source=source, progress=progress)

        self._run(work, self._bepinex_backed_up, f"Backing up {source}…")

    def _bepinex_backed_up(self, result) -> None:
        extra = f" ({result.skipped} skipped)" if result.skipped else ""
        self.statusBar().showMessage(f"Backed up {result.file_count} files{extra} to {result.dest}")
        QMessageBox.information(
            self,
            "Backup complete",
            f"Saved {result.file_count} files from\n{result.source}\n\nto\n{result.dest}{extra}",
        )

    def _restore_bepinex(self) -> None:
        start = str(self.manager.paths.backups_dir)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Restore BepInEx backup",
            start,
            "Zip archive (*.zip)",
        )
        if not path:
            return
        archive = Path(path)
        try:
            inspect_bepinex_zip(archive)
        except BackupError as exc:
            QMessageBox.critical(self, "Not a BepInEx backup", str(exc))
            return
        pack_id = self.current_pack_id()
        try:
            dest, kind = self.manager.resolve_bepinex_restore_target(pack_id)
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "No restore location", str(exc))
            return
        where = "the Sailwind BepInEx folder" if kind == "game" else "this ModPack's BepInEx folder"
        if (
            QMessageBox.question(
                self,
                "Restore BepInEx",
                f"Replace {where}?\n\n{dest}\n\nClose Sailwind first. This cannot be undone except by restoring another backup.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def work(progress):
            return self.manager.restore_bepinex(archive, pack_id=pack_id, dest=dest, progress=progress)

        self._run(work, self._bepinex_restored, f"Restoring {archive.name}…")

    def _bepinex_restored(self, result) -> None:
        self.statusBar().showMessage(f"Restored {result.file_count} files to {result.dest}")
        QMessageBox.information(
            self,
            "Restore complete",
            f"Restored {result.file_count} files to\n{result.dest}",
        )

    def _refresh_catalog(self) -> None:
        self._run(lambda progress: self.manager.refresh_catalog(progress=progress), self._catalog_loaded, "Refreshing catalog…")

    def _catalog_loaded(self, _result) -> None:
        self._reload_views()
        self.statusBar().showMessage(f"Catalog: {len(self.manager.catalog)} mods")

    def _add_catalog_repo(self) -> None:
        dialog = RepoUrlDialog(
            "",
            self,
            title="Add repository",
            hint=(
                "Paste a GitHub or GitLab repository URL that is not in ModVersionChecker. "
                "owner/repo also works. The latest release is checked and added to the catalog."
            ),
        )
        if not dialog.exec():
            return
        url = dialog.repo_url()

        def work(progress):
            return self.manager.add_catalog_repo(url, progress=progress)

        self._run(work, self._catalog_repo_added, "Adding repository…")

    def _catalog_repo_added(self, entry) -> None:
        self._reload_views()
        name = getattr(entry, "name", None) or "repository"
        guid = getattr(entry, "primary_guid", "")
        extra = f" ({guid})" if guid else ""
        self.statusBar().showMessage(f"Catalog: added {name}{extra}")

    def _remove_custom_catalog(self, guid: str) -> None:
        self.manager.remove_catalog_repo(guid)
        self._reload_views()
        self.statusBar().showMessage(f"Removed {guid} from the catalog")

    def _scan_updates(self) -> None:
        self._run(lambda progress: self.manager.scan_updates(live=True, progress=progress), self._updates_scanned, "Scanning repositories…")

    def _updates_scanned(self, _result) -> None:
        self._reload_views()
        self.statusBar().showMessage("Update scan complete")

    def _install_from_catalog(self, guid: str) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            QMessageBox.warning(self, "No pack", "Create or select a ModPack first.")
            return
        entry = find_entry(self.manager.catalog, guid)
        repo = entry.repo if entry else ""
        version = entry.latest_version if entry else None
        version_raw = entry.latest_raw if entry else None

        def work(progress):
            return self.manager.install_mod(
                pack_id,
                guid,
                repo=repo,
                version=version,
                version_raw=version_raw,
                progress=progress,
            )

        name = entry.name if entry else guid
        self._run(work, lambda _r: QTimer.singleShot(0, self._reload_views), f"Adding {name} to library…")

    def _update_mod(self, guid: str) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            return
        self._run(
            lambda progress: self.manager.update_mod(pack_id, guid, progress=progress),
            lambda _r: QTimer.singleShot(0, self._reload_views),
            f"Updating {guid}…",
        )

    def _remove_mod(self, guid: str) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            return
        self.manager.packs.remove_mod(pack_id, guid)
        self._reload_views()

    def _toggle_mod(self, guid: str, enabled: bool) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            return
        try:
            self.manager.set_mod_enabled(pack_id, guid, enabled)
        except Exception as exc:
            QMessageBox.warning(self, "Could not update mod", str(exc))
        self._reload_views()

    def _add_library_mod(self, guid: str, version: str) -> None:
        self._set_pack_mod_version(guid, version, version)

    def _set_pack_mod_version(self, guid: str, version: str, version_raw: str = "") -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            QMessageBox.warning(self, "No pack", "Create or select a ModPack first.")
            return
        pack = self.manager.packs.get(pack_id)
        pinned = pack.find_mod(guid) if pack else None
        current = parse_mod_version(pinned.version) if pinned else None
        chosen = parse_mod_version(version) or version
        if pinned and current == chosen and self.manager.library.has_mod(guid, pinned.version):
            return
        if self.manager.library.has_mod(guid, version):
            try:
                pinned = self.manager.set_pack_mod_version(
                    pack_id, guid, version, version_raw or version
                )
            except Exception as exc:
                QMessageBox.warning(self, "Could not change version", str(exc))
                self._reload_views()
                return
            self._reload_views()
            self.statusBar().showMessage(f"Pinned {pinned.guid} {pinned.version} on the pack")
            return
        self._run(
            lambda progress: self.manager.set_pack_mod_version(
                pack_id,
                guid,
                version,
                version_raw or version,
                progress=progress,
            ),
            lambda _r: QTimer.singleShot(0, self._reload_views),
            f"Fetching {guid} {version_raw or version}…",
        )

    def _browse_pack_mod_versions(self, guid: str) -> None:
        pack_id = self.current_pack_id()
        pack = self.manager.packs.get(pack_id) if pack_id else None
        pinned = pack.find_mod(guid) if pack else None
        if pack is None or pinned is None:
            return
        entry = find_entry(self.manager.catalog, guid)
        name = self.manager.mod_display_name(
            guid,
            plugin_folders=list(pinned.plugin_folders),
            repo=pinned.repo or (entry.repo if entry else ""),
        )
        library_versions = [
            (item.version, item.meta.version_raw or item.version)
            for item in self.manager.library.list_mods()
            if item.guid == guid
        ]
        library_versions.sort(key=lambda pair: version_key(pair[0]), reverse=True)
        repo = pinned.repo or (entry.repo if entry else "")
        dialog = SelectVersionDialog(
            guid=guid,
            name=name,
            current_version=pinned.version,
            library_versions=library_versions,
            repo=repo,
            parent=self,
        )
        if repo:
            dialog.start_remote(
                lambda progress: self.manager.list_remote_mod_versions(repo, progress=progress)
            )
        if not dialog.exec():
            return
        chosen = dialog.selected()
        if chosen is None:
            return
        self._set_pack_mod_version(guid, chosen[0], chosen[1])

    def _find_pack_repo(self, guid: str) -> None:
        pack_id = self.current_pack_id()
        pack = self.manager.packs.get(pack_id) if pack_id else None
        pinned = pack.find_mod(guid) if pack else None
        initial = pinned.repo if pinned else ""
        page = self._ask_repo_url(guid, initial)
        if not page:
            return
        self.manager.set_mod_repo(guid, page)
        if pack_id and pinned and not self.manager.library.has_mod(pinned.guid, pinned.version):
            self._run(
                lambda progress: self.manager.install_mod(
                    pack_id,
                    guid,
                    repo=page,
                    version=pinned.version,
                    version_raw=pinned.version_raw or pinned.version,
                    progress=progress,
                ),
                lambda _r: QTimer.singleShot(0, self._reload_views),
                f"Fetching {guid}…",
            )
            return
        self._reload_views()
        self.statusBar().showMessage(f"Repository set to {page}")

    def _find_library_repo(self, guid: str, version: str) -> None:
        meta = self.manager.library.read_mod_meta(guid, version)
        initial = meta.repo if meta else ""
        page = self._ask_repo_url(guid, initial)
        if not page:
            return
        self.manager.set_mod_repo(guid, page)
        self._reload_views()
        self.statusBar().showMessage(f"Repository set to {page}")

    def _rename_library_mod(self, guid: str) -> None:
        current = self.manager.mod_display_name(guid)
        default = self.manager.mod_display_name(guid, alias="")
        name, ok = QInputDialog.getText(
            self,
            "Rename mod",
            (
                f"Display name for {guid}.\n"
                f"Leave empty to use the default name ({default})."
            ),
            text=current,
        )
        if not ok:
            return
        shown = self.manager.set_mod_alias(guid, name)
        self._reload_views()
        self.statusBar().showMessage(f"Showing {guid} as {shown}")

    def _show_mod_details(self, guid: str, version: str) -> None:
        try:
            details = self.manager.local_mod_details(guid, version)
        except Exception as exc:
            QMessageBox.warning(self, "Mod details", str(exc))
            return
        dialog = ModDetailsDialog(details, self)
        repo = details.repo

        def work(progress):
            return self.manager.fetch_remote_mod_info(repo, progress=progress)

        if repo:
            dialog.start_remote(work)
        dialog.exec()

    def _ask_repo_url(self, guid: str, initial: str = "") -> str | None:
        dialog = RepoUrlDialog(guid, self, initial)
        if not dialog.exec():
            return None
        return dialog.repo_url()

    def _delete_artifact(self, guid: str, version: str) -> None:
        self.manager.library.delete_mod(guid, version)
        self._reload_views()

    def _prune_library(self) -> None:
        removed = self.manager.prune_library()
        self._reload_views()
        self.statusBar().showMessage(f"Pruned {removed} unused artifact(s)")

    def _import_local_mod(self) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            QMessageBox.warning(self, "No pack", "Create or select a ModPack first.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import mod file",
            "",
            "Mod files (*.dll *.zip);;DLL (*.dll);;Zip (*.zip)",
        )
        if not paths:
            return
        files = [Path(item) for item in paths]

        def work(progress):
            imported = []
            for path in files:
                imported.append(self.manager.import_local_mod(path, pack_id, progress=progress))
            return imported

        self._run(work, self._local_mods_imported, f"Importing {files[0].name}…")

    def _import_missing_mod(self, guid: str) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            QMessageBox.warning(self, "No pack", "Create or select a ModPack first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Import file for {guid}",
            "",
            "Mod files (*.dll *.zip);;DLL (*.dll);;Zip (*.zip)",
        )
        if not path:
            return
        file_path = Path(path)

        def work(progress):
            return [self.manager.import_local_mod(file_path, pack_id, progress=progress, guid=guid)]

        self._run(work, self._local_mods_imported, f"Importing {file_path.name}…")

    def _local_mods_imported(self, imported) -> None:
        self._reload_views()
        if not imported:
            return
        names = ", ".join(f"{item.guid} {item.version}" for item in imported)
        self.statusBar().showMessage(f"Imported {names}")

    def _play(self) -> None:
        pack_id = self.current_pack_id()
        if not pack_id:
            return
        if not self._confirm_missing_mods(pack_id):
            return

        def work(progress):
            return self.manager.play(pack_id, progress=progress)

        self._run(work, lambda _r: self.statusBar().showMessage("Sailwind launched"), "Preparing ModPack…")

    def _confirm_missing_mods(self, pack_id: str) -> bool:
        if not self.manager.config.warn_missing_mods:
            return True
        pack = self.manager.packs.get(pack_id)
        missing = self.manager.missing_mods(pack)
        if not missing:
            return True
        dialog = MissingModsWarningDialog(missing, pack.name, self)
        if not dialog.exec():
            return False
        if dialog.stop_reminding:
            self.manager.config.warn_missing_mods = False
            self.manager.save_config()
        return True

    def _play_vanilla(self) -> None:
        try:
            self.manager.play_vanilla()
        except Exception as exc:
            QMessageBox.critical(self, "Launch failed", str(exc))
            return
        self.statusBar().showMessage("Sailwind launched (vanilla)")

    def _run(self, fn, on_ok, busy_message: str) -> None:
        if self._busy:
            self.statusBar().showMessage("Already working…")
            log.info("Ignored overlapping task: %s", busy_message)
            return
        log.info("Starting UI task: %s", busy_message)
        self._busy = True
        self._on_ok = on_ok
        self.play_button.setEnabled(False)
        self.vanilla_button.setEnabled(False)
        self.backup_action.setEnabled(False)
        self.restore_action.setEnabled(False)
        self._set_views_enabled(False)
        self.statusBar().showMessage(busy_message)

        dialog = BusyDialog(self, "Working", busy_message)
        self._progress_dialog = dialog
        dialog.show()
        dialog.raise_()
        QApplication.processEvents()

        bridge = TaskBridge(self)
        self._bridge = bridge
        queued = Qt.ConnectionType.QueuedConnection
        bridge.progress.connect(self._on_progress, queued)
        bridge.finished.connect(self._on_task_ok, queued)
        bridge.failed.connect(self._on_fail, queued)
        QTimer.singleShot(0, lambda: run_background(fn, bridge))

    def _set_views_enabled(self, enabled: bool) -> None:
        self.catalog_view.setEnabled(enabled)
        self.pack_view.setEnabled(enabled)
        self.library_view.setEnabled(enabled)

    def _close_progress(self) -> None:
        dialog = self._progress_dialog
        self._progress_dialog = None
        if dialog is None:
            return
        dialog.allow_close()
        dialog.hide()
        dialog.deleteLater()

    def _clear_busy(self) -> None:
        self._busy = False
        self._on_ok = None
        if self._bridge is not None:
            self._bridge.deleteLater()
            self._bridge = None
        self.play_button.setEnabled(True)
        self.vanilla_button.setEnabled(True)
        self.backup_action.setEnabled(True)
        self.restore_action.setEnabled(True)
        self._set_views_enabled(True)

    @Slot(str)
    def _on_progress(self, message: str) -> None:
        self.statusBar().showMessage(message)
        if self._progress_dialog is not None:
            self._progress_dialog.set_message(message)

    @Slot(object)
    def _on_task_ok(self, result: object) -> None:
        callback = self._on_ok
        self._close_progress()
        self._clear_busy()
        log.info("UI task finished")
        if callback is not None:
            callback(result)

    @Slot(str)
    def _on_fail(self, message: str) -> None:
        self._close_progress()
        self._clear_busy()
        text = (message or "").strip() or "The task failed."
        log.error("UI task failed: %s", text)
        QMessageBox.critical(self, "Error", text)
        self.statusBar().showMessage(text)
        self._reload_views()
