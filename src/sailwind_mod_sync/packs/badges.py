from __future__ import annotations

import base64
import hashlib
import math
import random
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap

from sailwind_mod_sync.models import PackBadge

SHAPES = (
    "circle",
    "rounded_square",
    "shield",
    "hexagon",
    "diamond",
    "banner",
    "pentagon",
    "octagon",
)

SYMBOLS = (
    "anchor",
    "helm",
    "compass",
    "sail",
    "lighthouse",
    "whale",
    "fish",
    "wave",
    "starfish",
    "spyglass",
    "lantern",
    "flag",
    "gull",
    "trident",
    "shell",
    "buoy",
    "lifering",
    "moon",
    "sun",
    "harpoon",
    "barrel",
    "chest",
    "bottle",
    "map",
    "knot",
    "cannon",
    "sextant",
    "kraken",
)

SHAPE_LABELS = (
    "Circle",
    "Rounded square",
    "Shield",
    "Hexagon",
    "Diamond",
    "Banner",
    "Pentagon",
    "Octagon",
)

SYMBOL_LABELS = (
    "Anchor",
    "Ship's wheel",
    "Compass",
    "Sail",
    "Lighthouse",
    "Whale",
    "Fish",
    "Swell",
    "Starfish",
    "Spyglass",
    "Lantern",
    "House flag",
    "Gull",
    "Trident",
    "Shell",
    "Buoy",
    "Life ring",
    "Moon",
    "Sun",
    "Harpoon",
    "Barrel",
    "Chest",
    "Bottle",
    "Chart",
    "Knot",
    "Cannon",
    "Sextant",
    "Kraken",
)

_LEGACY_HEX = (
    "#001219",
    "#005f73",
    "#0a9396",
    "#94d2bd",
    "#e9d8a6",
    "#ee9b00",
    "#ca6702",
    "#bb3e03",
    "#ae2012",
    "#9b2226",
    "#16324f",
    "#1b6b93",
    "#274c77",
    "#3d5a80",
    "#98c1d9",
    "#e8c547",
    "#f4efe8",
    "#e36414",
    "#1d3557",
    "#a8dadc",
    "#2c6e49",
    "#d4a373",
    "#14213d",
    "#fca311",
    "#540b0e",
    "#f6bd60",
    "#22223b",
    "#c9ada7",
    "#283618",
    "#dda15e",
    "#4a5759",
    "#b7e4c7",
    "#0f4c5c",
    "#ee6c4d",
    "#e7ecef",
    "#023e8a",
    "#90e0ef",
)

COLOR_ROLES = ("edge", "fill", "mark", "ink")
COLOR_ROLE_LABELS = ("Edge", "Background", "Icon", "Accent")
ICON_SCALE_DEFAULT = 56
ICON_SCALE_MIN = 20
ICON_SCALE_MAX = 100
INK_LIGHT = (244, 239, 232)
INK_DARK = (18, 28, 42)
CUSTOM_BADGE_SIZE = 128


@dataclass(frozen=True)
class _LegacyBuiltin:
    id: str
    shape: str
    color: str
    accent: str
    symbol: str


_LEGACY_BUILTINS: tuple[_LegacyBuiltin, ...] = (
    _LegacyBuiltin("anchor", "shield", "#16324f", "#e8c547", "anchor"),
    _LegacyBuiltin("helm", "circle", "#1b6b93", "#f4efe8", "helm"),
    _LegacyBuiltin("compass", "octagon", "#274c77", "#e7ecef", "compass"),
    _LegacyBuiltin("sail", "banner", "#023e8a", "#90e0ef", "sail"),
    _LegacyBuiltin("lighthouse", "rounded_square", "#9b2226", "#e9d8a6", "lighthouse"),
    _LegacyBuiltin("whale", "pentagon", "#001219", "#0a9396", "whale"),
    _LegacyBuiltin("fish", "diamond", "#005f73", "#94d2bd", "fish"),
    _LegacyBuiltin("wave", "hexagon", "#1d3557", "#a8dadc", "wave"),
    _LegacyBuiltin("starfish", "circle", "#e36414", "#f4efe8", "starfish"),
    _LegacyBuiltin("spyglass", "rounded_square", "#3d5a80", "#ee6c4d", "spyglass"),
    _LegacyBuiltin("lantern", "banner", "#14213d", "#fca311", "lantern"),
    _LegacyBuiltin("flag", "shield", "#540b0e", "#f6bd60", "flag"),
    _LegacyBuiltin("gull", "pentagon", "#274c77", "#a8dadc", "gull"),
    _LegacyBuiltin("trident", "diamond", "#0f4c5c", "#e8c547", "trident"),
    _LegacyBuiltin("shell", "circle", "#dda15e", "#283618", "shell"),
    _LegacyBuiltin("buoy", "hexagon", "#9b2226", "#f4efe8", "buoy"),
    _LegacyBuiltin("lifering", "circle", "#9b2226", "#f4efe8", "lifering"),
    _LegacyBuiltin("moon", "pentagon", "#22223b", "#c9ada7", "moon"),
    _LegacyBuiltin("sun", "octagon", "#fca311", "#14213d", "sun"),
    _LegacyBuiltin("harpoon", "banner", "#4a5759", "#b7e4c7", "harpoon"),
    _LegacyBuiltin("barrel", "rounded_square", "#283618", "#dda15e", "barrel"),
    _LegacyBuiltin("chest", "shield", "#e8c547", "#16324f", "chest"),
    _LegacyBuiltin("bottle", "hexagon", "#2c6e49", "#e9d8a6", "bottle"),
    _LegacyBuiltin("chart", "octagon", "#1b6b93", "#e8c547", "map"),
    _LegacyBuiltin("knot", "circle", "#3d5a80", "#f4efe8", "knot"),
    _LegacyBuiltin("cannon", "banner", "#14213d", "#c9ada7", "cannon"),
    _LegacyBuiltin("sextant", "diamond", "#005f73", "#e8c547", "sextant"),
    _LegacyBuiltin("kraken", "pentagon", "#001219", "#ee6c4d", "kraken"),
    _LegacyBuiltin("albatross", "hexagon", "#023e8a", "#f4efe8", "gull"),
    _LegacyBuiltin("northstar", "octagon", "#16324f", "#90e0ef", "compass"),
)


def clamp_index(value: object, count: int) -> int:
    if count <= 0:
        return 0
    try:
        index = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if index < 0:
        return 0
    if index >= count:
        return count - 1
    return index


def shape_key(index: int) -> str:
    return SHAPES[clamp_index(index, len(SHAPES))]


def symbol_key(index: int) -> str:
    return SYMBOLS[clamp_index(index, len(SYMBOLS))]


def color_hex(rgb: tuple[int, int, int]) -> str:
    red, green, blue = clamp_rgb(rgb)
    return f"#{red:02x}{green:02x}{blue:02x}"


def clamp_byte(value: object, default: int = 0) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0, min(255, number))


def clamp_rgb(value: object, default: tuple[int, int, int] = (0, 0, 0)) -> tuple[int, int, int]:
    parsed = parse_rgb(value)
    if parsed is None:
        return default
    return parsed


def parse_rgb(value: object) -> tuple[int, int, int] | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (clamp_byte(value[0]), clamp_byte(value[1]), clamp_byte(value[2]))
    if isinstance(value, int):
        if 0 <= value < len(_LEGACY_HEX):
            return _rgb(_LEGACY_HEX[value])
        return ((value >> 16) & 255, (value >> 8) & 255, value & 255)
    text = str(value or "").strip()
    if not text:
        return None
    if text.lstrip("-").isdigit():
        return parse_rgb(_as_int(text))
    return _rgb(text)


def shape_label(index: int) -> str:
    return SHAPE_LABELS[clamp_index(index, len(SHAPE_LABELS))]


def symbol_label(index: int) -> str:
    return SYMBOL_LABELS[clamp_index(index, len(SYMBOL_LABELS))]


def clamp_scale(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ICON_SCALE_DEFAULT
    return max(ICON_SCALE_MIN, min(ICON_SCALE_MAX, number))


def _luma(rgb: tuple[int, int, int]) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _rgb_differ(left: tuple[int, int, int], right: tuple[int, int, int]) -> bool:
    return (left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2 + (left[2] - right[2]) ** 2 > 6400


def default_ink(mark: tuple[int, int, int], fill: tuple[int, int, int]) -> tuple[int, int, int]:
    ink = INK_DARK if _luma(mark) >= 160 else INK_LIGHT
    if not _rgb_differ(ink, fill):
        ink = INK_LIGHT if ink == INK_DARK else INK_DARK
    if not _rgb_differ(ink, mark):
        return (255 - mark[0], 255 - mark[1], 255 - mark[2])
    return ink


def normalize_badge(badge: PackBadge) -> PackBadge:
    fill = clamp_rgb(badge.fill, (22, 50, 79))
    mark = clamp_rgb(badge.mark, (232, 197, 71))
    return PackBadge(
        shape=clamp_index(badge.shape, len(SHAPES)),
        icon=clamp_index(badge.icon, len(SYMBOLS)),
        edge=clamp_rgb(badge.edge, (232, 197, 71)),
        fill=fill,
        mark=mark,
        ink=clamp_rgb(badge.ink, default_ink(mark, fill)),
        scale=clamp_scale(badge.scale),
        png=str(badge.png or "").strip(),
    )


def random_badge(rng: random.Random | None = None) -> PackBadge:
    picker = rng or random.Random()
    palette = [_rgb(item) for item in _LEGACY_HEX]
    fill = picker.choice(palette)
    others = [item for item in palette if item != fill] or [fill]
    mark = picker.choice(others)
    ink_choices = [item for item in others if item != mark] or others
    return PackBadge(
        shape=picker.randrange(len(SHAPES)),
        icon=picker.randrange(len(SYMBOLS)),
        edge=picker.choice(others),
        fill=fill,
        mark=mark,
        ink=picker.choice(ink_choices),
        scale=picker.randint(ICON_SCALE_MIN, ICON_SCALE_MAX),
    )


def badge_for_seed(seed: str) -> PackBadge:
    digest = hashlib.sha256((seed or "pack").encode("utf-8")).digest()
    fill = (digest[5], digest[6], digest[7])
    mark = (digest[8], digest[9], digest[10])
    return PackBadge(
        shape=digest[0] % len(SHAPES),
        icon=digest[1] % len(SYMBOLS),
        edge=(digest[2], digest[3], digest[4]),
        fill=fill,
        mark=mark,
        ink=(digest[12], digest[13], digest[14]),
        scale=ICON_SCALE_MIN + digest[11] % (ICON_SCALE_MAX - ICON_SCALE_MIN + 1),
    )


def resolve_badge(badge: PackBadge | None, seed: str = "") -> PackBadge:
    if badge is None:
        return badge_for_seed(seed)
    return normalize_badge(badge)


def badge_from_payload(data: object) -> PackBadge | None:
    if isinstance(data, (list, tuple)):
        if len(data) >= 14:
            fill = (clamp_byte(data[5]), clamp_byte(data[6]), clamp_byte(data[7]))
            mark = (clamp_byte(data[8]), clamp_byte(data[9]), clamp_byte(data[10]))
            return normalize_badge(
                PackBadge(
                    shape=_as_int(data[0]),
                    icon=_as_int(data[1]),
                    edge=(clamp_byte(data[2]), clamp_byte(data[3]), clamp_byte(data[4])),
                    fill=fill,
                    mark=mark,
                    ink=(clamp_byte(data[11]), clamp_byte(data[12]), clamp_byte(data[13])),
                    scale=clamp_scale(data[14]) if len(data) >= 15 else ICON_SCALE_DEFAULT,
                )
            )
        if len(data) >= 11:
            fill = (clamp_byte(data[5]), clamp_byte(data[6]), clamp_byte(data[7]))
            mark = (clamp_byte(data[8]), clamp_byte(data[9]), clamp_byte(data[10]))
            return normalize_badge(
                PackBadge(
                    shape=_as_int(data[0]),
                    icon=_as_int(data[1]),
                    edge=(clamp_byte(data[2]), clamp_byte(data[3]), clamp_byte(data[4])),
                    fill=fill,
                    mark=mark,
                    ink=default_ink(mark, fill),
                    scale=clamp_scale(data[11]) if len(data) >= 12 else ICON_SCALE_DEFAULT,
                )
            )
        if len(data) < 5:
            return None
        fill = clamp_rgb(data[3])
        mark = clamp_rgb(data[4])
        return normalize_badge(
            PackBadge(
                shape=_as_int(data[0]),
                icon=_as_int(data[1]),
                edge=clamp_rgb(data[2]),
                fill=fill,
                mark=mark,
                ink=clamp_rgb(data[5]) if len(data) >= 6 else default_ink(mark, fill),
            )
        )
    if not isinstance(data, dict):
        return None
    kind = str(data.get("kind") or "").strip().lower()
    png = str(data.get("png") or "").strip()
    has_png = bool(png and decode_custom_image(png) is not None)
    if kind == "custom":
        if not has_png:
            return None
        return normalize_badge(PackBadge(png=png))
    if kind == "builtin":
        return _from_legacy_builtin(str(data.get("id") or data.get("builtin_id") or ""))
    if kind and kind != "generated":
        return None
    keys = ("shape", "icon", "symbol", "edge", "fill", "mark", "ink", "color", "accent", "scale", "png")
    if not any(data.get(key) not in (None, "") for key in keys):
        return None
    accent = data.get("accent")
    fill = parse_rgb(data["fill"] if "fill" in data else data.get("color")) or (22, 50, 79)
    mark = parse_rgb(
        data["mark"] if "mark" in data else (accent if accent not in (None, "") else data.get("color"))
    ) or (232, 197, 71)
    return normalize_badge(
        PackBadge(
            shape=_name_or_index(data.get("shape"), SHAPES, aliases={"scallop": "pentagon"}),
            icon=_name_or_index(data.get("icon", data.get("symbol")), SYMBOLS),
            edge=parse_rgb(data["edge"] if "edge" in data else accent) or (232, 197, 71),
            fill=fill,
            mark=mark,
            ink=parse_rgb(data["ink"]) if "ink" in data else default_ink(mark, fill),
            scale=clamp_scale(data["scale"]) if "scale" in data else ICON_SCALE_DEFAULT,
            png=png if has_png else "",
        )
    )


def _from_legacy_builtin(badge_id: str) -> PackBadge | None:
    wanted = (badge_id or "").strip().lower()
    for item in _LEGACY_BUILTINS:
        if item.id == wanted:
            fill = parse_rgb(item.color) or (22, 50, 79)
            mark = parse_rgb(item.accent) or (232, 197, 71)
            return normalize_badge(
                PackBadge(
                    shape=_name_or_index(item.shape, SHAPES),
                    icon=_name_or_index(item.symbol, SYMBOLS),
                    edge=parse_rgb(item.accent) or (232, 197, 71),
                    fill=fill,
                    mark=mark,
                    ink=default_ink(mark, fill),
                )
            )
    return None


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _name_or_index(
    value: object,
    names: tuple[str, ...],
    aliases: dict[str, str] | None = None,
) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if text.lstrip("-").isdigit():
        return _as_int(text)
    wanted = text.lower()
    if aliases:
        wanted = aliases.get(wanted, wanted)
    for index, name in enumerate(names):
        if name == wanted:
            return index
    return 0


def _rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6:
        return (0, 0, 0)
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return (0, 0, 0)


def encode_custom_image(path: Path | str, max_px: int = CUSTOM_BADGE_SIZE) -> str:
    source = Path(path)
    image = QImage(str(source))
    if image.isNull():
        raise ValueError(f"Could not read image: {source}")
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    side = min(image.width(), image.height())
    if side <= 0:
        raise ValueError(f"Could not read image: {source}")
    x = (image.width() - side) // 2
    y = (image.height() - side) // 2
    square = image.copy(x, y, side, side)
    scaled = square.scaled(max_px, max_px, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not scaled.save(buffer, "PNG"):
        raise ValueError("Could not encode image")
    return base64.b64encode(bytes(buffer.data())).decode("ascii")


def decode_custom_image(png: str) -> QImage | None:
    text = (png or "").strip()
    if not text:
        return None
    if text.lower().startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    try:
        raw = base64.b64decode(text, validate=False)
    except (ValueError, TypeError):
        return None
    if not raw:
        return None
    image = QImage.fromData(raw)
    if image.isNull():
        return None
    return image


def render_badge(badge: PackBadge | None, logical_px: int, device_pixel_ratio: float = 1.0, seed: str = "") -> QPixmap:
    dpr = max(1.0, float(device_pixel_ratio) or 1.0)
    phys = max(16, int(round(logical_px * dpr)))
    if badge is not None and badge.png:
        custom = _paint_custom(badge.png, phys)
        if custom is not None:
            pixmap = QPixmap.fromImage(custom)
            pixmap.setDevicePixelRatio(dpr)
            return pixmap
    resolved = resolve_badge(badge, seed)
    image = QImage(phys, phys, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _paint_generated(painter, QRectF(0, 0, phys, phys), resolved)
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def _paint_custom(png: str, phys: int) -> QImage | None:
    source = decode_custom_image(png)
    if source is None:
        return None
    scaled = source.scaled(phys, phys, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    canvas = QImage(phys, phys, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage((phys - scaled.width()) // 2, (phys - scaled.height()) // 2, scaled)
    painter.end()
    return canvas


def _paint_generated(painter: QPainter, rect: QRectF, badge: PackBadge) -> None:
    fill = QColor(*badge.fill)
    edge = QColor(*badge.edge)
    mark = QColor(*badge.mark)
    ink = QColor(*badge.ink)
    if not _colors_differ(mark, ink):
        ink = QColor(*default_ink(badge.mark, badge.fill))
    path = _shape_path(shape_key(badge.shape), rect.adjusted(1.5, 1.5, -1.5, -1.5))
    painter.setPen(QPen(edge, max(1.4, rect.width() * 0.06)))
    painter.setBrush(fill)
    painter.drawPath(path)
    margin = (1.0 - (badge.scale / 100.0)) / 2.0
    inner = rect.adjusted(rect.width() * margin, rect.height() * margin, -rect.width() * margin, -rect.height() * margin)
    _paint_symbol(painter, symbol_key(badge.icon), inner, mark, ink)


def _shape_path(shape: str, rect: QRectF) -> QPainterPath:
    path = QPainterPath()
    if shape == "rounded_square":
        path.addRoundedRect(rect, rect.width() * 0.22, rect.height() * 0.22)
        return path
    if shape == "shield":
        path.moveTo(rect.center().x(), rect.top())
        path.lineTo(rect.right(), rect.top() + rect.height() * 0.18)
        path.lineTo(rect.right(), rect.top() + rect.height() * 0.52)
        path.quadTo(rect.right(), rect.bottom(), rect.center().x(), rect.bottom())
        path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.top() + rect.height() * 0.52)
        path.lineTo(rect.left(), rect.top() + rect.height() * 0.18)
        path.closeSubpath()
        return path
    if shape == "hexagon":
        cx, cy, rx, ry = rect.center().x(), rect.center().y(), rect.width() / 2, rect.height() / 2
        for index in range(6):
            angle = math.radians(30 + index * 60)
            point = QPointF(cx + math.cos(angle) * rx, cy + math.sin(angle) * ry)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        return path
    if shape == "diamond":
        path.moveTo(rect.center().x(), rect.top())
        path.lineTo(rect.right(), rect.center().y())
        path.lineTo(rect.center().x(), rect.bottom())
        path.lineTo(rect.left(), rect.center().y())
        path.closeSubpath()
        return path
    if shape == "banner":
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.right(), rect.bottom() - rect.height() * 0.22)
        path.lineTo(rect.center().x(), rect.bottom())
        path.lineTo(rect.left(), rect.bottom() - rect.height() * 0.22)
        path.closeSubpath()
        return path
    if shape in {"pentagon", "scallop"}:
        cx, cy, rx, ry = rect.center().x(), rect.center().y(), rect.width() / 2, rect.height() / 2
        for index in range(5):
            angle = math.radians(-90 + index * 72)
            point = QPointF(cx + math.cos(angle) * rx, cy + math.sin(angle) * ry)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        return path
    if shape == "octagon":
        inset = rect.width() * 0.22
        path.moveTo(rect.left() + inset, rect.top())
        path.lineTo(rect.right() - inset, rect.top())
        path.lineTo(rect.right(), rect.top() + inset)
        path.lineTo(rect.right(), rect.bottom() - inset)
        path.lineTo(rect.right() - inset, rect.bottom())
        path.lineTo(rect.left() + inset, rect.bottom())
        path.lineTo(rect.left(), rect.bottom() - inset)
        path.lineTo(rect.left(), rect.top() + inset)
        path.closeSubpath()
        return path
    path.addEllipse(rect)
    return path


def _colors_differ(left: QColor, right: QColor) -> bool:
    delta = (left.red() - right.red()) ** 2 + (left.green() - right.green()) ** 2 + (left.blue() - right.blue()) ** 2
    return delta > 6400


def _paint_symbol(painter: QPainter, symbol: str, rect: QRectF, primary: QColor, accent: QColor) -> None:
    painter.save()
    name = (symbol or "anchor").lower()
    painter_fn = _SYMBOLS.get(name, _draw_anchor)
    painter_fn(painter, rect, primary, accent)
    painter.restore()


def _pt(rect: QRectF, x: float, y: float) -> QPointF:
    return QPointF(rect.left() + rect.width() * x, rect.top() + rect.height() * y)


def _line_w(rect: QRectF, scale: float = 0.10) -> float:
    return max(1.4, rect.width() * scale)


def _use_fill(painter: QPainter, color: QColor) -> None:
    painter.setPen(QPen(color, 0.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(color)


def _use_stroke(painter: QPainter, color: QColor, width: float) -> None:
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))


def _draw_anchor(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    cx, top, bottom = rect.center().x(), rect.top(), rect.bottom()
    _use_fill(painter, primary)
    painter.drawEllipse(QRectF(cx - rect.width() * 0.16, top, rect.width() * 0.32, rect.height() * 0.22))
    _use_stroke(painter, primary, _line_w(rect, 0.12))
    painter.drawLine(QPointF(cx, top + rect.height() * 0.2), QPointF(cx, bottom - rect.height() * 0.12))
    painter.drawLine(QPointF(rect.left() + rect.width() * 0.12, top + rect.height() * 0.42), QPointF(rect.right() - rect.width() * 0.12, top + rect.height() * 0.42))
    arm = QPainterPath()
    arm.moveTo(rect.left(), bottom - rect.height() * 0.28)
    arm.quadTo(rect.left(), bottom, cx, bottom)
    arm.quadTo(rect.right(), bottom, rect.right(), bottom - rect.height() * 0.28)
    _use_stroke(painter, accent, _line_w(rect, 0.14))
    painter.drawPath(arm)


def _draw_helm(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_stroke(painter, primary, _line_w(rect, 0.11))
    painter.drawEllipse(rect.adjusted(rect.width() * 0.18, rect.height() * 0.18, -rect.width() * 0.18, -rect.height() * 0.18))
    cx, cy, rx, ry = rect.center().x(), rect.center().y(), rect.width() * 0.48, rect.height() * 0.48
    _use_stroke(painter, accent, _line_w(rect, 0.10))
    for index in range(8):
        angle = math.radians(index * 45)
        painter.drawLine(
            QPointF(cx + math.cos(angle) * rx * 0.22, cy + math.sin(angle) * ry * 0.22),
            QPointF(cx + math.cos(angle) * rx, cy + math.sin(angle) * ry),
        )
    _use_fill(painter, primary)
    painter.drawEllipse(QRectF(cx - rect.width() * 0.10, cy - rect.height() * 0.10, rect.width() * 0.20, rect.height() * 0.20))


def _draw_compass(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    cx, cy = rect.center().x(), rect.center().y()
    north = QPainterPath()
    north.moveTo(cx, rect.top())
    north.lineTo(cx + rect.width() * 0.12, cy)
    north.lineTo(cx, rect.bottom())
    north.lineTo(cx - rect.width() * 0.12, cy)
    north.closeSubpath()
    _use_fill(painter, primary)
    painter.drawPath(north)
    east = QPainterPath()
    east.moveTo(rect.left(), cy)
    east.lineTo(cx, cy - rect.height() * 0.12)
    east.lineTo(rect.right(), cy)
    east.lineTo(cx, cy + rect.height() * 0.12)
    east.closeSubpath()
    _use_fill(painter, accent)
    painter.drawPath(east)


def _draw_sail(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    hull = QPainterPath()
    hull.moveTo(_pt(rect, 0.06, 0.74))
    hull.lineTo(_pt(rect, 0.94, 0.74))
    hull.quadTo(_pt(rect, 0.78, 1.0), _pt(rect, 0.5, 1.0))
    hull.quadTo(_pt(rect, 0.22, 1.0), _pt(rect, 0.06, 0.74))
    hull.closeSubpath()
    _use_fill(painter, primary)
    painter.drawPath(hull)
    painter.drawRect(QRectF(_pt(rect, 0.34, 0.04), _pt(rect, 0.42, 0.76)).normalized())
    sail = QPainterPath()
    sail.moveTo(_pt(rect, 0.42, 0.08))
    sail.lineTo(_pt(rect, 0.96, 0.70))
    sail.lineTo(_pt(rect, 0.42, 0.70))
    sail.closeSubpath()
    _use_fill(painter, accent)
    painter.drawPath(sail)


def _draw_lighthouse(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    lamp = _pt(rect, 0.50, 0.18)
    _use_stroke(painter, accent, _line_w(rect, 0.07))
    painter.drawLine(lamp, _pt(rect, 0.02, 0.08))
    painter.drawLine(lamp, _pt(rect, 0.20, 0.00))
    painter.drawLine(lamp, _pt(rect, 0.80, 0.00))
    painter.drawLine(lamp, _pt(rect, 0.98, 0.08))
    tower = QPainterPath()
    tower.moveTo(_pt(rect, 0.22, 1.00))
    tower.lineTo(_pt(rect, 0.34, 0.42))
    tower.lineTo(_pt(rect, 0.66, 0.42))
    tower.lineTo(_pt(rect, 0.78, 1.00))
    tower.closeSubpath()
    _use_fill(painter, primary)
    painter.drawPath(tower)
    _use_fill(painter, accent)
    painter.drawRoundedRect(QRectF(_pt(rect, 0.42, 0.56), _pt(rect, 0.58, 0.76)).normalized(), 2, 2)
    painter.drawRoundedRect(QRectF(_pt(rect, 0.12, 0.38), _pt(rect, 0.88, 0.48)).normalized(), 2, 2)
    painter.drawRect(QRectF(_pt(rect, 0.34, 0.14), _pt(rect, 0.66, 0.42)).normalized())
    painter.drawEllipse(QRectF(_pt(rect, 0.34, 0.04), _pt(rect, 0.66, 0.22)).normalized())
    _use_stroke(painter, primary, _line_w(rect, 0.07))
    painter.drawLine(_pt(rect, 0.50, 0.18), _pt(rect, 0.50, 0.38))


def _draw_whale(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    body = QPainterPath()
    body.addEllipse(QRectF(rect.left(), rect.top() + rect.height() * 0.28, rect.width() * 0.78, rect.height() * 0.48))
    _use_fill(painter, primary)
    painter.drawPath(body)
    tail = QPainterPath()
    tail.moveTo(rect.left() + rect.width() * 0.72, rect.center().y())
    tail.lineTo(rect.right(), rect.top() + rect.height() * 0.18)
    tail.lineTo(rect.right() - rect.width() * 0.08, rect.center().y())
    tail.lineTo(rect.right(), rect.bottom() - rect.height() * 0.18)
    tail.closeSubpath()
    _use_fill(painter, accent)
    painter.drawPath(tail)
    painter.drawEllipse(QRectF(_pt(rect, 0.18, 0.40), _pt(rect, 0.30, 0.54)).normalized())


def _draw_fish(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    body = QPainterPath()
    body.addEllipse(QRectF(rect.left(), rect.top() + rect.height() * 0.28, rect.width() * 0.7, rect.height() * 0.44))
    _use_fill(painter, primary)
    painter.drawPath(body)
    tail = QPainterPath()
    tail.moveTo(rect.left() + rect.width() * 0.62, rect.center().y())
    tail.lineTo(rect.right(), rect.top() + rect.height() * 0.22)
    tail.lineTo(rect.right(), rect.bottom() - rect.height() * 0.22)
    tail.closeSubpath()
    _use_fill(painter, accent)
    painter.drawPath(tail)
    painter.drawEllipse(QRectF(_pt(rect, 0.16, 0.42), _pt(rect, 0.28, 0.56)).normalized())


def _draw_wave(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    def wave(y: float) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(rect.left(), y)
        path.cubicTo(
            rect.left() + rect.width() * 0.2,
            y - rect.height() * 0.28,
            rect.left() + rect.width() * 0.3,
            y + rect.height() * 0.28,
            rect.center().x(),
            y,
        )
        path.cubicTo(
            rect.center().x() + rect.width() * 0.2,
            y - rect.height() * 0.28,
            rect.right() - rect.width() * 0.2,
            y + rect.height() * 0.28,
            rect.right(),
            y,
        )
        return path

    _use_stroke(painter, primary, _line_w(rect, 0.12))
    painter.drawPath(wave(rect.center().y() - rect.height() * 0.12))
    _use_stroke(painter, accent, _line_w(rect, 0.12))
    painter.drawPath(wave(rect.center().y() + rect.height() * 0.16))


def _draw_starfish(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    cx, cy, rx, ry = rect.center().x(), rect.center().y(), rect.width() * 0.48, rect.height() * 0.48
    path = QPainterPath()
    for index in range(10):
        angle = math.radians(-90 + index * 36)
        radius_x = rx if index % 2 == 0 else rx * 0.42
        radius_y = ry if index % 2 == 0 else ry * 0.42
        point = QPointF(cx + math.cos(angle) * radius_x, cy + math.sin(angle) * radius_y)
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    _use_fill(painter, primary)
    painter.drawPath(path)
    _use_fill(painter, accent)
    painter.drawEllipse(QRectF(cx - rx * 0.22, cy - ry * 0.22, rx * 0.44, ry * 0.44))


def _draw_spyglass(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    painter.save()
    painter.translate(rect.center())
    painter.rotate(-38)
    width, height = rect.width(), rect.height()
    _use_fill(painter, primary)
    painter.drawRoundedRect(QRectF(-width * 0.46, -height * 0.09, width * 0.30, height * 0.18), 3, 3)
    painter.drawRoundedRect(QRectF(-width * 0.20, -height * 0.13, width * 0.36, height * 0.26), 3, 3)
    _use_fill(painter, accent)
    painter.drawRoundedRect(QRectF(width * 0.12, -height * 0.18, width * 0.26, height * 0.36), 4, 4)
    painter.drawEllipse(QRectF(width * 0.30, -height * 0.20, height * 0.40, height * 0.40))
    painter.restore()


def _draw_lantern(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_fill(painter, primary)
    painter.drawRoundedRect(QRectF(rect.left() + rect.width() * 0.28, rect.top() + rect.height() * 0.22, rect.width() * 0.44, rect.height() * 0.58), 3, 3)
    _use_fill(painter, accent)
    painter.drawRect(QRectF(rect.left() + rect.width() * 0.34, rect.top() + rect.height() * 0.08, rect.width() * 0.32, rect.height() * 0.16))
    painter.drawRoundedRect(
        QRectF(rect.left() + rect.width() * 0.34, rect.top() + rect.height() * 0.32, rect.width() * 0.32, rect.height() * 0.28),
        2,
        2,
    )


def _draw_flag(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_stroke(painter, primary, _line_w(rect, 0.10))
    painter.drawLine(QPointF(rect.left() + rect.width() * 0.22, rect.top()), QPointF(rect.left() + rect.width() * 0.22, rect.bottom()))
    flag = QPainterPath()
    flag.moveTo(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.08)
    flag.lineTo(rect.right() - rect.width() * 0.08, rect.top() + rect.height() * 0.22)
    flag.lineTo(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.42)
    flag.closeSubpath()
    _use_fill(painter, accent)
    painter.drawPath(flag)


def _draw_gull(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    left = QPainterPath()
    left.moveTo(rect.left(), rect.center().y())
    left.quadTo(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.12, rect.center().x(), rect.center().y())
    _use_stroke(painter, primary, _line_w(rect, 0.12))
    painter.drawPath(left)
    right = QPainterPath()
    right.moveTo(rect.center().x(), rect.center().y())
    right.quadTo(rect.right() - rect.width() * 0.22, rect.top() + rect.height() * 0.12, rect.right(), rect.center().y())
    _use_stroke(painter, accent, _line_w(rect, 0.12))
    painter.drawPath(right)


def _draw_trident(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_fill(painter, primary)
    painter.drawRoundedRect(QRectF(_pt(rect, 0.44, 0.40), _pt(rect, 0.56, 1.00)).normalized(), 2, 2)
    _use_fill(painter, accent)
    painter.drawRoundedRect(QRectF(_pt(rect, 0.18, 0.40), _pt(rect, 0.82, 0.52)).normalized(), 3, 3)
    _use_stroke(painter, accent, _line_w(rect, 0.11))
    center = QPainterPath()
    center.moveTo(_pt(rect, 0.50, 0.46))
    center.lineTo(_pt(rect, 0.50, 0.08))
    painter.drawPath(center)
    left = QPainterPath()
    left.moveTo(_pt(rect, 0.30, 0.46))
    left.cubicTo(_pt(rect, 0.04, 0.42), _pt(rect, 0.10, 0.18), _pt(rect, 0.20, 0.06))
    painter.drawPath(left)
    right = QPainterPath()
    right.moveTo(_pt(rect, 0.70, 0.46))
    right.cubicTo(_pt(rect, 0.96, 0.42), _pt(rect, 0.90, 0.18), _pt(rect, 0.80, 0.06))
    painter.drawPath(right)

    def tip(x: float, y: float) -> None:
        point = QPainterPath()
        point.moveTo(_pt(rect, x, y))
        point.lineTo(_pt(rect, x - 0.09, y + 0.12))
        point.lineTo(_pt(rect, x + 0.09, y + 0.12))
        point.closeSubpath()
        painter.drawPath(point)

    _use_fill(painter, accent)
    tip(0.20, 0.00)
    tip(0.50, 0.00)
    tip(0.80, 0.00)


def _draw_shell(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    cx = rect.center().x()
    hinge = _pt(rect, 0.5, 0.94)
    rx, ry = rect.width() * 0.48, rect.height() * 0.58
    path = QPainterPath()
    path.moveTo(hinge)
    for index in range(9):
        t = index / 8
        angle = math.pi * (0.12 + 0.76 * t)
        radius = 1.0 if index % 2 == 0 else 0.82
        path.lineTo(QPointF(cx + math.cos(angle) * rx * radius, hinge.y() - math.sin(angle) * ry * radius))
    path.closeSubpath()
    _use_fill(painter, primary)
    painter.drawPath(path)
    _use_stroke(painter, accent, _line_w(rect, 0.07))
    for index in (1, 3, 5, 7):
        t = index / 8
        angle = math.pi * (0.12 + 0.76 * t)
        painter.drawLine(hinge, QPointF(cx + math.cos(angle) * rx * 0.92, hinge.y() - math.sin(angle) * ry * 0.92))


def _draw_buoy(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_fill(painter, accent)
    painter.drawEllipse(QRectF(_pt(rect, 0.36, 0.0), _pt(rect, 0.64, 0.22)).normalized())
    painter.drawRect(QRectF(_pt(rect, 0.45, 0.16), _pt(rect, 0.55, 0.38)).normalized())
    body = QPainterPath()
    body.moveTo(_pt(rect, 0.5, 0.32))
    body.lineTo(_pt(rect, 0.92, 0.96))
    body.lineTo(_pt(rect, 0.08, 0.96))
    body.closeSubpath()
    _use_fill(painter, primary)
    painter.drawPath(body)
    painter.save()
    painter.setClipPath(body)
    _use_fill(painter, accent)
    painter.drawRect(QRectF(_pt(rect, 0.0, 0.52), _pt(rect, 1.0, 0.64)).normalized())
    painter.drawRect(QRectF(_pt(rect, 0.0, 0.76), _pt(rect, 1.0, 0.88)).normalized())
    painter.restore()


def _draw_lifering(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_stroke(painter, primary, max(2.4, rect.width() * 0.22))
    painter.drawEllipse(rect.adjusted(rect.width() * 0.16, rect.height() * 0.16, -rect.width() * 0.16, -rect.height() * 0.16))
    _use_fill(painter, accent)
    cx, cy = rect.center().x(), rect.center().y()
    strap = max(rect.width() * 0.10, 2.0)
    painter.drawRect(QRectF(cx - strap / 2, rect.top() + rect.height() * 0.10, strap, rect.height() * 0.80))
    painter.drawRect(QRectF(rect.left() + rect.width() * 0.10, cy - strap / 2, rect.width() * 0.80, strap))


def _draw_moon(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    full = QPainterPath()
    full.addEllipse(rect.adjusted(rect.width() * 0.12, rect.height() * 0.12, -rect.width() * 0.12, -rect.height() * 0.12))
    cut = QPainterPath()
    cut.addEllipse(rect.adjusted(rect.width() * 0.32, rect.height() * 0.08, -rect.width() * 0.02, -rect.height() * 0.22))
    _use_fill(painter, primary)
    painter.drawPath(full.subtracted(cut))
    _use_fill(painter, accent)
    painter.drawEllipse(QRectF(_pt(rect, 0.18, 0.22), _pt(rect, 0.30, 0.34)).normalized())
    painter.drawEllipse(QRectF(_pt(rect, 0.22, 0.42), _pt(rect, 0.32, 0.52)).normalized())


def _draw_sun(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_fill(painter, primary)
    painter.drawEllipse(rect.adjusted(rect.width() * 0.28, rect.height() * 0.28, -rect.width() * 0.28, -rect.height() * 0.28))
    cx, cy, rx, ry = rect.center().x(), rect.center().y(), rect.width() * 0.48, rect.height() * 0.48
    _use_stroke(painter, accent, _line_w(rect, 0.10))
    for index in range(8):
        angle = math.radians(index * 45)
        painter.drawLine(
            QPointF(cx + math.cos(angle) * rx * 0.55, cy + math.sin(angle) * ry * 0.55),
            QPointF(cx + math.cos(angle) * rx, cy + math.sin(angle) * ry),
        )


def _draw_harpoon(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_stroke(painter, primary, _line_w(rect, 0.11))
    painter.drawLine(rect.bottomLeft() + QPointF(rect.width() * 0.12, -rect.height() * 0.12), rect.topRight() - QPointF(rect.width() * 0.12, -rect.height() * 0.12))
    tip = QPainterPath()
    tip.moveTo(rect.right() - rect.width() * 0.08, rect.top() + rect.height() * 0.12)
    tip.lineTo(rect.right() - rect.width() * 0.32, rect.top() + rect.height() * 0.08)
    tip.lineTo(rect.right() - rect.width() * 0.22, rect.top() + rect.height() * 0.28)
    _use_fill(painter, accent)
    painter.drawPath(tip)


def _draw_barrel(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_fill(painter, primary)
    painter.drawRoundedRect(rect.adjusted(rect.width() * 0.22, rect.height() * 0.08, -rect.width() * 0.22, -rect.height() * 0.08), 6, 6)
    _use_stroke(painter, accent, _line_w(rect, 0.10))
    y1 = rect.top() + rect.height() * 0.32
    y2 = rect.top() + rect.height() * 0.68
    painter.drawLine(QPointF(rect.left() + rect.width() * 0.24, y1), QPointF(rect.right() - rect.width() * 0.24, y1))
    painter.drawLine(QPointF(rect.left() + rect.width() * 0.24, y2), QPointF(rect.right() - rect.width() * 0.24, y2))


def _draw_chest(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_fill(painter, primary)
    painter.drawRoundedRect(QRectF(_pt(rect, 0.08, 0.42), _pt(rect, 0.92, 0.94)).normalized(), 4, 4)
    lid = QPainterPath()
    lid.moveTo(_pt(rect, 0.08, 0.46))
    lid.quadTo(_pt(rect, 0.5, 0.0), _pt(rect, 0.92, 0.46))
    lid.lineTo(_pt(rect, 0.08, 0.46))
    lid.closeSubpath()
    _use_fill(painter, accent)
    painter.drawPath(lid)
    painter.drawRoundedRect(QRectF(_pt(rect, 0.42, 0.52), _pt(rect, 0.58, 0.74)).normalized(), 2, 2)


def _draw_bottle(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_fill(painter, accent)
    painter.drawRoundedRect(QRectF(_pt(rect, 0.40, 0.0), _pt(rect, 0.60, 0.14)).normalized(), 2, 2)
    body = QPainterPath()
    body.moveTo(_pt(rect, 0.40, 0.12))
    body.lineTo(_pt(rect, 0.40, 0.32))
    body.quadTo(_pt(rect, 0.40, 0.42), _pt(rect, 0.22, 0.50))
    body.lineTo(_pt(rect, 0.20, 0.90))
    body.quadTo(_pt(rect, 0.50, 1.02), _pt(rect, 0.80, 0.90))
    body.lineTo(_pt(rect, 0.78, 0.50))
    body.quadTo(_pt(rect, 0.60, 0.42), _pt(rect, 0.60, 0.32))
    body.lineTo(_pt(rect, 0.60, 0.12))
    body.closeSubpath()
    _use_fill(painter, primary)
    painter.drawPath(body)
    painter.save()
    painter.setClipPath(body)
    _use_fill(painter, accent)
    painter.drawRect(QRectF(_pt(rect, 0.0, 0.62), _pt(rect, 1.0, 0.96)).normalized())
    painter.restore()


def _draw_map(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    sheet = QPainterPath()
    sheet.moveTo(_pt(rect, 0.08, 0.24))
    sheet.lineTo(_pt(rect, 0.68, 0.08))
    sheet.lineTo(_pt(rect, 0.68, 0.30))
    sheet.lineTo(_pt(rect, 0.94, 0.30))
    sheet.lineTo(_pt(rect, 0.90, 0.90))
    sheet.lineTo(_pt(rect, 0.10, 0.94))
    sheet.closeSubpath()
    _use_fill(painter, primary)
    painter.drawPath(sheet)
    fold = QPainterPath()
    fold.moveTo(_pt(rect, 0.68, 0.08))
    fold.lineTo(_pt(rect, 0.94, 0.30))
    fold.lineTo(_pt(rect, 0.68, 0.30))
    fold.closeSubpath()
    _use_fill(painter, accent)
    painter.drawPath(fold)
    _use_stroke(painter, accent, _line_w(rect, 0.07))
    path = QPainterPath()
    path.moveTo(_pt(rect, 0.22, 0.52))
    path.lineTo(_pt(rect, 0.40, 0.40))
    path.lineTo(_pt(rect, 0.52, 0.62))
    path.lineTo(_pt(rect, 0.72, 0.48))
    painter.drawPath(path)


def _draw_knot(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_stroke(painter, primary, _line_w(rect, 0.12))
    painter.drawEllipse(rect.adjusted(rect.width() * 0.18, rect.height() * 0.18, -rect.width() * 0.18, -rect.height() * 0.18))
    _use_stroke(painter, accent, _line_w(rect, 0.10))
    painter.drawEllipse(rect.adjusted(rect.width() * 0.32, rect.height() * 0.32, -rect.width() * 0.32, -rect.height() * 0.32))


def _draw_cannon(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    trail = QPainterPath()
    trail.moveTo(_pt(rect, 0.10, 0.38))
    trail.lineTo(_pt(rect, 0.70, 0.38))
    trail.lineTo(_pt(rect, 0.62, 0.58))
    trail.lineTo(_pt(rect, 0.16, 0.92))
    trail.lineTo(_pt(rect, 0.02, 0.82))
    trail.closeSubpath()
    _use_fill(painter, primary)
    painter.drawPath(trail)
    wheel = QRectF(_pt(rect, 0.40, 0.46), _pt(rect, 0.98, 1.02)).normalized()
    _use_stroke(painter, primary, _line_w(rect, 0.12))
    painter.drawEllipse(wheel)
    hub = wheel.center()
    spoke = _line_w(rect, 0.07)
    _use_stroke(painter, accent, spoke)
    rx, ry = wheel.width() * 0.32, wheel.height() * 0.32
    painter.drawLine(QPointF(hub.x() - rx, hub.y()), QPointF(hub.x() + rx, hub.y()))
    painter.drawLine(QPointF(hub.x(), hub.y() - ry), QPointF(hub.x(), hub.y() + ry))
    painter.drawLine(
        QPointF(hub.x() - rx * 0.72, hub.y() - ry * 0.72),
        QPointF(hub.x() + rx * 0.72, hub.y() + ry * 0.72),
    )
    _use_fill(painter, accent)
    painter.drawEllipse(QRectF(hub.x() - rect.width() * 0.07, hub.y() - rect.height() * 0.07, rect.width() * 0.14, rect.height() * 0.14))
    painter.drawRoundedRect(QRectF(_pt(rect, 0.04, 0.14), _pt(rect, 0.84, 0.44)).normalized(), 4, 4)
    painter.drawEllipse(QRectF(_pt(rect, 0.00, 0.20), _pt(rect, 0.14, 0.38)).normalized())
    painter.drawRoundedRect(QRectF(_pt(rect, 0.78, 0.10), _pt(rect, 0.94, 0.48)).normalized(), 2, 2)


def _draw_sextant(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_stroke(painter, primary, _line_w(rect, 0.12))
    arc = QPainterPath()
    arc.arcMoveTo(rect.adjusted(rect.width() * 0.08, rect.height() * 0.18, -rect.width() * 0.08, -rect.height() * 0.08), 20)
    arc.arcTo(rect.adjusted(rect.width() * 0.08, rect.height() * 0.18, -rect.width() * 0.08, -rect.height() * 0.08), 20, 140)
    painter.drawPath(arc)
    _use_stroke(painter, accent, _line_w(rect, 0.10))
    painter.drawLine(rect.center(), QPointF(rect.right() - rect.width() * 0.12, rect.top() + rect.height() * 0.18))


def _draw_kraken(painter: QPainter, rect: QRectF, primary: QColor, accent: QColor) -> None:
    _use_fill(painter, primary)
    painter.drawEllipse(QRectF(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.08, rect.width() * 0.56, rect.height() * 0.42))
    _use_stroke(painter, accent, _line_w(rect, 0.10))
    for offset in (0.18, 0.38, 0.58, 0.78):
        path = QPainterPath()
        start = QPointF(rect.left() + rect.width() * offset, rect.top() + rect.height() * 0.44)
        path.moveTo(start)
        path.quadTo(
            QPointF(rect.left() + rect.width() * (offset + 0.08), rect.bottom()),
            QPointF(rect.left() + rect.width() * (offset - 0.04), rect.bottom() - rect.height() * 0.08),
        )
        painter.drawPath(path)


_SYMBOLS = {
    "anchor": _draw_anchor,
    "helm": _draw_helm,
    "compass": _draw_compass,
    "sail": _draw_sail,
    "lighthouse": _draw_lighthouse,
    "whale": _draw_whale,
    "fish": _draw_fish,
    "wave": _draw_wave,
    "starfish": _draw_starfish,
    "spyglass": _draw_spyglass,
    "lantern": _draw_lantern,
    "flag": _draw_flag,
    "gull": _draw_gull,
    "trident": _draw_trident,
    "shell": _draw_shell,
    "buoy": _draw_buoy,
    "lifering": _draw_lifering,
    "moon": _draw_moon,
    "sun": _draw_sun,
    "harpoon": _draw_harpoon,
    "barrel": _draw_barrel,
    "chest": _draw_chest,
    "bottle": _draw_bottle,
    "map": _draw_map,
    "knot": _draw_knot,
    "cannon": _draw_cannon,
    "sextant": _draw_sextant,
    "kraken": _draw_kraken,
}
