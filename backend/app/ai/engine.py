"""From-scratch intelligence engine — pure algorithms, no ML libraries.
Runs in milliseconds; powers the briefing, world summary, watchlist and trends."""
import math
import re
import time

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at", "by", "from", "as",
    "is", "are", "was", "were", "be", "been", "has", "have", "had", "will", "would", "could", "should",
    "it", "its", "his", "her", "their", "they", "them", "he", "she", "we", "you", "i", "this", "that",
    "these", "those", "not", "no", "but", "after", "before", "over", "under", "into", "during", "amid",
    "says", "said", "report", "reports", "reported", "news", "new", "first", "latest", "update", "updates",
    "us", "uk", "un", "eu", "u", "s", "vs", "de", "la", "le", "el", "who", "what", "when", "where", "why",
    "video", "photos", "breaking", "just", "one", "two", "three", "day", "week", "month", "year",
}


def tokenize(text: str) -> list:
    return [t for t in re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split() if len(t) > 3 and t not in STOPWORDS]


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

CLUSTER_SIM = 0.38


def cluster_events(events: list) -> list:
    clusters = []  # list of (tokens, events)
    for ev in events:
        toks = set(tokenize(ev["title"]))
        best, best_sim = -1, CLUSTER_SIM
        for i, (ctoks, _) in enumerate(clusters):
            sim = jaccard(ctoks, toks)
            if sim > best_sim:
                best_sim, best = sim, i
        if best >= 0:
            clusters[best][1].append(ev)
        else:
            clusters.append((toks, [ev]))

    now = time.time() * 1000
    out = []
    for _, evs in clusters:
        evs_sorted = sorted(evs, key=lambda e: e["published"], reverse=True)
        rep = max(evs_sorted, key=lambda e: (e["severity"], e["published"]))
        last_hour = sum(1 for e in evs if e["published"] > now - 3_600_000)
        out.append({
            "id": rep["id"],
            "title": rep["title"],
            "category": rep["category"],
            "severity": max(e["severity"] for e in evs),
            "count": len(evs),
            "sources": sorted({e["source"] for e in evs}),
            "categories": sorted({e["category"] for e in evs}),
            "first_seen": min(e["published"] for e in evs),
            "last_seen": max(e["published"] for e in evs),
            "momentum": (last_hour / len(evs)) if evs else 0,
            "sample": evs_sorted[:5],
            "timeline": [{"published": e["published"], "title": e["title"], "source": e["source"],
                           "url": e.get("url"), "severity": e["severity"]}
                          for e in sorted(evs, key=lambda e: e["published"])][:20],
        })
    return sorted(out, key=score_cluster, reverse=True)


def score_cluster(c: dict) -> float:
    recency = math.exp(-(time.time() * 1000 - c["last_seen"]) / (6 * 3_600_000))
    diversity = min(len(c["sources"]), 6) / 6
    size = min(c["count"], 20) / 20
    sev = c["severity"] / 5
    return (0.35 * sev + 0.25 * diversity + 0.2 * size + 0.2 * recency) * (1 + c["momentum"])


# ---------------------------------------------------------------------------
# Trend spikes
# ---------------------------------------------------------------------------

def detect_spikes(events: list, window_count: int = 4) -> list:
    if len(events) < 8:
        return []
    newest = max(e["published"] for e in events)
    oldest = min(e["published"] for e in events)
    span = max(newest - oldest, 1)
    win_ms = span / window_count
    buckets = [dict() for _ in range(window_count)]
    for e in events:
        idx = min(window_count - 1, int((e["published"] - oldest) / win_ms))
        for t in set(tokenize(e["title"])):
            buckets[idx][t] = buckets[idx].get(t, 0) + 1
    last = buckets[window_count - 1]
    out = []
    for term, count in last.items():
        base = sum(buckets[i].get(term, 0) for i in range(window_count - 1))
        baseline = base / max(window_count - 1, 1)
        if count >= 4 and count >= baseline * 2.5:
            out.append({"term": term, "count": count, "baseline": baseline,
                        "ratio": count / baseline if baseline else float(count)})
    return sorted(out, key=lambda s: s["ratio"], reverse=True)[:12]


# ---------------------------------------------------------------------------
# Entities + watchlist
# ---------------------------------------------------------------------------

COUNTRIES = [
    "afghanistan","algeria","argentina","australia","austria","azerbaijan","bangladesh","belarus","belgium",
    "bolivia","brazil","bulgaria","cambodia","cameroon","canada","chile","china","colombia","congo","croatia",
    "cuba","cyprus","czech republic","denmark","ecuador","egypt","ethiopia","finland","france","germany",
    "ghana","greece","hungary","iceland","india","indonesia","iran","iraq","ireland","israel","italy","japan",
    "jordan","kazakhstan","kenya","kuwait","laos","lebanon","libya","lithuania","malaysia","mali","mexico",
    "moldova","mongolia","morocco","myanmar","nepal","netherlands","new zealand","nicaragua","niger","nigeria",
    "north korea","norway","oman","pakistan","panama","paraguay","peru","philippines","poland","portugal",
    "qatar","romania","russia","rwanda","saudi arabia","serbia","singapore","slovakia","slovenia","somalia",
    "south africa","south korea","spain","sri lanka","sudan","sweden","switzerland","syria","taiwan","thailand",
    "tunisia","turkey","uganda","ukraine","united arab emirates","united kingdom","britain","united states",
    "america","venezuela","vietnam","yemen","zambia","zimbabwe",
]

CITIES = [
    "abuja","accra","amman","amsterdam","ankara","baghdad","bangkok","barcelona","beijing","beirut","berlin",
    "bogota","boston","brussels","bucharest","budapest","buenos aires","cairo","california","chicago","colombo",
    "copenhagen","dakar","dallas","damascus","delhi","denver","dhaka","doha","dubai","dublin","geneva","hanoi",
    "havana","helsinki","hong kong","houston","islamabad","istanbul","jakarta","jerusalem","johannesburg",
    "kabul","karachi","kathmandu","kiev","kuala lumpur","lagos","lahore","london","los angeles","madrid",
    "manila","melbourne","mexico city","miami","minsk","moscow","mumbai","munich","nairobi","new delhi",
    "new york","oslo","ottawa","paris","perth","philadelphia","prague","pyongyang","riyadh","rome",
    "san francisco","santiago","sao paulo","seattle","seoul","shanghai","singapore","stockholm","sydney",
    "taipei","tehran","tel aviv","tokyo","toronto","tripoli","vienna","warsaw","washington","wellington","zurich",
]


def extract_entities(text: str) -> dict:
    t = f" {text.lower()} "
    has = lambda name: f" {name} " in t or f" {name}," in t or f" {name}." in t or f" {name}s " in t
    return {"countries": [c for c in COUNTRIES if has(c)],
            "cities": [c for c in CITIES if f" {c} " in t or f" {c}," in t or f" {c}." in t]}


def matches_term(text: str, term: str) -> bool:
    t = f" {text.lower()} "
    if " " in term:
        return term in t
    return f" {term} " in t or f" {term}," in t or f" {term}." in t or f" {term}s " in t


def watch_alerts(events: list, watch: dict) -> list:
    out = []
    for ev in events:
        if ev["severity"] < watch["min_severity"]:
            continue
        text = f"{ev['title']} {ev.get('summary') or ''}"
        matched = []
        for country in watch["countries"]:
            if matches_term(text, country):
                matched.append(country)
        for kw in watch["keywords"]:
            if kw.lower() in text.lower():
                matched.append(kw)
        if matched:
            out.append({"event": ev, "matched": matched})
    return out[:50]


def watch_term_stats(events: list, watch: dict) -> list:
    """Per-term match counts across the given events (respects min_severity).
    Lets the UI show how active each watchlist term is right now."""
    counts: dict[str, int] = {}
    for ev in events:
        if ev["severity"] < watch["min_severity"]:
            continue
        text = f"{ev['title']} {ev.get('summary') or ''}"
        for country in watch["countries"]:
            if matches_term(text, country):
                counts[country] = counts.get(country, 0) + 1
        for kw in watch["keywords"]:
            if kw.lower() in text.lower():
                counts[kw] = counts.get(kw, 0) + 1
    return sorted([{"term": k, "count": v} for k, v in counts.items()],
                  key=lambda x: x["count"], reverse=True)


# ---------------------------------------------------------------------------
# Briefing
# ---------------------------------------------------------------------------

def generate_briefing(events: list, hours: int = 24) -> dict:
    since = time.time() * 1000 - hours * 3_600_000
    recent = [e for e in events if e["published"] >= since]
    clusters = cluster_events(recent)[:8]
    breaking = [e for e in recent if e["severity"] >= 4][:6]
    disasters = [e for e in recent if e["source"] in ("eonet", "gdacs", "usgs")][:5]
    supply = sorted([e for e in recent if e["category"] in ("supplychain", "energy")],
                    key=lambda e: e["severity"], reverse=True)[:5]
    spikes = detect_spikes(recent)

    sections = []
    if breaking:
        sections.append({"title": "Breaking", "items": [
            {"title": e["title"], "detail": f"{e['category']} · {e['source']}" + (f" · {(e.get('geo') or {}).get('place', '')}" if e.get("geo") else ""),
             "severity": e["severity"], "url": e.get("url")} for e in breaking]})
    if clusters:
        sections.append({"title": "Top stories", "items": [
            {"title": c["title"], "detail": f"Covered by {len(c['sources'])} source(s) · {c['count']} update(s) · {', '.join(c['categories'])}",
             "severity": c["severity"], "url": (c["sample"][0].get("url") if c["sample"] else None)} for c in clusters]})
    if disasters:
        sections.append({"title": "Natural disasters", "items": [
            {"title": e["title"], "detail": f"{e['source']} · severity {e['severity']}/5" + (f" · {(e.get('geo') or {}).get('place', '')}" if e.get("geo") else ""),
             "severity": e["severity"], "url": e.get("url")} for e in disasters]})
    if supply:
        sections.append({"title": "Supply chain & energy watch", "items": [
            {"title": e["title"], "detail": f"{e['source']} · severity {e['severity']}/5",
             "severity": e["severity"], "url": e.get("url")} for e in supply]})
    if spikes:
        sections.append({"title": "Emerging trends", "items": [
            {"title": s["term"], "detail": f"{s['count']} mention(s) vs baseline {s['baseline']:.1f} ({s['ratio']:.1f}×)",
             "severity": 0, "url": None} for s in spikes]})

    if breaking:
        headline = breaking[0]["title"]
    elif clusters:
        headline = clusters[0]["title"]
    else:
        headline = "No major developments in the last 24 hours."
    return {"generated": int(time.time() * 1000), "headline": headline, "sections": sections}


# ---------------------------------------------------------------------------
# World summary
# ---------------------------------------------------------------------------

_REGION_MAP = {
    "Middle East": ["iran", "iraq", "israel", "palestine", "gaza", "saudi arabia", "syria", "lebanon", "jordan",
                    "qatar", "kuwait", "oman", "yemen", "uae", "turkey", "bahrain"],
    "Europe": ["ukraine", "russia", "britain", "united kingdom", "france", "germany", "italy", "spain", "poland",
               "belarus", "finland", "sweden", "norway", "denmark", "netherlands", "belgium", "austria",
               "switzerland", "greece", "portugal", "ireland", "hungary", "czech", "romania", "bulgaria", "serbia",
               "croatia", "lithuania", "latvia", "estonia", "moldova", "georgia", "armenia", "azerbaijan"],
    "Asia-Pacific": ["china", "taiwan", "japan", "south korea", "north korea", "india", "pakistan", "indonesia",
                     "philippines", "thailand", "vietnam", "malaysia", "singapore", "myanmar", "bangladesh",
                     "sri lanka", "nepal", "afghanistan", "kazakhstan", "mongolia", "australia", "new zealand"],
    "Africa": ["egypt", "nigeria", "sudan", "south africa", "kenya", "ethiopia", "ghana", "tanzania", "uganda",
               "congo", "cameroon", "mali", "niger", "rwanda", "somalia", "libya", "tunisia", "algeria", "morocco",
               "zimbabwe", "zambia", "angola", "mozambique"],
    "Americas": ["united states", "america", "canada", "mexico", "brazil", "argentina", "chile", "colombia",
                 "peru", "venezuela", "ecuador", "bolivia", "paraguay", "uruguay", "cuba", "haiti", "panama",
                 "costa rica", "guatemala"],
}


def region_of(text: str) -> str:
    t = text.lower()
    for region, terms in _REGION_MAP.items():
        if any(matches_term(t, term) for term in terms):
            return region
    return "Global"


def generate_world_summary(events: list, hours: int = 24) -> dict:
    since = time.time() * 1000 - hours * 3_600_000
    recent = [e for e in events if e["published"] >= since]
    clusters = cluster_events(recent)
    spikes = detect_spikes(recent)

    region_map: dict = {}
    for c in clusters:
        region_map.setdefault(region_of(c["title"]), []).append(c)
    regions = []
    for name, cl in region_map.items():
        regions.append({
            "name": name,
            "count": len(cl),
            "top": [{"title": c["title"], "severity": c["severity"],
                     "url": (c["sample"][0].get("url") if c["sample"] else None)} for c in cl[:3]],
        })
    regions.sort(key=lambda r: r["count"], reverse=True)

    cat_map: dict = {}
    for c in clusters:
        cat_map.setdefault(c["category"], []).append(c)
    categories = []
    for cat, cl in cat_map.items():
        categories.append({
            "category": cat,
            "count": len(cl),
            "top": [{"title": c["title"], "severity": c["severity"],
                     "url": (c["sample"][0].get("url") if c["sample"] else None)} for c in cl[:3]],
        })
    categories.sort(key=lambda c: c["count"], reverse=True)

    active = [r for r in regions if r["name"] != "Global"]
    opening = f"Over the last {hours}h, {len(recent)} reports were grouped into {len(clusters)} story lines across {len(regions)} regions."
    if active:
        opening += f" Most active: {', '.join(r['name'] for r in active[:3])}."
    if spikes:
        opening += " Rising fast: " + ", ".join(f"{s['term']} ({s['ratio']:.1f}×)" for s in spikes[:4]) + "."
    if clusters:
        opening += f" The single most important story right now is: {clusters[0]['title']}"

    return {"generated": int(time.time() * 1000), "hours": hours, "opening": opening,
            "regions": regions, "categories": categories}
