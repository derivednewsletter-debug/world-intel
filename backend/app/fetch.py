"""HTTP helpers — httpx with timeout, user agent, one retry, and circuit breaker.

The circuit breaker tracks failures per host domain. After 5 consecutive
failures to a host, requests to that host are short-circuited for 60s to
avoid wasting time on a known-dead endpoint (e.g. rate-limited GDELT).
"""
import json
import threading
import time
from urllib.parse import urlparse

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


class JsonDecodeError(Exception):
    """Raised when a response isn't valid JSON — includes the URL for debugging."""
    pass


class CircuitOpen(Exception):
    """Raised when the circuit breaker is open for a host."""
    pass


# Circuit breaker state: host → (failures, open_until_epoch)
_circuit: dict[str, tuple[int, float]] = {}
_circuit_lock = threading.Lock()
_CIRCUIT_THRESHOLD = 5      # consecutive failures to trip
_CIRCUIT_COOLDOWN = 60.0    # seconds to keep circuit open


def _circuit_key(url: str) -> str:
    try:
        return urlparse(url).hostname or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _check_circuit(url: str) -> None:
    key = _circuit_key(url)
    with _circuit_lock:
        failures, open_until = _circuit.get(key, (0, 0.0))
    if failures >= _CIRCUIT_THRESHOLD and time.time() < open_until:
        raise CircuitOpen(f"Circuit breaker open for {key} — too many failures")


def _record_failure(url: str) -> None:
    key = _circuit_key(url)
    with _circuit_lock:
        failures, _ = _circuit.get(key, (0, 0.0))
        failures += 1
        if failures >= _CIRCUIT_THRESHOLD:
            _circuit[key] = (failures, time.time() + _CIRCUIT_COOLDOWN)
        else:
            _circuit[key] = (failures, 0.0)


def _record_success(url: str) -> None:
    key = _circuit_key(url)
    with _circuit_lock:
        _circuit[key] = (0, 0.0)


def fetch_text(url: str, timeout_ms: int = 20000, headers: dict | None = None) -> str:
    _check_circuit(url)

    def _attempt() -> str:
        res = _client.get(url, timeout=timeout_ms / 1000, headers=headers)
        if res.status_code >= 400:
            raise HttpError(res.status_code, f"{res.status_code} for {url}")
        return res.text

    try:
        result = _attempt()
        _record_success(url)
        return result
    except CircuitOpen:
        raise
    except HttpError as err:
        _record_failure(url)
        if err.status < 500:
            raise
        # fall through to retry for 5xx
        time.sleep(1.5)
        result = _attempt()
        _record_success(url)
        return result
    except (httpx.HTTPError, OSError):
        _record_failure(url)
        # network blip — retry once
        time.sleep(1.5)
        result = _attempt()
        _record_success(url)
        return result


def fetch_json(url: str, timeout_ms: int = 20000, headers: dict | None = None):
    raw = fetch_text(url, timeout_ms, headers)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise JsonDecodeError(f"Invalid JSON from {url}: {err}") from err


def sleep(ms: float) -> None:
    time.sleep(ms / 1000)
