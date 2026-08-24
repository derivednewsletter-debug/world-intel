"""FRED indicator collector — live CPI, rates, oil, freight (needs the free API key)."""
import time
from urllib.parse import quote

from ..config import FRED_API_KEY, FRED_SERIES
from ..db import set_indicator, set_source_status
from ..fetch import fetch_json


def collect_series(series_id: str) -> dict:
    meta = next(s for s in FRED_SERIES if s["series_id"] == series_id)
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={quote(FRED_API_KEY)}"
        "&file_type=json&sort_order=desc&limit=250"
    )
    data = fetch_json(url)
    valid = []
    for o in data.get("observations") or []:
        if o.get("value") == ".":
            continue
        try:
            v = float(o["value"])
        except (TypeError, ValueError):
            continue
        valid.append({"date": o.get("date"), "value": v})
    latest = valid[0] if valid else None
    return {
        "series_id": series_id,
        "name": meta["name"],
        "category": meta["category"],
        "unit": meta.get("unit"),
        "latest_value": latest["value"] if latest else None,
        "latest_date": latest["date"] if latest else None,
        "updated": int(time.time() * 1000),
        "history": list(reversed(valid)),
    }


def run_fred() -> None:
    if not FRED_API_KEY or FRED_API_KEY.startswith("PASTE_"):
        set_source_status(
            "fred",
            False,
            last_error="No FRED API key configured — set FRED_API_KEY in backend/.env",
        )
        return
    for s in FRED_SERIES:
        try:
            ind = collect_series(s["series_id"])
            set_indicator(ind)
            set_source_status(f"fred-{s['series_id']}", True)
        except Exception as err:  # noqa: BLE001
            set_source_status(f"fred-{s['series_id']}", False, last_error=str(err)[:200])
