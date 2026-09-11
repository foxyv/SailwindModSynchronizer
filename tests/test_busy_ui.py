from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QHeaderView, QLabel, QPushButton, QTableWidget

from sailwind_mod_sync.models import CatalogEntry, LibraryEntry, ArtifactMeta, ModDetails, PinnedMod
from sailwind_mod_sync.ui.catalog_view import CatalogView, catalog_library_button
from sailwind_mod_sync.ui.library_view import LibraryView
from sailwind_mod_sync.ui.mod_details_dialog import ModDetailsDialog
from sailwind_mod_sync.ui.links import repo_button
from sailwind_mod_sync.ui.missing_mods_dialog import MissingModsWarningDialog
from sailwind_mod_sync.ui.progress_dialog import BusyDialog
from sailwind_mod_sync.ui.tables import enable_column_resize


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
