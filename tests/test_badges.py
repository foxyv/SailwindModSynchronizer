from __future__ import annotations

import json
import random
from pathlib import Path

from PySide6.QtWidgets import QApplication

from sailwind_mod_sync.library.store import LibraryStore
from sailwind_mod_sync.models import PackBadge, ModPack, PinnedMod
from sailwind_mod_sync.packs.badges import (
    SHAPE_LABELS,
    SHAPES,
    SYMBOL_LABELS,
    SYMBOLS,
    badge_for_seed,
    color_hex,
    encode_custom_image,
    random_badge,
    render_badge,
    resolve_badge,
    shape_key,
    symbol_key,
)
from sailwind_mod_sync.packs.modpack import PackStore
from sailwind_mod_sync.packs.share import DISCORD_MESSAGE_LIMIT, encode_pack_share, pack_share_payload, parse_share_text
from sailwind_mod_sync.paths import AppPaths

WHITE = (255, 255, 255)
NAVY = (22, 50, 79)
GOLD = (232, 197, 71)
WAVE_FILL = (29, 53, 87)
WAVE_EDGE = (168, 218, 220)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_shape_icon_and_color_catalogs_are_indexed() -> None:
    assert len(SHAPES) == len(SHAPE_LABELS) >= 6
    assert len(SYMBOLS) == len(SYMBOL_LABELS) >= 20
    assert len(set(SHAPES)) == len(SHAPES)
    assert len(set(SYMBOLS)) == len(SYMBOLS)
    assert "anchor" in SYMBOLS
    assert "helm" in SYMBOLS
    assert "kraken" in SYMBOLS
    assert "circle" in SHAPES
    assert "shield" in SHAPES
    assert "pentagon" in SHAPES
    assert "scallop" not in SHAPES
    assert shape_key(6) == "pentagon"


def test_random_and_seeded_badges_are_stable() -> None:
    first = random_badge(random.Random(7))
    second = random_badge(random.Random(7))
    assert first.to_dict() == second.to_dict()
    assert 0 <= first.shape < len(SHAPES)
    assert 0 <= first.icon < len(SYMBOLS)
    assert 20 <= first.scale <= 100
    assert first.fill == tuple(max(0, min(255, part)) for part in first.fill)
    same = badge_for_seed("crew")
    again = badge_for_seed("crew")
    assert same.to_dict() == again.to_dict()
    assert badge_for_seed("other").to_dict() != same.to_dict()
    assert same.edge == (same.edge[0], same.edge[1], same.edge[2])


def test_composed_badges_render() -> None:
    app = _app()
    generated = random_badge()
    pixmap = render_badge(generated, 32)
    assert not pixmap.isNull()
    assert pixmap.width() == 32
    composed = render_badge(PackBadge(shape=2, icon=0, edge=GOLD, fill=NAVY, mark=GOLD), 40, 2.0)
    assert composed.width() == 80
    assert composed.devicePixelRatio() == 2.0
    app.processEvents()


def _inner_has_color(pixmap, rgb: tuple[int, int, int], *, inset: float = 0.18, tolerance: int = 52) -> bool:
    image = pixmap.toImage()
    width, height = image.width(), image.height()
    left, top = int(width * inset), int(height * inset)
    right, bottom = int(width * (1 - inset)), int(height * (1 - inset))
    limit = tolerance * tolerance
    for y in range(top, bottom):
        for x in range(left, right):
            color = image.pixelColor(x, y)
            if color.alpha() < 180:
                continue
            if (color.red() - rgb[0]) ** 2 + (color.green() - rgb[1]) ** 2 + (color.blue() - rgb[2]) ** 2 <= limit:
                return True
    return False


def test_hard_to_read_symbols_still_render() -> None:
    app = _app()
    for symbol in ("shell", "buoy", "cannon", "bottle", "chest", "spyglass", "sail", "map", "lighthouse", "trident"):
        badge = PackBadge(shape=0, icon=SYMBOLS.index(symbol), edge=(200, 40, 40), fill=NAVY, mark=GOLD, ink=WHITE, scale=80)
        pixmap = render_badge(badge, 64)
        assert not pixmap.isNull(), symbol
        assert pixmap.width() == 64
        assert _inner_has_color(pixmap, GOLD), symbol
        assert _inner_has_color(pixmap, WHITE), symbol
        assert not _inner_has_color(pixmap, (200, 40, 40), tolerance=24), symbol
    matched = PackBadge(shape=0, icon=SYMBOLS.index("sail"), edge=GOLD, fill=NAVY, mark=GOLD, ink=GOLD, scale=80)
    same = render_badge(matched, 64)
    assert _inner_has_color(same, GOLD)
    assert _inner_has_color(same, (244, 239, 232))
    app.processEvents()


def test_badge_roundtrip_uses_rgb_bytes() -> None:
    badge = PackBadge(shape=3, icon=12, edge=WHITE, fill=NAVY, mark=GOLD)
    payload = badge.to_dict()
    assert payload == {
        "shape": 3,
        "icon": 12,
        "edge": [255, 255, 255],
        "fill": [22, 50, 79],
        "mark": [232, 197, 71],
        "ink": [244, 239, 232],
        "scale": 56,
    }
    restored = PackBadge.from_dict(payload)
    assert restored == badge
    packed = PackBadge.from_dict([3, 12, list(WHITE), list(NAVY), list(GOLD)])
    assert packed == badge
    with_ink = PackBadge.from_dict([3, 12, list(WHITE), list(NAVY), list(GOLD), list(WHITE)])
    assert with_ink is not None
    assert with_ink.ink == WHITE
    flat = PackBadge.from_dict([3, 12, 255, 255, 255, 22, 50, 79, 232, 197, 71, 80])
    assert flat is not None
    assert flat.scale == 80
    assert flat.ink == (244, 239, 232)
    colored = PackBadge.from_dict([3, 12, 255, 255, 255, 22, 50, 79, 232, 197, 71, 10, 20, 30, 80])
    assert colored is not None
    assert colored.ink == (10, 20, 30)
    assert colored.scale == 80
    assert PackBadge.from_dict({"shape": 2, "icon": 0, "fill": list(NAVY)}).scale == 56


def test_legacy_badges_decode_to_rgb() -> None:
    builtin = PackBadge.from_dict({"kind": "builtin", "id": "anchor"})
    assert builtin is not None
    assert shape_key(builtin.shape) == "shield"
    assert symbol_key(builtin.icon) == "anchor"
    assert builtin.fill == NAVY
    assert color_hex(builtin.fill).lower() == "#16324f"
    generated = PackBadge.from_dict(
        {
            "kind": "generated",
            "shape": "hexagon",
            "color": "#1d3557",
            "accent": "#a8dadc",
            "symbol": "wave",
        }
    )
    assert generated is not None
    assert shape_key(generated.shape) == "hexagon"
    assert symbol_key(generated.icon) == "wave"
    assert generated.fill == WAVE_FILL
    assert generated.edge == WAVE_EDGE
    scallop = PackBadge.from_dict({"kind": "generated", "shape": "scallop", "color": "#1d3557"})
    assert scallop is not None
    assert shape_key(scallop.shape) == "pentagon"
    indexed = PackBadge.from_dict({"shape": 2, "icon": 0, "edge": 15, "fill": 10, "mark": 15})
    assert indexed is not None
    assert color_hex(indexed.fill).lower() == "#16324f"
    assert PackBadge.from_dict({"kind": "custom", "png": "not-an-image"}) is None
    assert PackBadge.from_dict({"kind": "builtin", "id": "not-a-badge"}) is None


def test_custom_png_renders_and_stays_off_clipboard() -> None:
    app = _app()
    icon = Path(__file__).resolve().parents[1] / "assets" / "icon.png"
    png = encode_custom_image(icon)
    badge = PackBadge(shape=2, icon=4, edge=WHITE, fill=NAVY, mark=GOLD, png=png)
    pixmap = render_badge(badge, 36)
    assert not pixmap.isNull()
    payload = badge.to_dict()
    assert payload["png"] == png
    restored = PackBadge.from_dict(payload)
    assert restored is not None
    assert restored.png == png
    custom = PackBadge.from_dict({"kind": "custom", "png": png})
    assert custom is not None
    assert custom.png == png
    pack = ModPack(id="art", name="Art Crew", badge=badge)
    shared = pack_share_payload(pack)
    assert "badge" not in shared
    parsed = parse_share_text(encode_pack_share(pack))
    assert "badge" not in parsed
    assert "png" not in json.dumps(parsed)
    app.processEvents()


def test_paste_without_badge_assigns_random(paths: AppPaths) -> None:
    store = PackStore(paths)
    imported = store.import_manifest({"name": "Pasted Crew", "mods": []}, random_if_missing=True)
    assert imported.badge is not None
    assert not imported.badge.png
    assert 0 <= imported.badge.shape < len(SHAPES)
    assert 0 <= imported.badge.icon < len(SYMBOLS)


def test_composed_badge_share_is_compact() -> None:
    pack = ModPack(
        id="crew-night",
        name="Crew Night",
        version="1.0.0",
        bepinex="5.4.2305",
        mods=[
            PinnedMod(
                guid="com.dizzy.sailwind.gamma",
                version="0.3.3",
                repo="https://github.com/foxyv/dizzy_sailwind_mods",
                plugin_folders=["Dizzy.Gamma"],
                version_raw="v0.3.3",
            ),
            PinnedMod(guid="com.example.optional", version="2.0.0", enabled=False),
        ],
        badge=PackBadge(shape=2, icon=4, edge=WHITE, fill=NAVY, mark=GOLD),
    )
    text = encode_pack_share(pack)
    assert len(text) <= DISCORD_MESSAGE_LIMIT
    parsed = parse_share_text(text)
    assert parsed["badge"] == pack.badge.to_dict()
    assert parsed["badge"]["edge"] == [255, 255, 255]
    assert "png" not in parsed["badge"]
    assert "kind" not in parsed["badge"]


def test_create_export_import_preserves_badge(paths: AppPaths) -> None:
    store = PackStore(paths)
    pack = store.create("Badge Pack")
    assert pack.badge is not None
    dest = paths.root / "badge-pack.json"
    store.export_json(pack.id, dest)
    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["badge"]["shape"] == pack.badge.shape
    assert payload["badge"]["icon"] == pack.badge.icon
    assert payload["badge"]["fill"] == list(pack.badge.fill)
    assert "png" not in payload["badge"]
    imported = store.import_file(dest, LibraryStore(paths))
    assert imported.badge is not None
    assert imported.badge.to_dict() == pack.badge.to_dict()


def test_duplicate_copies_badge(paths: AppPaths) -> None:
    store = PackStore(paths)
    original = store.create("Flagship")
    original.badge = PackBadge(shape=2, icon=0, edge=GOLD, fill=NAVY, mark=GOLD)
    store.save(original)
    copy = store.duplicate(original.id, "Flagship copy")
    assert copy.badge is not None
    assert copy.badge.to_dict() == original.badge.to_dict()


def test_missing_badge_is_assigned_from_id(paths: AppPaths) -> None:
    store = PackStore(paths)
    pack = store.create("Legacy")
    data = pack.to_dict()
    data.pop("badge", None)
    store.manifest_path(pack.id).write_text(json.dumps(data) + "\n", encoding="utf-8")
    loaded = store.get(pack.id)
    assert loaded.badge is not None
    assert loaded.badge.to_dict() == badge_for_seed(pack.id).to_dict()


def test_resolve_none_falls_back_to_seed() -> None:
    fallback = resolve_badge(None, seed="x")
    assert fallback.to_dict() == badge_for_seed("x").to_dict()
    clamped = resolve_badge(PackBadge(shape=99, icon=-3, edge=(300, -1, 4), fill=NAVY, mark=GOLD, scale=4))
    assert clamped.shape == len(SHAPES) - 1
    assert clamped.icon == 0
    assert clamped.edge == (255, 0, 4)
    assert clamped.scale == 20
