"""Keyword-based sentiment analysis — no ML libraries.

Scores text on a -1.0 (very negative) to +1.0 (very positive) scale using
weighted keyword lists.  Designed for news headlines and summaries where
conflict/disaster language dominates, so the negative lexicon is heavier.

Used by the AI engine to add a sentiment dimension to story clusters and
the briefing — lets the dashboard show whether coverage is getting darker
or lighter over time.
"""

# Each tuple: (keyword, weight).  Weights are roughly:
#   ±0.05  mild / contextual
#   ±0.10  moderate
#   ±0.15  strong
#   ±0.20  very strong

_NEGATIVE = [
    # violence / conflict
    ("killed", 0.15), ("dead", 0.12), ("deaths", 0.15), ("deadliest", 0.18),
    ("massacre", 0.20), ("slaughter", 0.20), ("bombing", 0.15), ("airstrike", 0.12),
    ("shelling", 0.12), ("missile", 0.10), ("attack", 0.10), ("invade", 0.15),
    ("invasion", 0.15), ("war", 0.15), ("conflict", 0.08), ("escalation", 0.10),
    ("troops", 0.05), ("military", 0.05), ("casualties", 0.15), ("wounded", 0.12),
    ("hostage", 0.15), ("siege", 0.12), ("ambush", 0.12),
    # disaster / destruction
    ("earthquake", 0.08), ("tsunami", 0.12), ("wildfire", 0.08), ("hurricane", 0.08),
    ("cyclone", 0.08), ("typhoon", 0.08), ("flood", 0.06), ("flooding", 0.06),
    ("devastation", 0.15), ("destroy", 0.12), ("destroyed", 0.15), ("damage", 0.05),
    ("collapse", 0.08), ("evacuate", 0.08), ("evacuation", 0.08), ("refugee", 0.08),
    ("displaced", 0.08), ("homeless", 0.10), ("rubble", 0.10),
    # economic / market
    ("crash", 0.10), ("plunge", 0.10), ("slump", 0.08), ("recession", 0.10),
    ("default", 0.10), ("bankrupt", 0.12), ("bankruptcy", 0.12), ("crisis", 0.08),
    ("inflation", 0.05), ("unemployment", 0.05), ("shortage", 0.05),
    # cyber / tech
    ("cyberattack", 0.12), ("ransomware", 0.12), ("breach", 0.08), ("outage", 0.06),
    ("hack", 0.08), ("hacked", 0.08), ("disruption", 0.06),
    # general negative
    ("severe", 0.05), ("extreme", 0.05), ("threat", 0.06), ("warn", 0.04),
    ("warning", 0.04), ("alert", 0.03), ("emergency", 0.06), ("panic", 0.10),
    ("chaos", 0.10), ("surge", 0.03), ("soar", 0.03),
]

_POSITIVE = [
    # peace / resolution
    ("ceasefire", 0.15), ("peace", 0.12), ("truce", 0.12), ("deal", 0.08),
    ("agreement", 0.08), ("negotiate", 0.05), ("negotiation", 0.05),
    ("reconcil", 0.08), ("disarm", 0.08),
    # recovery / progress
    ("recover", 0.08), ("recovery", 0.08), ("rescue", 0.08), ("rescued", 0.10),
    ("survive", 0.08), ("survivor", 0.06), ("heal", 0.06), ("rebuild", 0.06),
    ("contained", 0.05), ("controlled", 0.04), ("stable", 0.05),
    # positive economic
    ("rally", 0.08), ("surge", -0.02), ("soar", -0.02), ("boom", 0.08),
    ("growth", 0.06), ("profit", 0.06), ("record high", 0.08), ("recovery", 0.06),
    ("surplus", 0.06), ("breakthrough", 0.10),
    # general positive
    ("success", 0.08), ("victory", 0.08), ("win", 0.06), ("cooperation", 0.06),
    ("humanitarian", 0.03), ("aid", 0.03), ("support", 0.03), ("help", 0.03),
    ("improve", 0.05), ("improvement", 0.05), ("progress", 0.06),
]

# Pre-compile for speed — news text is scanned millions of times per day.
_NEG_PAT = [(kw, w) for kw, w in _NEGATIVE]
_POS_PAT = [(kw, w) for kw, w in _POSITIVE]


def score_text(text: str) -> dict:
    """Score a piece of text for sentiment.

    Returns:
        {"score": float (-1..+1), "label": str, "positive": float, "negative": float}
    """
    if not text:
        return {"score": 0.0, "label": "neutral", "positive": 0.0, "negative": 0.0}

    lower = text.lower()
    pos = 0.0
    neg = 0.0
    for kw, w in _POS_PAT:
        if kw in lower:
            pos += w
    for kw, w in _NEG_PAT:
        if kw in lower:
            neg += w

    # Clamp components to [0, 1] range before combining.
    pos = min(pos, 1.0)
    neg = min(neg, 1.0)
    raw = pos - neg  # range roughly -1..+1
    score = max(-1.0, min(1.0, raw))

    if score > 0.05:
        label = "positive"
    elif score < -0.05:
        label = "negative"
    else:
        label = "neutral"

    return {"score": round(score, 3), "label": label,
            "positive": round(pos, 3), "negative": round(neg, 3)}


def score_events(events: list) -> dict:
    """Aggregate sentiment across a list of events.

    Returns:
        {"average": float, "label": str, "negative_count": int,
         "positive_count": int, "neutral_count": int, "total": int}
    """
    if not events:
        return {"average": 0.0, "label": "neutral", "negative_count": 0,
                "positive_count": 0, "neutral_count": 0, "total": 0}

    scores = []
    neg = pos = neu = 0
    for e in events:
        text = f"{e.get('title', '')} {e.get('summary') or ''}"
        s = score_text(text)
        scores.append(s["score"])
        if s["label"] == "negative":
            neg += 1
        elif s["label"] == "positive":
            pos += 1
        else:
            neu += 1

    avg = sum(scores) / len(scores)
    if avg > 0.05:
        label = "positive"
    elif avg < -0.05:
        label = "negative"
    else:
        label = "neutral"

    return {
        "average": round(avg, 3),
        "label": label,
        "negative_count": neg,
        "positive_count": pos,
        "neutral_count": neu,
        "total": len(events),
    }


def cluster_sentiment(cluster: dict) -> dict:
    """Add sentiment to a story cluster dict (from cluster_events).

    Mutates the cluster in place and returns it.
    """
    samples = cluster.get("sample", [])
    text = " ".join(f"{e.get('title', '')} {e.get('summary') or ''}" for e in samples)
    sentiment = score_text(text)
    cluster["sentiment"] = sentiment
    return cluster


def sentiment_history(events: list, hours: int = 24) -> list:
    """Compute per-hour average sentiment over the last N hours.

    Returns a list of {"hour": epoch_ms, "score": float, "label": str,
    "positive": int, "negative": int, "neutral": int, "total": int} dicts.
    """
    import time
    now_ms = time.time() * 1000
    since_ms = now_ms - hours * 3_600_000
    bucket_ms = 3_600_000  # 1 hour

    # Initialize buckets.
    buckets = []
    for h in range(hours):
        buckets.append({
            "hour": since_ms + h * bucket_ms,
            "scores": [],
            "positive": 0,
            "negative": 0,
            "neutral": 0,
        })

    for e in events:
        pub = e.get("published") or 0
        if pub < since_ms:
            continue
        idx = min(hours - 1, int((pub - since_ms) / bucket_ms))
        text = f"{e.get('title', '')} {e.get('summary') or ''}"
        s = score_text(text)
        buckets[idx]["scores"].append(s["score"])
        buckets[idx][s["label"]] += 1

    out = []
    for b in buckets:
        scores = b["scores"]
        avg = sum(scores) / len(scores) if scores else 0.0
        if avg > 0.05:
            label = "positive"
        elif avg < -0.05:
            label = "negative"
        else:
            label = "neutral"
        out.append({
            "hour": b["hour"],
            "score": round(avg, 3),
            "label": label,
            "positive": b["positive"],
            "negative": b["negative"],
            "neutral": b["neutral"],
            "total": len(scores),
        })
    return out


def timeline_sentiment(timeline: list) -> list:
    """Score each entry in a story timeline for sentiment trend.

    Returns a list of {"published": ..., "title": ..., "sentiment": {...}} dicts.
    """
    out = []
    for entry in timeline:
        text = f"{entry.get('title', '')} {entry.get('summary') or ''}"
        sentiment = score_text(text)
        out.append({**entry, "sentiment": sentiment})
    return out
