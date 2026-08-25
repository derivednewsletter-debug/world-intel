"""Disaster collectors — NASA EONET, USGS earthquakes, GDACS alerts (all keyless)."""
import calendar
import time

import feedparser

from ..db import set_source_status, upsert_events_batch
from ..dedupe import compute_severity, event_id
from ..eventhub import hub
from ..fetch import fetch_json, fetch_text
from ..util import parse_published, strip_html, to_float

EONET_CATEGORY_MAP = {
    "severeStorms": "weather",
    "seaLakeIce": "weather",
    "drought": "weather",
    "dustHaze": "weather",
    "snow": "weather",
    "tempExtremes": "weather",
    "wildfires": "disaster",
    "volcanoes": "disaster",
    "earthquakes": "disaster",
    "floods": "disaster",
    "landslides": "disaster",
    "manmade": "news",
    "waterColor": "news",
}


def collect_eonet() -> int:
    data = fetch_json("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=50")
    events = []
    for e in data.get("events") or []:
        coords = None
        for g in e.get("geometry") or []:
            if g.get("type") == "Point" and g.get("coordinates") and len(g["coordinates"]) >= 2:
                coords = g["coordinates"]
                break
        geo_date = (e.get("geometry") or [{}])[0].get("date")
        first_source = (e.get("sources") or [{}])[0].get("url")
        published = _parse_date(geo_date)  # EONET has custom date format
        category = EONET_CATEGORY_MAP.get((e.get("categories") or [{}])[0].get("id", ""), "disaster")
        summary = e.get("description")
        if not summary and e.get("closed") is None:
            summary = "Active event (NASA EONET)"
        events.append({
            "id": event_id(e.get("title", ""), first_source or e.get("id", "")),
            "source": "eonet",
            "category": category,
            "severity": compute_severity(3, e.get("title", "")),
            "title": e.get("title", ""),
            "url": first_source or e.get("link"),
            "summary": summary,
            "published": published,
            "geo": {"lat": coords[1], "lon": coords[0], "place": e.get("title", "")} if coords else None,
        })
    n, inserted = upsert_events_batch(events)
    if inserted:
        hub.publish_batch(inserted)
    return n


def _parse_date(s) -> int:
    if not s:
        return int(time.time() * 1000)
    try:
        # ISO 8601 with optional fractional seconds / Z offset
        t = calendar.timegm(time.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S"))
        return int(t * 1000)
    except (ValueError, OverflowError):
        return int(time.time() * 1000)


def collect_usgs() -> int:
    from urllib.parse import quote
    start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 24 * 3600))
    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
        f"&starttime={quote(start)}&minmagnitude=4.5&orderby=time&limit=100"
    )
    data = fetch_json(url)
    events = []
    for f in data.get("features") or []:
        props = f.get("properties") or {}
        mag = props.get("mag") or 0
        place = props.get("place") or "Unknown location"
        title = f"Earthquake M{mag:.1f} — {place}"
        base = 5 if mag >= 6 else 4 if mag >= 5.5 else 3 if mag >= 5 else 2
        coords = (f.get("geometry") or {}).get("coordinates") or []
        events.append({
            "id": event_id(title, props.get("url") or ""),
            "source": "usgs",
            "category": "disaster",
            "severity": compute_severity(base, title),
            "title": title,
            "url": props.get("url"),
            "published": props.get("time") or int(time.time() * 1000),
            "geo": {"lat": coords[1], "lon": coords[0], "place": place} if len(coords) >= 2 else None,
        })
    n, inserted = upsert_events_batch(events)
    if inserted:
        hub.publish_batch(inserted)
    return n


def collect_gdacs() -> int:
    xml = fetch_text("https://www.gdacs.org/xml/rss.xml")
    feed = feedparser.parse(xml)
    events = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        lower = title.lower()
        level = 4 if "red alert" in lower else 3 if "orange alert" in lower else 2 if "green alert" in lower else 1
        lat = to_float(entry.get("geo_lat") or entry.get("geo:lat"))
        lon = to_float(entry.get("geo_long") or entry.get("geo:long"))
        published = parse_published(entry)
        events.append({
            "id": event_id(title, entry.get("link") or ""),
            "source": "gdacs",
            "category": "disaster",
            "severity": compute_severity(level, title),
            "title": title,
            "url": entry.get("link"),
            "summary": strip_html(entry.get("summary") or ""),
            "published": published,
            "geo": {"lat": lat, "lon": lon} if lat is not None and lon is not None else None,
        })
    n, inserted = upsert_events_batch(events)
    if inserted:
        hub.publish_batch(inserted)
    return n



def run_disasters() -> None:
    jobs = [
        ("eonet", collect_eonet),
        ("usgs", collect_usgs),
        ("gdacs", collect_gdacs),
    ]
    for name, fn in jobs:
        try:
            n = fn()
            set_source_status(name, True, count=n)
        except Exception as err:  # noqa: BLE001
            set_source_status(name, False, last_error=str(err)[:200])
