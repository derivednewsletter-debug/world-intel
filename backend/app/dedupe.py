"""Title normalization, dedupe keys, severity scoring, category refinement."""
import hashlib
import re

_BOOSTS = [
    (re.compile(r"magnitude\s*[6-9]", re.I), 4),
    (re.compile(r"magnitude\s*5", re.I), 3),
    (re.compile(r"earthquake", re.I), 1),
    (re.compile(r"red alert", re.I), 4),
    (re.compile(r"orange alert", re.I), 3),
    (re.compile(r"hurricane|cyclone|typhoon", re.I), 2),
    (re.compile(r"tsunami", re.I), 3),
    (re.compile(r"wildfire|volcano|eruption", re.I), 2),
    (re.compile(r"flood|flooding", re.I), 1),
    (re.compile(r"killed|deaths|deadliest|massacre", re.I), 2),
    (re.compile(r"war|invasion|missile|airstrike|air strike", re.I), 2),
    (re.compile(r"ceasefire|truce", re.I), 1),
    (re.compile(r"cyberattack|ransomware|data breach", re.I), 2),
    (re.compile(r"outage|blackout", re.I), 1),
    (re.compile(r"port congestion|supply chain|freight", re.I), 1),
    (re.compile(r"crash|plunge|surge|soar", re.I), 1),
]

_CATEGORY_RULES = [
    ("conflict", re.compile(r"\b(war|wars|invasion|missile|airstrike|air strike|ceasefire|troops|military|rebel|insurgent|protest|riot|battle|shelling|bombing|escalation|offensive)\b", re.I)),
    ("disaster", re.compile(r"\b(earthquake|wildfire|flood|flooding|hurricane|cyclone|typhoon|volcano|eruption|tsunami|landslide|mudslide|avalanche|famine)\b", re.I)),
    ("weather", re.compile(r"\b(blizzard|heatwave|heat wave|drought|tornado|monsoon|freezing|snowstorm|extreme weather)\b", re.I)),
    ("tech", re.compile(r"\b(cyberattack|cyber attack|ransomware|data breach|hacking|hacked|outage|blackout|artificial intelligence|\bai\b|semiconductor|chip maker|microchip)\b", re.I)),
    ("energy", re.compile(r"\b(oil price|crude oil|opec|natural gas|lng|energy crisis|refinery|gas prices|petrol)\b", re.I)),
    ("supplychain", re.compile(r"\b(port congestion|freight|container ship|container shipping|supply chain|logistics|suez|panama canal|red sea shipping|strike at|shipping rates)\b", re.I)),
    ("markets", re.compile(r"\b(stock market|wall street|inflation|interest rate|central bank|recession|gdp|treasury yields|nasdaq|s&p 500|dow jones|dow closes)\b", re.I)),
    ("health", re.compile(r"\b(outbreak|epidemic|pandemic|vaccine|virus|disease|hospital|who says|health officials)\b", re.I)),
]


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()[:120]


def event_id(title: str, url: str = "") -> str:
    base = f"{normalize_title(title)}|{re.sub(r'^https?://', '', url.lower())}"
    return hashlib.sha1(base.encode()).hexdigest()


def compute_severity(base: int, title: str) -> int:
    s = base
    for pattern, boost in _BOOSTS:
        if pattern.search(title):
            s += boost
    return max(0, min(5, round(s)))


def refine_category(category: str, title: str) -> str:
    if category != "news":
        return category
    for new_cat, pattern in _CATEGORY_RULES:
        if pattern.search(title):
            return new_cat
    return category
