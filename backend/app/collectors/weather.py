"""NOAA NWS weather alerts — live severe-weather warnings (keyless).

Uses api.weather.gov (the legacy alerts.weather.gov host blocks many networks).
Their API requires a descriptive User-Agent, which fetch.py already sends.
Only alerts that are actually in effect (`status=actual`) are collected, and the
run is capped at the most severe alerts so the feed doesn't flood.
"""
import time
from urllib.parse import quote

from ..db import set_source_status, upsert_events_batch
from ..dedupe import compute_severity, event_id
from ..eventhub import hub
from ..fetch import fetch_json

_ALERTS_URL = "https://api.weather.gov/alerts/active?status=actual"

# Map NWS severity → base severity 0-5.
_SEVERITY = {
    "Extreme": 4,
    "Severe": 3,
    "Moderate": 2,
    "Minor": 1,
    "Unknown": 1,
}

MAX_ALERTS = 60


def _centroid(coords) -> tuple | None:
    """First point of the first polygon ring — a representative location."""
    ring = coords
    if ring and isinstance(ring[0], list) and len(ring[0]) == 2:
        return ring[0][1], ring[0][0]  # GeoJSON is [lon, lat]
    return None


def _clean(s) -> str | None:
    if not s:
        return None
    return s.strip()[:500] or None


def collect_weather() -> int:
    data = fetch_json(_ALERTS_URL, timeout_ms=30000)
    features = data.get("features") or []
    # Sort by severity so the cap keeps the most serious warnings.
    features.sort(
        key=lambda f: _SEVERITY.get((f.get("properties") or {}).get("severity", "Unknown"), 0),
        reverse=True,
    )
    events = []
    for f in features[:MAX_ALERTS]:
        p = f.get("properties") or {}
        event = (p.get("event") or "Weather alert").strip()
        area = p.get("areaDesc") or ""
        # areaDesc is a long "County; County; ..." list — keep the start.
        title = f"{event} — {area.split(';')[0].strip()}" if area else event
        geo = None
        geometry = f.get("geometry") or {}
        if geometry.get("type") == "Polygon" and geometry.get("coordinates"):
            geo = _centroid(geometry["coordinates"][0])
        elif geometry.get("type") == "MultiPolygon" and geometry.get("coordinates"):
            geo = _centroid(geometry["coordinates"][0][0])
        published = _parse_iso(p.get("sent") or p.get("effective"))
        headline = p.get("headline") or title
        description = p.get("description") or ""
        summary = _clean(headline if len(headline) <= 200 else description[:400])
        base = _SEVERITY.get(p.get("severity", "Unknown"), 1)
        events.append({
            "id": event_id(headline, f.get("id") or title),
            "source": "noaa-weather",
            "category": "weather",
            "severity": compute_severity(base, title),
            "title": title,
            "url": p.get("url"),
            "summary": summary,
            "published": published,
            "geo": {"lat": geo[0], "lon": geo[1], "place": area[:60]} if geo else None,
        })
    n, inserted = upsert_events_batch(events)
    if inserted:
        hub.publish_batch(inserted)
    return n


def _parse_iso(s) -> int:
    if not s:
        return int(time.time() * 1000)
    try:
        from datetime import datetime
        # "2026-08-22T18:32:00-04:00" (fromisoformat handles the offset)
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, OverflowError):
        return int(time.time() * 1000)


def run_weather() -> None:
    try:
        n = collect_weather()
        set_source_status("noaa-weather", True, count=n)
    except Exception as err:  # noqa: BLE001
        set_source_status("noaa-weather", False, last_error=str(err)[:200])
