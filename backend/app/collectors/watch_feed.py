"""Dynamic watchlist feed.

Builds a Google News search URL from the *effective* watchlist (your countries
and keywords) and collects it like any other RSS feed. Edit the watchlist on the
website and this feed changes on the next run — your interests become a live,
always-on feed.
"""
from urllib.parse import quote

from ..db import set_source_status
from ..watchlist import effective_watchlist
from .rss import collect_feed_url


def _build_query(wl: dict) -> str:
    terms = wl["keywords"] + wl["countries"]
    return " OR ".join(f'"{t}"' if " " in t else t for t in terms)


def run_watch_feed() -> None:
    try:
        wl = effective_watchlist()
        if not (wl["keywords"] or wl["countries"]):
            set_source_status("watch-feed", True, count=0)
            return
        query = _build_query(wl)
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
        n = collect_feed_url("watch-feed", url, "news")
        set_source_status("watch-feed", True, count=n)
    except Exception as err:  # noqa: BLE001
        set_source_status("watch-feed", False, last_error=str(err)[:200])
