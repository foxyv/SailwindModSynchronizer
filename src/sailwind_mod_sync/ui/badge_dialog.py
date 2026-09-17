from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sailwind_mod_sync.models import PackBadge
from sailwind_mod_sync.packs.badges import (
    COLOR_ROLE_LABELS,
    COLOR_ROLES,
    ICON_SCALE_MAX,
    ICON_SCALE_MIN,
    SHAPES,
    SYMBOLS,
    clamp_rgb,
    clamp_scale,
    encode_custom_image,
    normalize_badge,
    random_badge,
    render_badge,
    shape_label,
    symbol_label,
)

IMAGE_FILTERS = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.ico);;All files (*.*)"


class RgbRow(QWidget):
    changed = Signal(object)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.swatch = QToolButton()
        self.swatch.setFixedSize(36, 36)
        self.swatch.setAutoRaise(True)
        self.swatch.setToolTip("Choose color")
        self.swatch.clicked.connect(self._pick)
        self.spins: list[QSpinBox] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        name = QLabel(title)
        name.setMinimumWidth(88)
        layout.addWidget(name)
        layout.addWidget(self.swatch)
        for channel in ("R", "G", "B"):
            label = QLabel(channel)
            spin = QSpinBox()
            spin.setRange(0, 255)
            spin.setMaximumWidth(72)
            spin.valueChanged.connect(self._spin_changed)
            self.spins.append(spin)
            layout.addWidget(label)
            layout.addWidget(spin)
        layout.addStretch(1)
        self.set_rgb((0, 0, 0))

    def rgb(self) -> tuple[int, int, int]:
        return (self.spins[0].value(), self.spins[1].value(), self.spins[2].value())

    def set_rgb(self, rgb: tuple[int, int, int]) -> None:
        red, green, blue = clamp_rgb(rgb)
        for spin, value in zip(self.spins, (red, green, blue), strict=True):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._paint_swatch()

    def _spin_changed(self) -> None:
        self._paint_swatch()
        self.changed.emit(self.rgb())

    def _pick(self) -> None:
        dialog = QColorDialog(QColor(*self.rgb()), self)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setWindowTitle("Choose color")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        if not color.isValid():
            return
        rgb = (color.red(), color.green(), color.blue())
        self.set_rgb(rgb)
        self.changed.emit(rgb)

    def _paint_swatch(self) -> None:
        rgb = self.rgb()
        self.swatch.setIcon(_swatch_icon(rgb, size=28))
        self.swatch.setToolTip(f"{rgb[0]}, {rgb[1]}, {rgb[2]}")


class BadgePickerDialog(QDialog):
    def __init__(
        self,
        badge: PackBadge | None,
        parent: QWidget | None = None,
        seed: str = "",
        pack=None,  # noqa: ANN001
        name: str = "",
    ) -> None:
        del pack
        super().__init__(parent)
        self.setWindowTitle("Edit ModPack")
        self.resize(520, 600)
        self._seed = seed
        self.badge = normalize_badge(badge or random_badge())

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(96, 96)
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("ModPack name")
        self.caption = QLabel()
        self.caption.setWordWrap(True)

        title = QVBoxLayout()
        title.addWidget(self.name_edit)
        title.addWidget(self.caption)
        header = QHBoxLayout()
        header.addWidget(self.preview)
        header.addLayout(title, 1)

        self._shape_group, shape_host = self._choice_grid(
            [shape_label(index) for index in range(len(SHAPES))],
            columns=8,
            icon_size=40,
            on_pick=self._set_shape,
        )
        self._icon_group, icon_host = self._choice_grid(
            [symbol_label(index) for index in range(len(SYMBOLS))],
            columns=7,
            icon_size=36,
            on_pick=self._set_icon,
        )
        icon_scroll = QScrollArea()
        icon_scroll.setWidgetResizable(True)
        icon_scroll.setWidget(icon_host)
        icon_scroll.setMinimumHeight(160)

        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(ICON_SCALE_MIN, ICON_SCALE_MAX)
        self.scale_slider.setPageStep(5)
        self.scale_slider.valueChanged.connect(self._set_scale)
        self.scale_value = QLabel()
        self.scale_value.setMinimumWidth(36)
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Size"))
        scale_row.addWidget(self.scale_slider, 1)
        scale_row.addWidget(self.scale_value)

        self._color_rows: dict[str, RgbRow] = {}
        colors = QVBoxLayout()
        colors.setSpacing(6)
        for role, label in zip(COLOR_ROLES, COLOR_ROLE_LABELS, strict=True):
            row = RgbRow(label)
            row.changed.connect(lambda rgb, key=role: self._set_rgb(key, rgb))
            self._color_rows[role] = row
            colors.addWidget(row)

        randomize = QPushButton("Randomize")
        randomize.setAutoDefault(False)
        randomize.clicked.connect(self._randomize)
        choose = QPushButton("Choose image…")
        choose.setAutoDefault(False)
        choose.clicked.connect(self._choose_image)
        actions = QHBoxLayout()
        actions.addWidget(randomize)
        actions.addWidget(choose)
        actions.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self._section_label("Border"))
        layout.addWidget(shape_host)
        layout.addWidget(self._section_label("Icon"))
        layout.addWidget(icon_scroll, 1)
        layout.addLayout(scale_row)
        layout.addWidget(self._section_label("Colors"))
        layout.addLayout(colors)
        layout.addLayout(actions)
        layout.addWidget(buttons)
        self._refresh()

    @property
    def pack_name(self) -> str:
        return self.name_edit.text().strip()

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def accept(self) -> None:
        if not self.pack_name:
            QMessageBox.warning(self, "Name required", "Enter a name for this ModPack.")
            self.name_edit.setFocus()
            return
        super().accept()

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: 600;")
        return label

    def _choice_grid(
        self,
        labels: list[str],
        *,
        columns: int,
        icon_size: int,
        on_pick,
    ) -> tuple[QButtonGroup, QWidget]:
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        group = QButtonGroup(host)
        group.setExclusive(True)
        for index, label in enumerate(labels):
            button = QToolButton()
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setIconSize(QSize(icon_size, icon_size))
            button.setToolTip(label)
            group.addButton(button, index)
            grid.addWidget(button, index // columns, index % columns)
        group.idClicked.connect(on_pick)
        host.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        return group, host

    def _set_shape(self, index: int) -> None:
        self.badge = replace(self.badge, shape=index, png="")
        self._refresh()

    def _set_icon(self, index: int) -> None:
        self.badge = replace(self.badge, icon=index, png="")
        self._refresh()

    def _set_rgb(self, role: str, rgb: tuple[int, int, int]) -> None:
        if role not in COLOR_ROLES:
            return
        self.badge = replace(self.badge, png="", **{role: clamp_rgb(rgb)})
        self._refresh()

    def _set_scale(self, value: int) -> None:
        self.badge = replace(self.badge, scale=clamp_scale(value), png="")
        self._refresh()

    def _randomize(self) -> None:
        self.badge = random_badge()
        self._refresh()

    def _choose_image(self) -> None:
        path = self._pick_image_path()
        if not path:
            return
        try:
            png = encode_custom_image(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Could not read image", str(exc))
            return
        self.badge = replace(self.badge, png=png)
        self._refresh()

    def _pick_image_path(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose image",
            "",
            IMAGE_FILTERS,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        return path

    def _refresh(self) -> None:
        self.badge = normalize_badge(self.badge)
        self.preview.setPixmap(render_badge(self.badge, 96, seed=self._seed))
        if self.badge.png:
            self.caption.setText("Custom image")
        else:
            self.caption.setText(f"{shape_label(self.badge.shape)} · {symbol_label(self.badge.icon)}")
        self._sync_group(self._shape_group, self.badge.shape)
        self._sync_group(self._icon_group, self.badge.icon)
        for index, button in self._indexed_buttons(self._shape_group):
            preview = replace(self.badge, shape=index, png="")
            button.setIcon(QIcon(render_badge(preview, 40)))
        for index, button in self._indexed_buttons(self._icon_group):
            preview = replace(self.badge, icon=index, png="")
            button.setIcon(QIcon(render_badge(preview, 36)))
        for role, row in self._color_rows.items():
            row.blockSignals(True)
            row.set_rgb(getattr(self.badge, role))
            row.blockSignals(False)
        self.scale_slider.blockSignals(True)
        self.scale_slider.setValue(self.badge.scale)
        self.scale_slider.blockSignals(False)
        self.scale_value.setText(f"{self.badge.scale}%")

    def _sync_group(self, group: QButtonGroup, index: int) -> None:
        button = group.button(index)
        if button is not None and not button.isChecked():
            button.setChecked(True)

    def _indexed_buttons(self, group: QButtonGroup) -> list[tuple[int, QToolButton]]:
        items: list[tuple[int, QToolButton]] = []
        for button in group.buttons():
            ident = group.id(button)
            if ident >= 0:
                items.append((ident, button))
        items.sort(key=lambda item: item[0])
        return items


def _swatch_icon(rgb: tuple[int, int, int], *, size: int = 18) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(*clamp_rgb(rgb)))
    painter = QPainter(pixmap)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#111111"), 1))
    painter.drawRect(0, 0, size - 1, size - 1)
    painter.end()
    return QIcon(pixmap)
