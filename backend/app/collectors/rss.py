"""RSS/Atom collectors — direct publisher feeds + Google News topic/site/search feeds."""
import calendar
import re
import time

import feedparser

from ..config import ALL_RSS_SOURCES
from ..db import set_source_status, upsert_event
from ..dedupe import compute_severity, event_id, refine_category
from ..fetch import fetch_text

_IMG_TAG = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
_HTML_TAG = re.compile(r"<[^>]+>")

# Reddit blocks generic bot UAs — a browser UA dramatically reduces 429s.
_REDDIT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _first_url(value):
    if isinstance(value, str):
        return value if value.startswith("http") else None
    if isinstance(value, list):
        for x in value:
            r = _first_url(x)
            if r:
                return r
        return None
    if isinstance(value, dict):
        u = value.get("url")
        if isinstance(u, str) and u.startswith("http"):
            return u
        # feedparser nests media_group items under "content"
        return _first_url(value.get("content"))
    return None


def _extract_image(entry) -> str | None:
    # feedparser normalizes media:content / media:thumbnail / media:group.
    for field in ("media_content", "media_thumbnail", "media_group"):
        v = entry.get(field)
        if v:
            u = _first_url(v)
            if u:
                return u
    for enc in entry.get("enclosures", []) or []:
        href = enc.get("href") or enc.get("url")
        if isinstance(href, str) and href.startswith("http"):
            return href
    for link in entry.get("links", []) or []:
        if link.get("rel") in ("enclosure", "image", "thumbnail"):
            href = link.get("href")
            if isinstance(href, str) and href.startswith("http"):
                return href
    # Fall back to the first <img> inside content HTML.
    html = entry.get("content")
    if isinstance(html, list):
        html = "".join(x.get("value", "") for x in html if isinstance(x, dict))
    if not isinstance(html, str):
        html = entry.get("summary") or ""
    m = _IMG_TAG.search(html or "")
    return m.group(1) if m else None


def _parse_published(entry) -> int:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return int(calendar.timegm(t) * 1000)
            except (ValueError, OverflowError, TypeError):
                pass
    return int(time.time() * 1000)


def _plain_summary(entry) -> str | None:
    raw = entry.get("summary") or ""
    if isinstance(raw, list):
        raw = "".join(x.get("value", "") for x in raw if isinstance(x, dict))
    if not raw:
        return None
    return _HTML_TAG.sub(" ", raw).strip()[:500] or None


def collect_feed_url(name: str, url: str, category: str) -> int:
    """Collect a single feed by name/url — used by the dynamic watchlist feed."""
    return collect_feed({"name": name, "url": url, "category": category})


def collect_feed(src: dict) -> int:
    headers = None
    if src["name"].startswith("reddit-"):
        headers = {"User-Agent": _REDDIT_UA}
    xml = fetch_text(src["url"], headers=headers)
    feed = feedparser.parse(xml)
    n = 0
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        link = entry.get("link")
        ev = {
            "id": event_id(title, link or ""),
            "source": src["name"],
            "category": refine_category(src["category"], title),
            "severity": compute_severity(1, title),
            "title": title,
            "url": link,
            "summary": _plain_summary(entry),
            "image": _extract_image(entry),
            "published": _parse_published(entry),
        }
        if upsert_event(ev):
            n += 1
    return n


def run_rss() -> None:
    # Google News + Reddit RSS dislike bursts — requests run sequentially with a
    # short politeness pause after Reddit feeds (they 429 aggressive clients).
    for src in ALL_RSS_SOURCES:
        try:
            n = collect_feed(src)
            set_source_status(src["name"], True, count=n)
        except Exception as err:  # noqa: BLE001 — one bad feed must never kill the run
            set_source_status(src["name"], False, last_error=str(err)[:200])
        if src["name"].startswith("reddit-"):
            time.sleep(1.5)
