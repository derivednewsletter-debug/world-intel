"""WHO Disease Outbreak News — keyless RSS feed of global health alerts.

Collects from the WHO Disease Outbreak News (DON) feed, which covers
outbreaks, epidemics, and health emergencies worldwide.  Events land in
the health category so they show on the map and health tab.

Feed: https://www.who.int/feeds/entity/don/en/rss.xml
"""

import re

from ..db import set_source_status, upsert_events_batch
from ..dedupe import compute_severity, event_id
from ..eventhub import hub
from ..fetch import fetch_text
from ..util import parse_published, strip_html

WHO_DON_URL = "https://www.who.int/feeds/entity/don/en/rss.xml"

# Approximate country centroids (lat, lon, place_name) for map markers.
# WHO DON titles often mention the country, e.g. "Cholera — Sudan".
_COUNTRY_COORDS = {
    "afghanistan": (33.9, 67.7), "algeria": (28.0, 1.7), "angola": (-11.2, 17.9),
    "argentina": (-38.4, -63.6), "australia": (-25.3, 133.8),
    "bangladesh": (23.7, 90.4), "belarus": (53.7, 27.9),
    "bolivia": (-16.3, -63.6), "brazil": (-14.2, -51.9),
    "burkina faso": (12.4, -1.6), "burundi": (-3.4, 29.9),
    "cambodia": (12.6, 105.0), "cameroon": (7.4, 12.4),
    "canada": (56.1, -106.3), "central african republic": (6.6, 20.9),
    "chad": (15.5, 18.7), "chile": (-35.7, -71.5),
    "china": (35.9, 104.2), "colombia": (4.6, -74.3),
    "congo": (-0.2, 15.8), "costa rica": (10.0, -84.0),
    "cuba": (21.5, -77.8), "democratic republic": (-4.0, 21.8),
    "dominican republic": (18.7, -70.2), "ecuador": (-1.8, -78.2),
    "egypt": (26.8, 30.8), "ethiopia": (9.1, 40.5),
    "gabon": (-0.8, 11.6), "gambia": (13.4, -15.3),
    "ghana": (7.9, -1.0), "guatemala": (15.8, -90.2),
    "guinea": (9.9, -11.7), "guinea-bissau": (12.0, -15.2),
    "haiti": (18.9, -72.3), "honduras": (15.2, -86.2),
    "india": (20.6, 78.9), "indonesia": (-0.8, 113.9),
    "iran": (32.4, 53.7), "iraq": (33.2, 43.7),
    "ivory coast": (7.5, -5.5), "jamaica": (18.1, -77.3),
    "jordan": (30.6, 36.2), "kazakhstan": (48.0, 68.0),
    "kenya": (-0.0, 37.9), "korea": (35.9, 127.8),
    "laos": (19.9, 102.5), "lebanon": (33.9, 35.9),
    "lesotho": (-29.6, 28.2), "liberia": (6.4, -9.4),
    "libya": (26.3, 17.2), "madagascar": (-18.8, 46.9),
    "malawi": (-13.3, 34.3), "malaysia": (4.2, 101.9),
    "mali": (17.6, -4.0), "mauritania": (21.0, -10.9),
    "mexico": (23.6, -102.6), "mozambique": (-18.7, 35.5),
    "myanmar": (21.9, 95.9), "nepal": (28.4, 84.1),
    "nicaragua": (12.9, -85.2), "niger": (17.6, 8.1),
    "nigeria": (9.1, 8.7), "pakistan": (30.4, 69.3),
    "palestine": (31.9, 35.2), "papua new guinea": (-6.3, 143.9),
    "peru": (-9.2, -75.0), "philippines": (12.9, 121.8),
    "saudi arabia": (23.9, 45.1), "senegal": (14.5, -14.5),
    "sierra leone": (8.5, -11.8), "somalia": (5.2, 46.2),
    "south africa": (-30.6, 22.9), "south sudan": (6.9, 31.3),
    "sri lanka": (7.9, 80.8), "sudan": (12.9, 30.2),
    "syria": (34.8, 39.0), "taiwan": (23.7, 120.9),
    "tanzania": (-6.4, 34.9), "thailand": (15.9, 100.9),
    "togo": (8.6, 1.2), "tunisia": (33.9, 9.5),
    "turkey": (38.9, 35.2), "uganda": (1.4, 32.3),
    "ukraine": (48.4, 31.2), "united arab emirates": (23.4, 53.8),
    "united kingdom": (55.4, -3.4), "united states": (37.1, -95.7),
    "uzbekistan": (41.4, 64.6), "venezuela": (6.4, -66.6),
    "vietnam": (14.1, 108.3), "yemen": (15.6, 48.5),
    "zambia": (-13.1, 27.8), "zimbabwe": (-19.0, 29.2),
}

# Keywords that bump severity for health events.
_SEVERITY_KEYWORDS = {
    "pandemic": 4, "outbreak": 3, "epidemic": 3, "emergency": 3,
    "death": 2, "deaths": 2, "fatal": 2, "fatalities": 2,
    "novel": 2, "new strain": 3, "mutation": 2,
    "avian influenza": 2, "h5n1": 2, "h7n9": 2, "ebola": 3,
    "marburg": 3, "nipah": 3, "mpox": 2, "monkeypox": 2,
    "cholera": 2, "plague": 2, "mers": 2, "sars": 2,
    "vaccine": 1, "who says": 1,
}


def _geocode_title(title: str) -> dict | None:
    """Try to find a country name in the title and return approximate coordinates."""
    lower = title.lower()
    # Try longest country names first to avoid partial matches
    # (e.g. "south africa" before "south" or "africa").
    for name in sorted(_COUNTRY_COORDS, key=len, reverse=True):
        if name in lower:
            lat, lon = _COUNTRY_COORDS[name]
            return {"lat": lat, "lon": lon, "place": name.title()}
    return None


def _health_severity(title: str, summary: str) -> int:
    """Compute a base severity for a health event from keyword matches."""
    text = f"{title} {summary}".lower()
    base = 2  # health events start at 2 (notable by default)
    for kw, boost in _SEVERITY_KEYWORDS.items():
        if kw in text:
            base = max(base, boost)
    return base


def _extract_entries(xml: str) -> list:
    """Parse WHO DON RSS XML into event dicts."""
    import feedparser
    feed = feedparser.parse(xml)
    events = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        link = entry.get("link") or ""
        summary_raw = entry.get("summary") or entry.get("description") or ""
        summary = strip_html(summary_raw)
        published = parse_published(entry)
        base = _health_severity(title, summary or "")
        geo = _geocode_title(title)
        events.append({
            "id": event_id(title, link),
            "source": "who-don",
            "category": "health",
            "severity": compute_severity(base, title),
            "title": title,
            "url": link,
            "summary": summary,
            "published": published,
            "geo": geo,
        })
    return events


def collect_who_outbreak() -> int:
    """Fetch and store WHO Disease Outbreak News events."""
    xml = fetch_text(WHO_DON_URL, timeout_ms=30000)
    events = _extract_entries(xml)
    n, inserted = upsert_events_batch(events)
    if inserted:
        hub.publish_batch(inserted)
    return n


def run_who_outbreak() -> None:
    try:
        n = collect_who_outbreak()
        set_source_status("who-don", True, count=n)
    except Exception as err:  # noqa: BLE001
        set_source_status("who-don", False, last_error=str(err)[:200])
