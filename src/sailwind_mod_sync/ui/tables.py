from __future__ import annotations

from PySide6.QtWidgets import QHeaderView, QTableWidget


def enable_column_resize(table: QTableWidget, widths: list[int] | None = None) -> None:
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(36)
    if widths:
        for index, width in enumerate(widths):
            if index < table.columnCount():
                table.setColumnWidth(index, width)
