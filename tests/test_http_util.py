from __future__ import annotations

from pathlib import Path

import httpx

from sailwind_mod_sync.http_util import HttpClient, HttpError, url_needs_api_token


def test_url_needs_api_token() -> None:
    assert url_needs_api_token("https://api.github.com/repos/o/r/releases/latest")
    assert url_needs_api_token("https://api.github.com/repos/o/r/releases/assets/1")
    assert url_needs_api_token("https://gitlab.com/api/v4/projects/1/releases")
    assert not url_needs_api_token("https://github.com/o/r/releases/download/v1/big.zip")
    assert not url_needs_api_token("https://release-assets.githubusercontent.com/file.bin")
    assert not url_needs_api_token("https://objects.githubusercontent.com/file.bin")
    assert not url_needs_api_token("https://gitlab.com/group/project/-/releases/v1/downloads/mod.zip")


def test_json_requests_send_token() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"ok": True})

    http = HttpClient(
        token="ghs_secret",
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )
    data, _, _ = http.get_json("https://api.github.com/repos/o/r/releases/latest")
    assert data == {"ok": True}
    assert seen == ["Bearer ghs_secret"]


def test_browser_download_does_not_send_token(tmp_path: Path) -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers.get("authorization")))
        if request.url.host == "github.com":
            return httpx.Response(
                302,
                headers={"Location": "https://release-assets.githubusercontent.com/large.bin"},
            )
        return httpx.Response(200, content=b"mod-bytes")

    http = HttpClient(
        token="ghs_secret",
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )
    dest = tmp_path / "large.bin"
    http.download("https://github.com/o/r/releases/download/v1/large.bin", dest)
    assert dest.read_bytes() == b"mod-bytes"
    assert seen[0] == ("github.com", None)
    assert seen[1] == ("release-assets.githubusercontent.com", None)


def test_api_asset_download_sends_token_only_to_github_api(tmp_path: Path) -> None:
    seen: list[tuple[str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.host,
                request.headers.get("authorization"),
                request.headers.get("accept"),
            )
        )
        if request.url.host == "api.github.com":
            return httpx.Response(
                302,
                headers={"Location": "https://objects.githubusercontent.com/large.bin"},
            )
        return httpx.Response(200, content=b"asset-bytes")

    http = HttpClient(
        token="ghs_secret",
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )
    dest = tmp_path / "large.bin"
    http.download("https://api.github.com/repos/o/r/releases/assets/99", dest)
    assert dest.read_bytes() == b"asset-bytes"
    assert seen[0][0] == "api.github.com"
    assert seen[0][1] == "Bearer ghs_secret"
    assert seen[0][2] == "application/octet-stream"
    assert seen[1][0] == "objects.githubusercontent.com"
    assert seen[1][1] is None


def test_download_rejects_short_content_length(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"short", headers={"Content-Length": "80"})

    http = HttpClient(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    )
    dest = tmp_path / "mod.zip"
    try:
        http.download("https://github.com/o/r/releases/download/v1/mod.zip", dest)
    except HttpError as exc:
        assert "Incomplete download" in str(exc)
        assert "5 of 80" in str(exc)
    else:
        raise AssertionError("expected HttpError")
    assert not dest.exists()
    assert not dest.with_suffix(".zip.part").exists()


def test_download_rejects_empty_body(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"", headers={"Content-Length": "0"})

    http = HttpClient(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    )
    dest = tmp_path / "mod.zip"
    try:
        http.download("https://github.com/o/r/releases/download/v1/mod.zip", dest)
    except HttpError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("expected HttpError")
    assert not dest.exists()
