from __future__ import annotations

import base64
import gzip
import json
import re

from sailwind_mod_sync.models import ModPack, PinnedMod

SHARE_FENCE = "sailwind-modpack"
SHARE_TOKEN_PREFIX = "sailwind-modpack:1:"
DISCORD_MESSAGE_LIMIT = 2000

_FENCE_RE = re.compile(
    r"```(?:sailwind-modpack|json|sms)?[^\n]*\n?(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_TOKEN_RE = re.compile(
    r"sailwind-modpack\s*:\s*1\s*:\s*([A-Za-z0-9_\-=\s]+)",
    re.IGNORECASE,
)


def encode_pack_share(pack: ModPack) -> str:
    payload = pack_share_payload(pack)
    json_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    header = _share_header(pack)
    fenced_json = f"{header}\n```{SHARE_FENCE}\n{json_body}\n```"
    token = _encode_token(json_body)
    fenced_token = f"{header}\n```\n{token}\n```"
    preferred = (fenced_json, fenced_token, token)
    for text in preferred:
        if len(text) <= DISCORD_MESSAGE_LIMIT:
            return text
    return min(preferred, key=len)


def pack_share_payload(pack: ModPack) -> dict:
    payload = {
        "schema": pack.schema,
        "name": pack.name,
        "version": pack.version,
        "mods": [_compact_mod(mod) for mod in pack.mods],
    }
    if pack.bepinex:
        payload["bepinex"] = pack.bepinex
    return payload


def parse_share_text(text: str) -> dict:
    raw = (text or "").strip().lstrip("\ufeff")
    if not raw:
        raise ValueError("Clipboard is empty")
    token_match = _TOKEN_RE.search(raw)
    if token_match:
        blob = re.sub(r"\s+", "", token_match.group(1))
        try:
            return _validate_payload(_decode_token(blob))
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Clipboard share code could not be decoded") from exc
    candidates = [block.strip() for block in _FENCE_RE.findall(raw)]
    candidates.append(raw)
    last_error = "Clipboard does not contain a Sailwind ModPack"
    for candidate in candidates:
        try:
            return _validate_payload(_parse_json_object(candidate))
        except ValueError as exc:
            last_error = str(exc)
    raise ValueError(last_error)


def _compact_mod(mod: PinnedMod) -> dict:
    item: dict = {"guid": mod.guid, "version": mod.version}
    if mod.repo:
        item["repo"] = mod.repo
    if not mod.enabled:
        item["enabled"] = False
    if mod.plugin_folders:
        item["plugin_folders"] = list(mod.plugin_folders)
    if mod.version_raw and mod.version_raw != mod.version:
        item["version_raw"] = mod.version_raw
    return item


def _share_header(pack: ModPack) -> str:
    count = len(pack.mods)
    noun = "mod" if count == 1 else "mods"
    return (
        f'Sailwind ModPack "{pack.name}" ({count} {noun}) — '
        "paste this in Sailwind Mod Synchronizer"
    )


def _encode_token(json_body: str) -> str:
    compressed = gzip.compress(json_body.encode("utf-8"), compresslevel=9)
    token = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return f"{SHARE_TOKEN_PREFIX}{token}"


def _decode_token(blob: str) -> dict:
    padded = blob + ("=" * (-len(blob) % 4))
    raw = gzip.decompress(base64.urlsafe_b64decode(padded))
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Clipboard share code is not a ModPack")
    return data


def _parse_json_object(text: str) -> dict:
    snippet = text.strip()
    start = snippet.find("{")
    end = snippet.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Clipboard does not contain a Sailwind ModPack")
    try:
        data = json.loads(snippet[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("Clipboard does not contain a Sailwind ModPack") from exc
    if not isinstance(data, dict):
        raise ValueError("ModPack share must be a JSON object")
    return data


def _validate_payload(data: dict) -> dict:
    mods = data.get("mods")
    name = str(data.get("name") or "").strip()
    pack_id = str(data.get("id") or "").strip()
    if mods is None and not name and not pack_id:
        raise ValueError("Clipboard does not contain a Sailwind ModPack")
    if mods is not None and not isinstance(mods, list):
        raise ValueError("ModPack mods must be a list")
    return data
