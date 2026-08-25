"""Collector registry."""
from concurrent.futures import ThreadPoolExecutor

from .disasters import run_disasters
from .firms import run_firms
from .fred import run_fred
from .gdelt import run_gdelt_doc, run_gdelt_points
from .money import run_money
from .rss import run_rss
from .spaceweather import run_spaceweather
from .watch_feed import run_watch_feed
from .weather import run_weather
from .who_outbreak import run_who_outbreak

__all__ = [
    "run_rss", "run_gdelt_doc", "run_gdelt_points", "run_disasters",
    "run_fred", "run_firms", "run_weather", "run_spaceweather", "run_watch_feed", "run_money",
    "run_who_outbreak", "run_all",
]


def run_all() -> None:
    """Run every collector once (used at boot and by `python -m app.collect`).

    GDELT jobs run sequentially and last — they share a strict per-IP rate limit.
    Each collector publishes new events to the SSE hub for real-time push.
    """
    _fast = [run_rss, run_disasters, run_weather, run_spaceweather,
             run_watch_feed, run_money, run_who_outbreak]
    _key = [run_fred, run_firms]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(fn) for fn in _fast + _key]
        for f in futures:
            try:
                f.result()
            except Exception:  # noqa: BLE001 — collectors already guard internally
                pass
    run_gdelt_doc()
    run_gdelt_points()
