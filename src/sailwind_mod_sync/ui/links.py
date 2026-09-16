from __future__ import annotations

import html
import re
from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QPushButton, QWidget

from sailwind_mod_sync.catalog.github import repo_page_url

_HTTP_URL_RE = re.compile(r"https://[^\s<>]+")


def help_text_to_html(text: str) -> str:
    """Escape help text and turn https URLs into clickable links."""
    raw = text or ""
    parts: list[str] = []
    last = 0
    for match in _HTTP_URL_RE.finditer(raw):
        parts.append(html.escape(raw[last:match.start()]).replace("\n", "<br>\n"))
        full = match.group(0)
        url = full.rstrip(".,);]")
        safe = html.escape(url, quote=True)
        parts.append(f'<a href="{safe}">{html.escape(url)}</a>')
        if len(full) > len(url):
            parts.append(html.escape(full[len(url):]))
        last = match.end()
    parts.append(html.escape(raw[last:]).replace("\n", "<br>\n"))
    return "".join(parts)


def repo_button(repo: str, parent: QWidget | None = None) -> QPushButton:
    page = repo_page_url(repo)
    label = "Open GitLab in Browser" if page and "gitlab.com" in page.lower() else "Open GitHub in Browser"
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
    button = QPushButton("Add Repository", parent)
    button.setToolTip("Add a GitHub or GitLab repository URL, or pick a catalog entry")
    button.clicked.connect(lambda _=False: on_find())
    return button
