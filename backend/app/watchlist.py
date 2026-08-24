"""Effective watchlist.

The watchlist drives the AI's alerts, the dynamic watch feed, and push
notifications. Users can edit it from the website (stored in the DB) — when a
DB override exists it wins; otherwise the config defaults apply.
"""
import json

from . import db
from .config import WATCHLIST_DEFAULTS

_KV_KEY = "watchlist"


def _clean_terms(terms) -> list:
    out = []
    for t in terms or []:
        s = str(t).strip().lower()
        if s and s not in out:
            out.append(s)
    return out


def effective_watchlist() -> dict:
    """The watchlist in effect: DB override if present, else config defaults."""
    raw = db.get_kv(_KV_KEY)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and (data.get("countries") or data.get("keywords")):
                return {
                    "countries": _clean_terms(data.get("countries")),
                    "keywords": _clean_terms(data.get("keywords")),
                    "min_severity": int(data.get("min_severity") or WATCHLIST_DEFAULTS["min_severity"]),
                }
        except (ValueError, TypeError):
            pass
    return dict(WATCHLIST_DEFAULTS)


def save_watchlist(countries, keywords, min_severity=None) -> dict:
    """Validate and persist a watchlist override; returns the saved value."""
    wl = {
        "countries": _clean_terms(countries),
        "keywords": _clean_terms(keywords),
        "min_severity": int(min_severity) if min_severity is not None else WATCHLIST_DEFAULTS["min_severity"],
    }
    wl["min_severity"] = max(1, min(5, wl["min_severity"]))
    db.set_kv(_KV_KEY, json.dumps(wl))
    return wl


def reset_watchlist() -> dict:
    """Drop the override and return the config defaults."""
    db.set_kv(_KV_KEY, "")
    return dict(WATCHLIST_DEFAULTS)
