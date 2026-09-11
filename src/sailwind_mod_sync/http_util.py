from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from sailwind_mod_sync.constants import USER_AGENT

ProgressFn = Callable[[str], None]
log = logging.getLogger(__name__)


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
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=10.0),
            headers=headers,
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_bytes(self, url: str, extra_headers: dict[str, str] | None = None) -> bytes:
        started = time.perf_counter()
        log.info("HTTP GET %s", url)
        response = self._client.get(url, headers=extra_headers)
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
        response = self._client.get(url, headers=headers)
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
        with self._client.stream("GET", url) as response:
            self._raise_for_status(response, url)
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            last_report = 0
            tmp = dest.with_suffix(dest.suffix + ".part")
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
            tmp.replace(dest)
        log.info(
            "HTTP download finished %s (%s bytes, %.1fs)",
            dest.name,
            dest.stat().st_size if dest.exists() else done,
            time.perf_counter() - started,
        )

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
