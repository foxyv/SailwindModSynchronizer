from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.catalog.github import repo_page_url
from sailwind_mod_sync.http_util import ProgressFn
from sailwind_mod_sync.models import ModDetails, RemoteModInfo
from sailwind_mod_sync.ui.library_view import format_size
from sailwind_mod_sync.ui.workers import TaskBridge, run_background


class ModDetailsDialog(QDialog):
    def __init__(
        self,
        details: ModDetails,
        parent: QWidget | None = None,
        cached_readme: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._closed = False
        self._bridge: TaskBridge | None = None
        self._have_readme = bool((cached_readme or "").strip())
        self.setWindowTitle(details.name or details.guid)
        self.resize(760, 680)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(4)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow("Name", _selectable(details.name or details.guid))
        form.addRow("GUID", _selectable(details.guid))
        form.addRow("This version", _selectable(details.version))
        form.addRow("Repository", _repo_row(details.repo))
        _add_detail_row(form, "Source", details.source_url)
        _add_detail_row(form, "File", details.filename)
        _add_detail_row(
            form,
            "Size",
            format_size(details.size_bytes) if details.size_bytes else "",
        )
        _add_detail_row(form, "SHA-256", details.sha256)
        _add_detail_row(form, "Downloaded", details.downloaded_at)
        folders = ", ".join(details.plugin_folders) if details.plugin_folders else ""
        _add_detail_row(form, "Plugin folders", folders)
        installed = _format_installed(details.installed_versions, details.version)
        _add_detail_row(form, "In library", installed if details.installed_versions else "")
        form.addRow("Catalog latest", _selectable(details.catalog_latest or "Not in catalog"))
        self.latest_release = _selectable("Checking…" if details.repo else "No repository URL")
        form.addRow("Latest release", self.latest_release)
        self.available = _selectable("Checking…" if details.repo else "—")
        form.addRow("Available releases", self.available)
        form.addRow("In packs", _selectable(_format_packs(details.pack_pins)))

        self.status = QLabel(
            "" if details.repo else "No repository URL. Use Add Repository, then open details again."
        )
        self.status.setWordWrap(True)
        self.status.setVisible(bool(self.status.text().strip()))

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        header_layout.addLayout(form)
        header_layout.addWidget(self.status)

        self.header_scroll = QScrollArea()
        self.header_scroll.setWidgetResizable(True)
        self.header_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.header_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.header_scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.header_scroll.setWidget(header)
        self.header_scroll.setMinimumHeight(72)

        self.readme = QTextBrowser()
        self.readme.setOpenExternalLinks(True)
        if self._have_readme:
            _set_readme(self.readme, cached_readme or "")
        elif details.repo:
            self.readme.setPlainText("Loading README…")
        else:
            self.readme.setPlainText("No README to load until a GitHub or GitLab URL is saved for this mod.")

        readme_label = QLabel("README")
        readme_label.setStyleSheet("font-weight: 600;")
        readme_pane = QWidget()
        readme_layout = QVBoxLayout(readme_pane)
        readme_layout.setContentsMargins(0, 0, 0, 0)
        readme_layout.setSpacing(4)
        readme_layout.addWidget(readme_label)
        readme_layout.addWidget(self.readme, 1)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.header_scroll)
        self.splitter.addWidget(readme_pane)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([140, 520])

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter, 1)
        layout.addWidget(buttons)

    def start_remote(self, fetch: Callable[[ProgressFn], object]) -> None:
        bridge = TaskBridge(self)
        self._bridge = bridge
        queued = Qt.ConnectionType.QueuedConnection
        bridge.progress.connect(self._on_progress, queued)
        bridge.finished.connect(self._on_remote, queued)
        bridge.failed.connect(self._on_remote_fail, queued)
        run_background(fetch, bridge)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._closed = True
        super().closeEvent(event)

    @Slot(str)
    def _on_progress(self, message: str) -> None:
        if self._closed:
            return
        self._set_status(message)

    @Slot(object)
    def _on_remote(self, result: object) -> None:
        if self._closed:
            return
        info = result if isinstance(result, RemoteModInfo) else RemoteModInfo()
        self._set_status("")
        if info.latest_tag:
            self.latest_release.setText(info.latest_tag)
        elif info.releases_error:
            self.latest_release.setText(info.releases_error)
        else:
            self.latest_release.setText("No releases found")
        if info.release_tags:
            self.available.setText(", ".join(info.release_tags))
        elif info.releases_error:
            self.available.setText(info.releases_error)
        else:
            self.available.setText("—")
        if info.readme:
            _set_readme(self.readme, info.readme)
            self._have_readme = True
        elif not self._have_readme:
            if info.readme_error:
                self.readme.setPlainText(f"Could not load README.\n\n{info.readme_error}")
            else:
                self.readme.setPlainText("This repository has no README.")

    @Slot(str)
    def _on_remote_fail(self, message: str) -> None:
        if self._closed:
            return
        self._set_status("")
        self.latest_release.setText(message)
        self.available.setText(message)
        if not self._have_readme:
            self.readme.setPlainText(f"Could not load remote details.\n\n{message}")

    def _set_status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setVisible(bool((text or "").strip()))


def _add_detail_row(form: QFormLayout, title: str, value: str) -> None:
    text = (value or "").strip()
    if not text:
        return
    form.addRow(title, _selectable(text))


def _selectable(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    return label


def _repo_row(repo: str) -> QWidget:
    page = repo_page_url(repo)
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(_selectable(page or repo or "—"), 1)
    if page:
        button = QPushButton("Open")
        button.clicked.connect(lambda _=False, url=page: QDesktopServices.openUrl(QUrl(url)))
        layout.addWidget(button)
    return row


def _format_installed(versions: list[str], current: str) -> str:
    if not versions:
        return "—"
    parts: list[str] = []
    for version in versions:
        if version == current:
            parts.append(f"{version} (this row)")
        else:
            parts.append(version)
    return ", ".join(parts)


def _format_packs(pins: list[tuple[str, str]]) -> str:
    if not pins:
        return "Not in any pack"
    return ", ".join(f"{name} ({version})" for name, version in pins)


def _set_readme(browser: QTextBrowser, text: str) -> None:
    stripped = text.lstrip()
    if stripped[:32].lower().startswith("<"):
        browser.setHtml(text)
        return
    set_markdown = getattr(browser, "setMarkdown", None)
    if callable(set_markdown):
        set_markdown(text)
        return
    browser.setPlainText(text)
