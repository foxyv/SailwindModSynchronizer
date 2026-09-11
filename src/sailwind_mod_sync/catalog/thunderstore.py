from __future__ import annotations

from sailwind_mod_sync.constants import (
    BEPINEX_NAMESPACE,
    BEPINEX_PACK_NAME,
    THUNDERSTORE_DOWNLOAD,
    THUNDERSTORE_PACK_API,
)
from sailwind_mod_sync.http_util import HttpClient, HttpError, ProgressFn


def latest_bepinex_version(http: HttpClient) -> str:
    data, _, _ = http.get_json(THUNDERSTORE_PACK_API)
    if not isinstance(data, dict):
        raise HttpError("Unexpected Thunderstore package payload")
    latest = data.get("latest") or {}
    version = str(latest.get("version_number") or "").strip()
    if not version:
        raise HttpError("Thunderstore BepInExPack has no version_number")
    return version


def bepinex_download_url(version: str) -> str:
    return THUNDERSTORE_DOWNLOAD.format(
        namespace=BEPINEX_NAMESPACE,
        name=BEPINEX_PACK_NAME,
        version=version,
    )


def download_bepinex_pack(
    http: HttpClient,
    dest,
    version: str,
    progress: ProgressFn | None = None,
) -> None:
    url = bepinex_download_url(version)
    if progress:
        progress(f"Downloading BepInExPack {version}…")
    http.download(url, dest, progress=progress)
