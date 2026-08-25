"""Shared utility functions for collectors — avoid duplicating tiny helpers."""
import calendar
import re
import time


def parse_iso(s: str) -> int:
    """Parse an ISO 8601 datetime string to epoch milliseconds."""
    if not s:
        return int(time.time() * 1000)
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, OverflowError):
        return int(time.time() * 1000)


def to_float(v) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def parse_published(entry) -> int:
    """Extract published timestamp from an RSS entry as epoch milliseconds."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return int(calendar.timegm(t) * 1000)
            except (ValueError, OverflowError, TypeError):
                pass
    return int(time.time() * 1000)


def strip_html(raw) -> str | None:
    """Strip HTML tags and return plain text, or None if empty."""
    if not raw:
        return None
    if isinstance(raw, list):
        raw = "".join(x.get("value", "") for x in raw if isinstance(x, dict))
    return re.sub(r"<[^>]+>", " ", raw).strip()[:500] or None
