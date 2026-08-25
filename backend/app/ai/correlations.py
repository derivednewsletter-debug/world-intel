"""Correlation engine — finds patterns between economic indicators and event volume.

Cross-correlates FRED indicator history (CPI, oil, VIX, etc.) with per-hour
event counts by category.  Surfaces insights like "oil price spikes tend to
follow Middle East conflict escalation by 2-3 hours" or "VIX rises when
markets events spike."

Pure math on existing data — no external service.
"""
import math
import time


def _pearson(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient between two equal-length lists.

    Returns a value in [-1, 1].  Returns 0.0 if either list has zero variance.
    """
    n = len(x)
    if n < 3:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)
    if var_x == 0 or var_y == 0:
        return 0.0
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    return cov / math.sqrt(var_x * var_y)


def _bucket_events(events: list, hours: int) -> dict[str, list[int]]:
    """Bucket events by category into hourly counts.

    Returns {category: [count_per_hour]} with `hours` buckets.
    """
    now_ms = time.time() * 1000
    since_ms = now_ms - hours * 3_600_000
    bucket_ms = 3_600_000

    cats: dict[str, list[int]] = {}
    for e in events:
        pub = e.get("published") or 0
        if pub < since_ms:
            continue
        cat = e.get("category", "news")
        if cat not in cats:
            cats[cat] = [0] * hours
        idx = min(hours - 1, int((pub - since_ms) / bucket_ms))
        cats[cat][idx] += 1
    return cats


def _indicator_history(ind: dict, hours: int) -> list[float | None]:
    """Extract hourly values from an indicator's history, aligned to `hours` buckets.

    Returns a list of `hours` values (or None where data is missing).
    Uses the most recent `hours` data points from the indicator's history.
    """
    hist = ind.get("history") or []
    if not hist:
        return [None] * hours
    # Take the last `hours` points.
    recent = hist[-hours:]
    values = []
    for p in recent:
        v = p.get("value")
        if isinstance(v, (int, float)):
            values.append(float(v))
        else:
            values.append(None)
    # Pad if shorter than hours.
    while len(values) < hours:
        values.insert(0, None)
    return values


def find_correlations(events: list, indicators: list, hours: int = 24) -> list:
    """Find significant correlations between indicators and event categories.

    Returns a list of dicts sorted by absolute correlation strength:
        [{"indicator": str, "category": str, "correlation": float,
          "direction": "positive"|"negative", "strength": "strong"|"moderate"|"weak",
          "description": str}]
    """
    if not events or not indicators:
        return []

    cat_buckets = _bucket_events(events, hours)
    results = []

    for ind in indicators:
        series_id = ind.get("series_id", "")
        name = ind.get("name", series_id)
        ind_values = _indicator_history(ind, hours)

        # Skip indicators with no numeric data.
        numeric_count = sum(1 for v in ind_values if v is not None)
        if numeric_count < 3:
            continue

        for cat, cat_counts in cat_buckets.items():
            # Align lengths.
            n = min(len(ind_values), len(cat_counts))
            iv = ind_values[:n]
            cc = cat_counts[:n]

            # Replace None with the mean for correlation (listwise deletion would
            # lose too much data with sparse indicators).
            numeric_vals = [v for v in iv if v is not None]
            if len(numeric_vals) < 3:
                continue
            mean_v = sum(numeric_vals) / len(numeric_vals)
            iv_filled = [v if v is not None else mean_v for v in iv]

            # Need variation in both series.
            if len(set(cc)) < 2:
                continue

            corr = _pearson(iv_filled, cc)
            abs_corr = abs(corr)
            if abs_corr < 0.3:
                continue  # too weak to be interesting

            if abs_corr >= 0.6:
                strength = "strong"
            elif abs_corr >= 0.45:
                strength = "moderate"
            else:
                strength = "weak"

            direction = "positive" if corr > 0 else "negative"

            # Generate a human-readable description.
            if direction == "positive":
                desc = f"{name} rises when {cat} events increase"
            else:
                desc = f"{name} falls when {cat} events increase"

            results.append({
                "indicator": name,
                "series_id": series_id,
                "category": cat,
                "correlation": round(corr, 3),
                "direction": direction,
                "strength": strength,
                "description": desc,
            })

    # Sort by absolute correlation, strongest first.
    results.sort(key=lambda r: abs(r["correlation"]), reverse=True)
    return results[:15]  # top 15 correlations
