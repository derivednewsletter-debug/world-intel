"""World Stress Index — a single 0–100 "how bad is the world right now" gauge.

A transparent weighted composite of five signals, all computed from data the
dashboard already collects (no external service):

  • Event pressure   — severity-weighted volume over the window (weight 0.35)
  • Breaking now     — severity ≥ 4 events in the last 2h            (0.25)
  • Active disasters — disaster-category events in the window        (0.15)
  • Market volatility— VIX if available, else max daily indicator swing (0.15)
  • Watchlist hits   — how active your watchlist terms are           (0.10)

The history is the same formula replayed per hour, so the sparkline shows how
the day has been trending.
"""
import time

_SEV_WEIGHT = {0: 0, 1: 1, 2: 2, 3: 4, 4: 8, 5: 12}

# Score → label thresholds.
_LEVELS = [
    (75, "severe"),
    (55, "high"),
    (30, "elevated"),
    (0, "calm"),
]


def _level(score: int) -> str:
    for threshold, label in _LEVELS:
        if score >= threshold:
            return label
    return "calm"


def _volatility_n(indicators) -> float:
    """VIX if present, otherwise the max daily swing across indicators."""
    for ind in indicators or []:
        if ind.get("series_id") == "VIXCLS" and ind.get("latest_value") is not None:
            return min(max(float(ind["latest_value"]) / 40.0, 0.0), 1.0)
    swings = []
    for ind in indicators or []:
        hist = ind.get("history") or []
        if len(hist) >= 2:
            a = hist[-2].get("value")
            b = hist[-1].get("value")
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b:
                swings.append(abs((b - a) / b))
    return min(max((max(swings) if swings else 0.0) / 0.03, 0.0), 1.0)


def compute_stress(events: list, indicators=None, watch_count: int = 0, hours: int = 24) -> dict:
    """Compute the index over `events` (published in ms) plus optional context."""
    now = time.time() * 1000
    since = now - hours * 3_600_000
    recent = [e for e in events if (e.get("published") or 0) >= since]

    pressure = sum(_SEV_WEIGHT.get(e.get("severity", 0), 0) for e in recent)
    pressure_n = min(pressure / 60.0, 1.0)

    breaking_2h = sum(1 for e in recent
                      if e.get("severity", 0) >= 4 and e["published"] >= now - 2 * 3_600_000)
    breaking_n = min(breaking_2h / 3.0, 1.0)

    disasters = sum(1 for e in recent if e.get("category") == "disaster")
    disasters_n = min(disasters / 12.0, 1.0)

    vol_n = _volatility_n(indicators)

    watch_n = min(max(watch_count, 0) / 8.0, 1.0)

    score = round(100 * (0.35 * pressure_n + 0.25 * breaking_n
                         + 0.15 * disasters_n + 0.15 * vol_n + 0.10 * watch_n))

    # Per-hour history: replay the formula per bucket (local components only).
    buckets = [0] * hours
    breaking_b = [0] * hours
    dis_b = [0] * hours
    for e in recent:
        idx = min(hours - 1, max(0, int((e["published"] - since) / 3_600_000)))
        buckets[idx] += _SEV_WEIGHT.get(e.get("severity", 0), 0)
        if e.get("severity", 0) >= 4:
            breaking_b[idx] += 1
        if e.get("category") == "disaster":
            dis_b[idx] += 1
    history = []
    for idx in range(hours):
        p = min(buckets[idx] / 60.0, 1.0)
        b = min(breaking_b[idx] / 3.0, 1.0)
        d = min(dis_b[idx] / 12.0, 1.0)
        history.append({"hour": since + idx * 3_600_000,
                        "score": round(100 * (0.35 * p + 0.25 * b + 0.15 * d))})

    return {
        "score": score,
        "level": _level(score),
        "components": {
            "pressure": round(pressure_n * 100),
            "breaking": round(breaking_n * 100),
            "disasters": round(disasters_n * 100),
            "volatility": round(vol_n * 100),
            "watchlist": round(watch_n * 100),
        },
        "history": history,
        "hours": hours,
    }


def compute_stress_compare(events: list, indicators=None, watch_count: int = 0,
                           hours: int = 24) -> dict:
    """Compare this period's stress vs the same period last week.

    Returns the current stress, last week's stress, and a delta.
    """
    now_ms = time.time() * 1000
    week_ms = 7 * 24 * 3_600_000

    # Current period.
    current_events = [e for e in events if (e.get("published") or 0) >= now_ms - hours * 3_600_000]
    current = compute_stress(current_events, indicators, watch_count=watch_count, hours=hours)

    # Last week's period (same hours, shifted back 7 days).
    last_week_events = [
        e for e in events
        if (e.get("published") or 0) >= now_ms - week_ms - hours * 3_600_000
        and (e.get("published") or 0) < now_ms - week_ms
    ]
    last_week = compute_stress(last_week_events, indicators=[], watch_count=0, hours=hours)

    delta = current["score"] - last_week["score"]
    if delta > 5:
        trend = "worse"
    elif delta < -5:
        trend = "better"
    else:
        trend = "stable"

    return {
        "current": current,
        "last_week": last_week,
        "delta": round(delta),
        "trend": trend,
    }
