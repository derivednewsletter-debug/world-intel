"""NASA FIRMS — real-time satellite fire detection.

The API is CSV-only (the JSON endpoint 400s) and each source uses a different
confidence format (MODIS: 0-100 numeric, VIIRS: l/n/h letters), so we parse the
header row generically and normalize. Hotspots are aggregated into 1°×1° cells
and one event is emitted per active cell (top 15).
"""
import math
import time
from urllib.parse import quote

from ..config import FIRMS_API_KEY
from ..db import set_source_status, upsert_events_batch
from ..dedupe import compute_severity, event_id
from ..fetch import fetch_text


def _fetch_fires(source: str) -> list:
    url = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{quote(FIRMS_API_KEY)}/{source}/world/1"
    )
    csv = fetch_text(url, timeout_ms=60000)
    lines = csv.strip().splitlines()
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].split(",")]
    col = {name: headers.index(name) for name in headers}
    li, lo = col.get("latitude", -1), col.get("longitude", -1)
    if li < 0 or lo < 0:
        return []
    ci = col.get("confidence", -1)
    fi = col.get("frp", -1)
    di = col.get("acq_date", -1)

    rows = []
    for line in lines[1:]:
        cols = line.split(",")
        if len(cols) <= max(li, lo):
            continue
        try:
            lat, lon = float(cols[li]), float(cols[lo])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(lat) or not math.isfinite(lon):
            continue
        raw_conf = (cols[ci].strip().lower() if ci >= 0 and ci < len(cols) else "")
        # MODIS: numeric 0-100. VIIRS: letter (l=low, n=nominal, h=high).
        if raw_conf == "h":
            confidence = 90.0
        elif raw_conf == "n":
            confidence = 70.0
        elif raw_conf == "l":
            confidence = 30.0
        else:
            try:
                confidence = float(raw_conf)
            except (TypeError, ValueError):
                confidence = 70.0
        if not math.isfinite(confidence) or confidence < 70:
            continue  # keep nominal+ fires
        try:
            frp = float(cols[fi]) if fi >= 0 and fi < len(cols) else 0.0
        except (TypeError, ValueError):
            frp = 0.0
        day = cols[di].strip() if di >= 0 and di < len(cols) else ""
        rows.append({"lat": lat, "lon": lon, "confidence": confidence, "frp": frp or 0, "day": day})
    return rows


def collect_firms() -> int:
    if not FIRMS_API_KEY or FIRMS_API_KEY.startswith("PASTE_"):
        raise RuntimeError("No FIRMS API key — get a free one at firms.modaps.eosdis.nasa.gov")
    # MODIS (numeric confidence) + VIIRS S-NPP (higher resolution) — merge.
    all_rows = []
    for s in ("MODIS_NRT", "VIIRS_SNPP_NRT"):
        try:
            all_rows.extend(_fetch_fires(s))
        except Exception:  # noqa: BLE001 — one source failing shouldn't kill the other
            pass
    if not all_rows:
        return 0

    cells: dict[str, dict] = {}
    for p in all_rows:
        key = f"{round(p['lat'])}:{round(p['lon'])}"
        cell = cells.setdefault(key, {
            "lat": round(p["lat"]), "lon": round(p["lon"]),
            "n": 0, "max_frp": 0.0, "day": p["day"],
        })
        cell["n"] += 1
        cell["max_frp"] = max(cell["max_frp"], p["frp"])
        if p["day"] > cell["day"]:
            cell["day"] = p["day"]

    top = sorted(cells.values(), key=lambda c: c["n"], reverse=True)[:15]
    events = []
    for c in top:
        title = f"🔥 Fire cluster near ({c['lat']:.1f}°, {c['lon']:.1f}°) — {c['n']} active hotspot(s)"
        base = 4 if c["n"] >= 10 else 3 if c["n"] >= 4 else 2
        day = f" · {c['day']}" if c["day"] else ""
        events.append({
            "id": event_id(title, f"{c['lat']},{c['lon']}"),
            "source": "firms",
            "category": "disaster",
            "severity": compute_severity(base, title),
            "title": title,
            "summary": f"Satellite fire detection (NASA FIRMS) · max FRP {c['max_frp']:.0f} MW{day}",
            "published": int(time.time() * 1000),
            "geo": {"lat": c["lat"] + 0.5, "lon": c["lon"] + 0.5, "place": f"{c['lat']:.1f}°, {c['lon']:.1f}°"},
        })
    return upsert_events_batch(events)


def run_firms() -> None:
    try:
        n = collect_firms()
        set_source_status("firms", True, count=n)
    except Exception as err:  # noqa: BLE001
        set_source_status("firms", False, last_error=str(err)[:200])
