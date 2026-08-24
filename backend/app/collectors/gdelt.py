"""GDELT collectors — DOC API articles (throttle-aware) + pointdata map points."""
import calendar
import json
from urllib.parse import quote

from ..config import GDELT_DOC_QUERIES, GDELT_EVENT_QUERY
from ..db import is_in_cooldown, set_cooldown, set_source_status, upsert_event
from ..dedupe import compute_severity, event_id, refine_category
from ..fetch import HttpError, fetch_text, sleep

DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT rate limit: 1 request per 5 seconds (enforced loosely — we're conservative).
GDELT_INTERVAL_MS = 6500
MAX_RETRIES = 2
RETRY_BACKOFF_MS = 10000


class RateLimitedError(Exception):
    pass


def _gdelt_fetch_json(url: str) -> dict:
    text = fetch_text(url)
    trimmed = text.strip()
    if not trimmed.startswith("{"):
        # GDELT answers rate-limit violations with a plain-text message.
        raise RateLimitedError("GDELT rate limit: " + trimmed[:120])
    return json.loads(trimmed)


def _with_retry(fn):
    last_err: Exception | None = None
    for _ in range(MAX_RETRIES):
        try:
            return fn()
        except RateLimitedError as err:
            last_err = err
            sleep(RETRY_BACKOFF_MS)
            continue
        except HttpError as err:
            if err.status == 429:
                last_err = err
                sleep(RETRY_BACKOFF_MS)
                continue
            raise
    raise last_err


def _parse_seendate(s: str) -> int:
    if not s or len(s) < 12:
        return int(calendar.timegm(__import__("time").gmtime()) * 1000)
    try:
        y, mo, d, h, mi = int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12])
        sec = int(s[12:14]) if len(s) >= 14 else 0
        return int(calendar.timegm((y, mo, d, h, mi, sec, 0, 0, 0)) * 1000)
    except (ValueError, OverflowError):
        import time
        return int(time.time() * 1000)


def _to_float(v) -> float | None:
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def collect_doc_query(name: str, query: str, category: str) -> int:
    url = (
        f"{DOC_URL}?query={quote(query)}&mode=artlist&format=json"
        f"&maxrecords=75&timespan=1d&sort=datedesc"
    )
    data = _with_retry(lambda: _gdelt_fetch_json(url))
    articles = data.get("articles") or data.get("results") or []
    n = 0
    for a in articles:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        tone = _to_float(a.get("tone"))
        base = 1 + min(2, round(-tone / 5)) if tone is not None and tone < 0 else 1
        domain = a.get("domain") or ""
        summary = None
        if a.get("sourcecountry"):
            summary = f"Reported from {a['sourcecountry']}" + (f" · {domain}" if domain else "")
        elif domain:
            summary = f"Source: {domain}"
        ev = {
            "id": event_id(title, a.get("url") or ""),
            "source": name,
            "category": refine_category(category, title),
            "severity": compute_severity(base, title),
            "title": title,
            "url": a.get("url"),
            "summary": summary,
            "image": a.get("socialimage"),
            "published": _parse_seendate(a.get("seendate") or ""),
        }
        if upsert_event(ev):
            n += 1
    return n


def run_gdelt_doc() -> None:
    if is_in_cooldown("gdelt-doc"):
        return  # throttled recently — back off
    throttled = False
    for q in GDELT_DOC_QUERIES:
        if throttled:
            break
        try:
            n = collect_doc_query(q["name"], q["query"], q["category"])
            set_source_status(q["name"], True, count=n)
        except Exception as err:  # noqa: BLE001
            set_source_status(q["name"], False, last_error=str(err)[:200])
            if isinstance(err, RateLimitedError) or (isinstance(err, HttpError) and err.status == 429):
                throttled = True
                set_cooldown("gdelt-doc", 30)  # don't hammer for the next 30 min
        sleep(GDELT_INTERVAL_MS)


def collect_point_data() -> int:
    url = (
        f"{DOC_URL}?query={quote(GDELT_EVENT_QUERY)}&mode=pointdata"
        f"&format=json&timespan=1d&maxrecords=200"
    )
    data = _with_retry(lambda: _gdelt_fetch_json(url))
    points = data.get("points") or data.get("results") or data.get("events") or []
    n = 0
    for p in points:
        title = (p.get("title") or p.get("name") or "Event").strip()
        lat = _to_float(p.get("lat", p.get("lat_")))
        lon = _to_float(p.get("lon", p.get("lon_")))
        if lat is None or lon is None:
            continue
        tone = _to_float(p.get("tone"))
        base = 2 + min(2, round(-tone / 4)) if tone is not None and tone < 0 else 2
        ev = {
            "id": event_id(title, p.get("url") or f"{lat},{lon}"),
            "source": "gdelt-points",
            "category": "conflict",
            "severity": compute_severity(base, title),
            "title": title,
            "url": p.get("url"),
            "summary": (f"{p.get('type') or 'event'} cluster (GDELT)" if (p.get("desc") or p.get("type")) else None),
            "published": _parse_seendate(p.get("seendate") or ""),
            "geo": {"lat": lat, "lon": lon, "place": title},
        }
        if upsert_event(ev):
            n += 1
    return n


def run_gdelt_points() -> None:
    if is_in_cooldown("gdelt-points"):
        return
    try:
        n = collect_point_data()
        set_source_status("gdelt-points", True, count=n)
    except Exception as err:  # noqa: BLE001
        set_source_status("gdelt-points", False, last_error=str(err)[:200])
        if isinstance(err, RateLimitedError) or (isinstance(err, HttpError) and err.status == 429):
            set_cooldown("gdelt-points", 30)
