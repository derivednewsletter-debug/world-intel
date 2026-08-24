"""HTTP helpers — httpx with timeout, user agent, and one retry on network/5xx errors."""
import json
import time

import httpx

from .config import USER_AGENT

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, application/xml, text/xml, text/plain, */*",
}

_client = httpx.Client(timeout=20.0, follow_redirects=True, headers=_HEADERS)


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def fetch_text(url: str, timeout_ms: int = 20000, headers: dict | None = None) -> str:
    def _attempt() -> str:
        res = _client.get(url, timeout=timeout_ms / 1000, headers=headers)
        if res.status_code >= 400:
            raise HttpError(res.status_code, f"{res.status_code} for {url}")
        return res.text

    try:
        return _attempt()
    except HttpError as err:
        if err.status < 500:
            raise
        # fall through to retry for 5xx
        time.sleep(1.5)
        return _attempt()
    except (httpx.HTTPError, OSError):
        # network blip — retry once
        time.sleep(1.5)
        return _attempt()


def fetch_json(url: str, timeout_ms: int = 20000, headers: dict | None = None):
    return json.loads(fetch_text(url, timeout_ms, headers))


def sleep(ms: float) -> None:
    time.sleep(ms / 1000)
