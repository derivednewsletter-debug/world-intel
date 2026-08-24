"""NOAA SWPC space weather — solar flares, geomagnetic storms, radio blackouts.

Keyless JSON feed (services.swpc.noaa.gov/products/alerts.json). Alerts carry a
message type (Warning > Alert > Watch > Summary) and a short technical message.
Events land in the weather category so they show on the map/weather tabs.
"""
import time

from ..db import set_source_status, upsert_events_batch
from ..dedupe import compute_severity, event_id
from ..fetch import fetch_json

_ALERTS_URL = "https://services.swpc.noaa.gov/products/alerts.json"

# Message type → base severity 0-5.
_TYPE_SEVERITY = {
    "Warning": 4,
    "Alert": 3,
    "Watch": 2,
    "Summary": 1,
}

MAX_ALERTS = 40


def _parse_iso(s: str) -> int:
    if not s:
        return int(time.time() * 1000)
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, OverflowError):
        return int(time.time() * 1000)


def _first_line(s: str) -> str:
    """First non-empty line of the alert message — the actionable headline."""
    for line in (s or "").splitlines():
        line = line.strip()
        if line:
            return line[:160]
    return ""


def collect_spaceweather() -> int:
    data = fetch_json(_ALERTS_URL, timeout_ms=30000)
    if not isinstance(data, list):
        return 0
    # Newest first, capped at the most recent alerts.
    alerts = sorted(data, key=lambda a: a.get("issue_datetime", ""), reverse=True)[:MAX_ALERTS]
    events = []
    for a in alerts:
        msg_type = (a.get("message_type") or "Summary").strip()
        product = (a.get("product_id") or "").strip()
        message = (a.get("message") or "").strip()
        headline = _first_line(message) or f"{msg_type} — {product}"
        title = f"Space weather {msg_type.lower()}: {headline}"
        if len(title) > 200:
            title = title[:200]
        base = _TYPE_SEVERITY.get(msg_type, 1)
        events.append({
            "id": event_id(title, product or a.get("issue_datetime") or ""),
            "source": "noaa-space-weather",
            "category": "weather",
            "severity": compute_severity(base, title),
            "title": title,
            "url": "https://www.swpc.noaa.gov/",
            "summary": message[:500] or None,
            "published": _parse_iso(a.get("issue_datetime")),
            "geo": None,
        })
    return upsert_events_batch(events)


def run_spaceweather() -> None:
    try:
        n = collect_spaceweather()
        set_source_status("noaa-space-weather", True, count=n)
    except Exception as err:  # noqa: BLE001
        set_source_status("noaa-space-weather", False, last_error=str(err)[:200])
