"""Slack / Discord webhook integration — sends alerts to chat channels.

Both Slack and Discord accept the same JSON format for incoming webhooks:
  {"content": "message text"}  (Discord)
  {"text": "message text"}     (Slack)

We send both keys so the same payload works with either service.

Configuration is stored in the DB kv table:
  webhook_url      — the incoming webhook URL
  webhook_enabled  — "1" to enable, "0" to disable
  webhook_events   — JSON list of event categories to forward (empty = all)
  webhook_min_severity — minimum severity to forward (default 4)
"""
import json

import httpx

from .. import db

_KV_URL = "webhook_url"
_KV_ENABLED = "webhook_enabled"
_KV_CATEGORIES = "webhook_events"
_KV_MIN_SEV = "webhook_min_severity"


def get_config() -> dict:
    """Return the current webhook configuration."""
    url = db.get_kv(_KV_URL) or ""
    enabled = db.get_kv(_KV_ENABLED) == "1"
    cats_raw = db.get_kv(_KV_CATEGORIES) or ""
    categories = [c.strip() for c in cats_raw.split(",") if c.strip()] if cats_raw else []
    min_sev_raw = db.get_kv(_KV_MIN_SEV)
    min_severity = int(min_sev_raw) if min_sev_raw and min_sev_raw.isdigit() else 4
    return {
        "url": url,
        "enabled": enabled,
        "categories": categories,
        "min_severity": min_severity,
    }


def save_config(url: str = None, enabled: bool = None,
                categories: list = None, min_severity: int = None) -> dict:
    """Update webhook configuration. Only provided fields are changed."""
    if url is not None:
        db.set_kv(_KV_URL, url)
    if enabled is not None:
        db.set_kv(_KV_ENABLED, "1" if enabled else "0")
    if categories is not None:
        db.set_kv(_KV_CATEGORIES, ",".join(categories))
    if min_severity is not None:
        db.set_kv(_KV_MIN_SEV, str(max(1, min(5, min_severity))))
    return get_config()


def _format_message(event: dict) -> str:
    """Format an event into a Slack/Discord-friendly message."""
    sev = event.get("severity", 0)
    sev_emoji = ["", "ℹ️", "⚠️", "🔶", "🔴", "🚨"][min(sev, 5)]
    cat = event.get("category", "news").upper()
    title = event.get("title", "Event")
    source = event.get("source", "")
    url = event.get("url", "")
    place = (event.get("geo") or {}).get("place", "")

    parts = [f"{sev_emoji} **[{cat}]** {title}"]
    if place:
        parts.append(f"📍 {place}")
    if source:
        parts.append(f"📡 {source}")
    if url:
        parts.append(f"<{url}>")
    return "\n".join(parts)


def send_webhook(event: dict) -> bool:
    """Send a single event to the configured webhook. Returns True on success."""
    cfg = get_config()
    if not cfg["enabled"] or not cfg["url"]:
        return False

    # Filter by category if configured.
    if cfg["categories"] and event.get("category") not in cfg["categories"]:
        return False

    # Filter by severity.
    if event.get("severity", 0) < cfg["min_severity"]:
        return False

    message = _format_message(event)
    # Slack uses "text", Discord uses "content" — send both.
    payload = json.dumps({"text": message, "content": message})

    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.post(cfg["url"], content=payload,
                              headers={"Content-Type": "application/json"})
            return res.status_code in (200, 204)
    except Exception:  # noqa: BLE001
        return False


def send_webhook_batch(events: list) -> int:
    """Send a batch of events. Returns count of successful sends."""
    sent = 0
    for e in events:
        if send_webhook(e):
            sent += 1
    return sent
