from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QComboBox, QHeaderView, QLabel, QPushButton, QTableWidget

from sailwind_mod_sync.config import AppConfig
from sailwind_mod_sync.models import CatalogEntry, LibraryEntry, ArtifactMeta, ModDetails, ModPack, PinnedMod
from sailwind_mod_sync.paths import AppPaths
from sailwind_mod_sync.updater import AppUpdate
from sailwind_mod_sync.ui.settings_dialog import SettingsDialog
from sailwind_mod_sync.ui.update_dialog import OPEN, SKIP, UPDATE, UpdateDialog
from sailwind_mod_sync.ui.catalog_view import CatalogView, catalog_library_button
from sailwind_mod_sync.ui.library_view import LibraryView
from sailwind_mod_sync.ui.mod_details_dialog import ModDetailsDialog
from sailwind_mod_sync.ui.links import repo_button
from sailwind_mod_sync.ui.missing_mods_dialog import MissingModsWarningDialog
from sailwind_mod_sync.ui.pack_view import PackView
from sailwind_mod_sync.ui.progress_dialog import BusyDialog
from sailwind_mod_sync.ui.tables import enable_column_resize
from sailwind_mod_sync.ui.version_dialog import SelectVersionDialog


def test_busy_dialog_shows_status_text() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = BusyDialog(None, "Working", "Adding SailwindDifficulty to library…")
    try:
        assert dialog.windowTitle() == "Working"
        assert "SailwindDifficulty" in dialog._label.text()
        dialog.set_message("Downloading SailwindDifficulty.dll (40%)")
        assert "40%" in dialog._label.text()
        dialog.allow_close()
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_repo_button_opens_github_url() -> None:
    app = QApplication.instance() or QApplication([])
    button = repo_button("https://github.com/NANDbrew/StickyFix")
    assert button.text() == "GitHub"
    assert button.isEnabled()
    assert button.toolTip() == "https://github.com/NANDbrew/StickyFix"
    missing = repo_button("")
    assert not missing.isEnabled()
    app.processEvents()


def test_table_columns_are_interactive() -> None:
    app = QApplication.instance() or QApplication([])
    table = QTableWidget(0, 3)
    enable_column_resize(table, [80, 120, 160])
    header = table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Interactive
    assert table.columnWidth(1) == 120
    table.deleteLater()
    app.processEvents()


def test_missing_mods_warning_defaults_to_remind() -> None:
    app = QApplication.instance() or QApplication([])
    missing = [
        PinnedMod(guid="local.discord.mystery", version="1.0.0"),
        PinnedMod(guid="com.example.offline", version="2.0.0"),
    ]
    dialog = MissingModsWarningDialog(missing, "Test Pack")
    try:
        assert dialog.windowTitle() == "Missing mods"
        labels = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert "2 missing mods" in labels
        assert "local.discord.mystery 1.0.0" in labels
        assert "com.example.offline 2.0.0" in labels
        assert dialog.remind_radio.isChecked()
        assert not dialog.stop_reminding
        dialog.stop_radio.setChecked(True)
        assert dialog.stop_reminding
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_catalog_view_has_add_repo_button() -> None:
    app = QApplication.instance() or QApplication([])
    view = CatalogView()
    try:
        buttons = view.findChildren(QPushButton)
        labels = [button.text() for button in buttons]
        assert "Add GitHub repo" in labels
        assert "Refresh catalog" in labels
    finally:
        view.deleteLater()
    app.processEvents()


def _catalog_entry(guid: str = "com.example.mod", latest: str = "1.2.0") -> CatalogEntry:
    return CatalogEntry(
        repo="https://github.com/example/mod",
        guids=[guid],
        primary_guid=guid,
        name="mod",
        latest_raw=f"v{latest}",
        latest_version=latest,
        available=True,
    )


def test_catalog_library_button_labels() -> None:
    entry = _catalog_entry()
    assert catalog_library_button(entry, {})[0] == "Add to library"
    assert catalog_library_button(entry, {entry.primary_guid: {"1.2.0"}})[0] == "In library"
    assert catalog_library_button(entry, {entry.primary_guid: {"1.0.0"}})[0] == "Update"


def test_catalog_view_shows_in_library_button() -> None:
    app = QApplication.instance() or QApplication([])
    view = CatalogView()
    try:
        view.set_data([_catalog_entry()], None, {"com.example.mod": {"1.2.0"}})
        labels = [button.text() for button in view.findChildren(QPushButton)]
        assert "In library" in labels
        assert "Add to library" not in labels
    finally:
        view.deleteLater()
    app.processEvents()


def test_library_double_click_requests_details() -> None:
    app = QApplication.instance() or QApplication([])
    view = LibraryView()
    caught: list[tuple[str, str]] = []
    view.details_requested.connect(lambda guid, version: caught.append((guid, version)))
    entry = LibraryEntry(
        guid="com.example.mod",
        version="1.2.0",
        path=Path("."),
        zip_path=Path("."),
        extracted_dir=Path("."),
        meta=ArtifactMeta(
            guid="com.example.mod",
            version="1.2.0",
            version_raw="v1.2.0",
            repo="https://github.com/example/mod",
            source_url="https://example/mod.zip",
            sha256="abc",
            filename="mod.zip",
        ),
        size_bytes=12,
    )
    try:
        view.set_entries([entry])
        view._on_double_click(0, 0)
        assert caught == [("com.example.mod", "1.2.0")]
        assert view.table.item(0, 0).text() == "mod"
        assert view.table.horizontalHeaderItem(0).text() == "Name"
        assert "Rename" in [button.text() for button in view.findChildren(QPushButton)]
    finally:
        view.deleteLater()
    app.processEvents()


def test_mod_details_dialog_shows_installed_versions() -> None:
    app = QApplication.instance() or QApplication([])
    details = ModDetails(
        guid="com.example.mod",
        version="1.1.0",
        name="Example Mod",
        repo="https://github.com/example/mod",
        source_url="https://example/mod.zip",
        filename="mod.zip",
        sha256="abc",
        downloaded_at="2026-01-01",
        plugin_folders=["Mod"],
        size_bytes=2048,
        installed_versions=["1.1.0", "1.0.0"],
        catalog_latest="v1.2.0",
        pack_pins=[("Crew", "1.1.0")],
    )
    dialog = ModDetailsDialog(details)
    try:
        assert dialog.windowTitle() == "Example Mod"
        texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert "1.1.0 (this row)" in texts
        assert "1.0.0" in texts
        assert "v1.2.0" in texts
        assert "Crew (1.1.0)" in texts
        assert "Loading README" in dialog.readme.toPlainText()
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_library_view_uses_supplied_name_and_emits_rename() -> None:
    app = QApplication.instance() or QApplication([])
    view = LibraryView()
    renamed: list[str] = []
    view.rename_requested.connect(renamed.append)
    entry = LibraryEntry(
        guid="com.dizzy.sailwind.gamma",
        version="0.3.3",
        path=Path("."),
        zip_path=Path("."),
        extracted_dir=Path("."),
        meta=ArtifactMeta(
            guid="com.dizzy.sailwind.gamma",
            version="0.3.3",
            version_raw="v0.3.3",
            repo="https://github.com/foxyv/dizzy_sailwind_mods",
            source_url="https://example/gamma.zip",
            sha256="abc",
            filename="gamma.zip",
            plugin_folders=["Dizzy.Gamma"],
        ),
        size_bytes=12,
    )
    try:
        view.set_entries([entry], names={"com.dizzy.sailwind.gamma": "Dizzy Gamma"})
        assert view.table.item(0, 0).text() == "Dizzy Gamma"
        assert view.table.item(0, 1).text() == "com.dizzy.sailwind.gamma"
        rename = next(button for button in view.findChildren(QPushButton) if button.text() == "Rename")
        rename.click()
        assert renamed == ["com.dizzy.sailwind.gamma"]
    finally:
        view.deleteLater()
    app.processEvents()


def test_pack_view_version_combo_emits_choice() -> None:
    app = QApplication.instance() or QApplication([])
    view = PackView()
    chosen: list[tuple[str, str, str]] = []
    browsed: list[str] = []
    view.version_requested.connect(lambda guid, version, raw: chosen.append((guid, version, raw)))
    view.browse_versions_requested.connect(browsed.append)
    pack = ModPack(
        id="crew",
        name="Crew",
        mods=[
            PinnedMod(
                guid="com.example.mod",
                version="1.0.0",
                repo="https://github.com/example/mod",
                version_raw="v1.0.0",
            )
        ],
    )
    try:
        view.set_pack(
            pack,
            [_catalog_entry()],
            set(),
            {"com.example.mod": [("1.1.0", "v1.1.0"), ("1.0.0", "v1.0.0")]},
        )
        combo = view.table.cellWidget(0, 3)
        assert isinstance(combo, QComboBox)
        labels = [combo.itemText(index) for index in range(combo.count())]
        assert combo.currentText() == "v1.0.0"
        assert "v1.1.0" in labels
        assert "More versions…" in labels
        combo.setCurrentIndex(labels.index("More versions…"))
        assert browsed == ["com.example.mod"]
        assert combo.currentText() == "v1.0.0"
        combo.setCurrentIndex(labels.index("v1.1.0"))
        assert chosen == [("com.example.mod", "1.1.0", "v1.1.0")]
    finally:
        view.deleteLater()
    app.processEvents()


def test_select_version_dialog_lists_library_and_remote() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = SelectVersionDialog(
        guid="com.example.mod",
        name="Example",
        current_version="1.0.0",
        library_versions=[("1.0.0", "v1.0.0"), ("0.9.0", "v0.9.0")],
    )
    try:
        labels = [dialog.list.item(index).text() for index in range(dialog.list.count())]
        assert any("v1.0.0" in label and "current" in label for label in labels)
        assert any("v0.9.0" in label and "in library" in label for label in labels)
        dialog._on_remote([("1.2.0", "v1.2.0")])
        labels = [dialog.list.item(index).text() for index in range(dialog.list.count())]
        assert any("v1.2.0" in label and "download" in label for label in labels)
        dialog.list.setCurrentRow(0)
        dialog.accept()
        selected = dialog.selected()
        assert selected is not None
        assert selected[0] == "1.2.0"
        assert selected[1] == "v1.2.0"
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_play_button_style_is_green() -> None:
    from sailwind_mod_sync.ui.main_window import PLAY_BUTTON_STYLE

    assert "#2e7d32" in PLAY_BUTTON_STYLE
    assert "color: white" in PLAY_BUTTON_STYLE


def _sample_update(*, installable: bool) -> AppUpdate:
    return AppUpdate(
        version="0.2.0",
        version_raw="v0.2.0",
        tag="v0.2.0",
        html_url="https://github.com/foxyv/SailwindModSynchronizer/releases/tag/v0.2.0",
        notes="Bug fixes",
        asset_name="SailwindModSynchronizer-0.2.0-windows.zip",
        download_url="https://github.com/foxyv/SailwindModSynchronizer/releases/download/v0.2.0/app.zip",
        installable=installable,
    )


def test_update_dialog_installable_buttons() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = UpdateDialog(_sample_update(installable=True))
    try:
        labels = [button.text() for button in dialog.findChildren(QPushButton)]
        assert "Update" in labels
        assert "Skip this version" in labels
        assert "Later" in labels
        assert "Open GitHub" not in labels
        update_btn = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Update")
        update_btn.click()
        assert dialog.choice() == UPDATE
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_update_dialog_opens_github_when_not_installable() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = UpdateDialog(_sample_update(installable=False))
    try:
        labels = [button.text() for button in dialog.findChildren(QPushButton)]
        assert "Open GitHub" in labels
        assert "Update" not in labels
        open_btn = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Open GitHub")
        open_btn.click()
        assert dialog.choice() == OPEN
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_update_dialog_skip_choice() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = UpdateDialog(_sample_update(installable=True))
    try:
        skip = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Skip this version")
        skip.click()
        assert dialog.choice() == SKIP
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_settings_has_update_checkbox(paths: AppPaths) -> None:
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(AppConfig(check_for_updates=False), paths)
    try:
        assert not dialog.check_updates.isChecked()
        dialog.check_updates.setChecked(True)
        config = AppConfig(check_for_updates=False)
        dialog.apply_to(config)
        assert config.check_for_updates is True
    finally:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


def test_help_menu_has_check_for_updates(paths: AppPaths) -> None:
    from sailwind_mod_sync.http_util import HttpClient
    from sailwind_mod_sync.manager import Manager
    from sailwind_mod_sync.ui.main_window import MainWindow

    class _NoHttp(HttpClient):
        def __init__(self) -> None:
            self.token = ""
            self._owns_client = False
            self._client = None

        def close(self) -> None:
            return None

    app = QApplication.instance() or QApplication([])
    manager = Manager(paths=paths, config=AppConfig(check_for_updates=False), http=_NoHttp())
    manager.catalog = [
        CatalogEntry(
            repo="https://github.com/example/mod",
            guids=["com.example.mod"],
            primary_guid="com.example.mod",
            name="mod",
            latest_raw="v1.0.0",
            latest_version="1.0.0",
            available=True,
        )
    ]
    window = MainWindow(manager)
    try:
        help_menu = next(
            action.menu()
            for action in window.menuBar().actions()
            if action.menu() and action.menu().title().replace("&", "") == "Help"
        )
        items = [action.text().replace("&", "") for action in help_menu.actions()]
        assert "Check for updates…" in items
        assert "About" in items
        assert window.windowTitle().startswith("Sailwind Mod Synchronizer")
    finally:
        window.close()
        window.deleteLater()
        manager.close()
    app.processEvents()

