"""Money — keyless FX rates (open.er-api.com) + crypto prices (CoinGecko).

Values accumulate into the indicators table, so each series grows a history and
the dashboard gets real sparklines over time (FRED series keep their own
server-side history; money series append one point per run).
"""
import time

from ..config import CRYPTO_COINS, FX_CURRENCIES
from ..db import get_indicators, set_indicator, set_source_status
from ..fetch import fetch_json

_FX_URL = "https://open.er-api.com/v6/latest/USD"
_CRYPTO_URL = "https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"

MAX_HISTORY = 240  # ~1 day of 10-min points, or ~8 months of daily FRED points


def _accumulate(series_id: str, name: str, category: str, unit: str,
                value: float, point_date: str | None = None) -> None:
    """Append one point to the series history, replacing the previous point if
    it's identical (same timestamp, same value) so repeated runs don't bloat it."""
    existing = {i["series_id"]: i for i in get_indicators()}
    prev = existing.get(series_id)
    hist = list((prev or {}).get("history") or [])
    point = {"date": point_date or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "value": value}
    if hist and hist[-1].get("date") == point["date"] and hist[-1].get("value") == value:
        hist[-1] = point
    else:
        hist.append(point)
    set_indicator({
        "series_id": series_id,
        "name": name,
        "category": category,
        "unit": unit,
        "latest_value": value,
        "latest_date": point["date"],
        "history": hist[-MAX_HISTORY:],
    })


def collect_fx() -> int:
    data = fetch_json(_FX_URL)
    rates = data.get("rates") or {}
    n = 0
    for cur in FX_CURRENCIES:
        v = rates.get(cur)
        if v is None:
            continue
        _accumulate(f"FX:{cur}", f"USD/{cur}", "money", "rate", float(v))
        n += 1
    return n


def collect_crypto() -> int:
    ids = ",".join(CRYPTO_COINS)
    data = fetch_json(_CRYPTO_URL.format(ids=ids))
    n = 0
    for coin in CRYPTO_COINS:
        d = data.get(coin) or {}
        v = d.get("usd")
        if v is None:
            continue
        label = coin[0].upper() + coin[1:]
        _accumulate(f"CRYPTO:{coin}", f"{label} (USD)", "money", "USD", float(v))
        n += 1
    return n


def run_money() -> None:
    for source, fn in (("money-fx", collect_fx), ("money-crypto", collect_crypto)):
        try:
            n = fn()
            set_source_status(source, True, count=n)
        except Exception as err:  # noqa: BLE001 — one provider failing shouldn't kill the other
            set_source_status(source, False, last_error=str(err)[:200])
