from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from sailwind_mod_sync.constants import USER_AGENT

ProgressFn = Callable[[str], None]
log = logging.getLogger(__name__)


def url_needs_api_token(url: str) -> bool:
    """True when a GitHub/GitLab token belongs on this URL.

    Browser download links and GitHub CDNs must not receive Authorization.
    Sending a token there makes GitHub treat the request as an API download and
    fail for large public release assets (often around 50 MB).
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or ""
    if host == "api.github.com":
        return True
    if host == "gitlab.com" and path.startswith("/api/"):
        return True
    return False


class HttpError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpClient:
    def __init__(
        self,
        token: str = "",
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.token = token.strip()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_bytes(self, url: str, extra_headers: dict[str, str] | None = None) -> bytes:
        started = time.perf_counter()
        log.info("HTTP GET %s", url)
        response = self._client.get(url, headers=self._headers(url, extra_headers))
        self._raise_for_status(response, url)
        log.info(
            "HTTP %s %s (%.1fs, %s bytes)",
            response.status_code,
            url,
            time.perf_counter() - started,
            len(response.content),
        )
        return response.content

    def get_json(
        self,
        url: str,
        extra_headers: dict[str, str] | None = None,
        etag: str | None = None,
    ) -> tuple[Any | None, str | None, bool]:
        headers = dict(extra_headers or {})
        if etag:
            headers["If-None-Match"] = etag
        started = time.perf_counter()
        log.info("HTTP GET %s", url)
        response = self._client.get(url, headers=self._headers(url, headers))
        elapsed = time.perf_counter() - started
        if response.status_code == 304:
            log.info("HTTP 304 %s (%.1fs)", url, elapsed)
            return None, etag, True
        self._raise_for_status(response, url)
        log.info("HTTP %s %s (%.1fs)", response.status_code, url, elapsed)
        new_etag = response.headers.get("ETag")
        if not response.content:
            return None, new_etag, False
        return response.json(), new_etag, False

    def download(self, url: str, dest: Path, progress: ProgressFn | None = None) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        log.info("HTTP download %s -> %s", url, dest)
        headers = self._headers(url, {"Accept": "application/octet-stream"})
        stream_timeout = httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with self._client.stream("GET", url, headers=headers, timeout=stream_timeout) as response:
                self._raise_for_status(response, url)
                total = int(response.headers.get("Content-Length") or 0)
                encoding = (response.headers.get("Content-Encoding") or "").lower()
                skip_length_check = any(item in encoding for item in ("gzip", "br", "deflate"))
                done = 0
                last_report = 0
                with tmp.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
                        done += len(chunk)
                        if not progress:
                            continue
                        if total:
                            pct = min(100, int(done * 100 / total))
                            if pct != last_report:
                                last_report = pct
                                progress(f"Downloading {dest.name} ({pct}%)")
                        elif done - last_report >= 256 * 1024:
                            last_report = done
                            progress(f"Downloading {dest.name} ({done / (1024 * 1024):.1f} MB)")
                if done <= 0:
                    raise HttpError(f"Download of {dest.name} was empty")
                if total and not skip_length_check and done != total:
                    raise HttpError(
                        f"Incomplete download of {dest.name}: got {done} of {total} bytes"
                    )
                tmp.replace(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        log.info(
            "HTTP download finished %s (%s bytes, %.1fs)",
            dest.name,
            dest.stat().st_size if dest.exists() else done,
            time.perf_counter() - started,
        )

    def _headers(self, url: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if self.token and url_needs_api_token(url):
            headers.setdefault("Authorization", f"Bearer {self.token}")
        return headers

    def _raise_for_status(self, response: httpx.Response, url: str) -> None:
        if response.status_code == 403 and "rate limit" in response.text.lower():
            log.warning("GitHub rate limit for %s", url)
            raise HttpError(
                "GitHub API rate limit exceeded. Add a token in Settings.",
                status_code=403,
            )
        if response.is_error:
            log.warning("HTTP %s for %s: %s", response.status_code, url, response.text[:300])
            raise HttpError(
                f"HTTP {response.status_code} for {url}: {response.text[:300]}",
                status_code=response.status_code,
            )
