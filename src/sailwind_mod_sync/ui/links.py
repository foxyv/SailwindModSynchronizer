from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QPushButton, QWidget

from sailwind_mod_sync.catalog.github import repo_page_url


def repo_button(repo: str, parent: QWidget | None = None) -> QPushButton:
    page = repo_page_url(repo)
    label = "GitLab" if page and "gitlab.com" in page.lower() else "GitHub"
    button = QPushButton(label, parent)
    if not page:
        button.setEnabled(False)
        button.setToolTip("No repository URL")
        return button
    button.setToolTip(page)
    button.clicked.connect(lambda _=False, url=page: QDesktopServices.openUrl(QUrl(url)))
    return button


def repo_or_find_button(
    repo: str,
    parent: QWidget | None,
    on_find: Callable[[], None],
) -> QPushButton:
    page = repo_page_url(repo)
    if page:
        return repo_button(repo, parent)
    button = QPushButton("Associate", parent)
    button.setToolTip("Link this local plugin to a GitHub catalog entry, or paste a repository URL")
    button.clicked.connect(lambda _=False: on_find())
    return button
