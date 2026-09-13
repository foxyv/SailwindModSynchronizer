from __future__ import annotations

import json

from sailwind_mod_sync.models import ModPack, PinnedMod
from sailwind_mod_sync.packs.share import (
    SHARE_TOKEN_PREFIX,
    encode_pack_share,
    pack_share_payload,
    parse_share_text,
)


def _sample_pack() -> ModPack:
    return ModPack(
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
            PinnedMod(
                guid="com.example.optional",
                version="2.0.0",
                enabled=False,
            ),
        ],
    )


def test_share_payload_omits_id_and_defaults() -> None:
    payload = pack_share_payload(_sample_pack())
    assert "id" not in payload
    assert payload["name"] == "Crew Night"
    assert payload["mods"][0]["guid"] == "com.dizzy.sailwind.gamma"
    assert payload["mods"][0]["version_raw"] == "v0.3.3"
    assert "enabled" not in payload["mods"][0]
    assert payload["mods"][1]["enabled"] is False
    assert "repo" not in payload["mods"][1]


def test_encode_roundtrip_fenced_json() -> None:
    text = encode_pack_share(_sample_pack())
    assert "```sailwind-modpack" in text
    assert "Crew Night" in text
    parsed = parse_share_text(text)
    assert parsed["name"] == "Crew Night"
    assert parsed["mods"][1]["enabled"] is False


def test_parse_discord_chatter_around_fence() -> None:
    body = json.dumps(pack_share_payload(_sample_pack()), separators=(",", ":"))
    pasted = (
        "hey try this pack tonight\n"
        f"```sailwind-modpack\n{body}\n```\n"
        "paste it in the manager"
    )
    parsed = parse_share_text(pasted)
    assert parsed["name"] == "Crew Night"
    assert len(parsed["mods"]) == 2


def test_parse_exported_pretty_json() -> None:
    pack = _sample_pack()
    exported = json.dumps(pack.to_dict(), indent=2)
    parsed = parse_share_text(exported)
    assert parsed["id"] == "crew-night"
    assert parsed["mods"][0]["guid"] == "com.dizzy.sailwind.gamma"


def test_parse_compressed_token_with_newlines(monkeypatch) -> None:
    monkeypatch.setattr("sailwind_mod_sync.packs.share.DISCORD_MESSAGE_LIMIT", 40)
    text = encode_pack_share(_sample_pack())
    assert SHARE_TOKEN_PREFIX in text
    wrapped = "\n".join(text[i : i + 24] for i in range(0, len(text), 24))
    parsed = parse_share_text(f"```\n{wrapped}\n```")
    assert parsed["name"] == "Crew Night"
    assert parsed["mods"][0]["version"] == "0.3.3"


def test_parse_rejects_empty_and_unrelated_json() -> None:
    try:
        parse_share_text("   ")
        assert False, "empty clipboard should fail"
    except ValueError as exc:
        assert "empty" in str(exc).lower()
    try:
        parse_share_text('{"hello": "discord"}')
        assert False, "unrelated JSON should fail"
    except ValueError as exc:
        assert "ModPack" in str(exc)
