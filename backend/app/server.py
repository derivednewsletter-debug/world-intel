"""FastAPI server — REST API + AI endpoints + push + the Jinja2 dashboard."""
import re
import socket
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware

from . import db, watchlist
from .ai.engine import (STOPWORDS, cluster_events, detect_spikes, generate_briefing,
                        generate_world_summary, watch_alerts, watch_term_stats)
from .ai.stress import compute_stress
from .collectors import run_all
from .config import APNS, CATEGORIES, HOST, LIVE_STREAMS, PORT
from .push.apns import send_push
from .scheduler import start_scheduler, stop_scheduler

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Boot on startup: init the DB, start the scheduler, kick off the first
    collection and the push scan. Everything shuts down cleanly on exit."""
    db.init_db()
    start_scheduler()
    threading.Thread(target=_push_scan, daemon=True).start()
    threading.Thread(target=run_all, daemon=True).start()
    yield
    stop_scheduler()


app = FastAPI(title="World Intelligence", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

_BASE = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")


async def _json_body(request: Request) -> dict:
    """Parse a JSON body safely — never 500 on malformed input."""
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _hours_param(request: Request) -> int:
    raw = request.query_params.get("hours", "24")
    try:
        return min(max(int(raw), 1), 72)
    except ValueError:
        return 24


def _ai_events(hours: int) -> list:
    return db.get_all_events_since(int(time.time() * 1000) - hours * 3_600_000)


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

@app.get("/api/events")
async def api_events(request: Request):
    q = dict(request.query_params)
    since = None
    if q.get("since"):
        try:
            since = int(q["since"])
        except ValueError:
            since = None
    try:
        limit = min(max(int(q.get("limit", 200)), 1), 500)
    except ValueError:
        limit = 200
    try:
        offset = max(int(q.get("offset", 0)), 0)
    except ValueError:
        offset = 0
    try:
        min_severity = int(q["minSeverity"]) if q.get("minSeverity") not in (None, "") else None
    except ValueError:
        min_severity = None
    geo = q.get("geo") in ("1", "true")
    events = db.get_events(
        category=q.get("category"), q=q.get("q"), since=since,
        limit=limit, offset=offset, with_geo=geo, min_severity=min_severity,
    )
    total = db.count_events(
        category=q.get("category"), q=q.get("q"), since=since, min_severity=min_severity,
    )
    return {"events": events, "total": total, "limit": limit, "offset": offset}


@app.get("/api/stats")
async def api_stats():
    now = int(time.time() * 1000)
    by_category = {c: db.count_events(category=c) for c in CATEGORIES}
    latest = db.get_events(limit=1)
    sources = []
    for s in db.get_source_status():
        last_run = s["last_run"]
        sources.append({
            **s,
            "ageMin": round((now - last_run) / 60000) if last_run else None,
            "stale": (now - last_run > 2 * 3_600_000) if last_run else True,
        })
    return {
        "total": db.count_events(),
        "byCategory": by_category,
        "latest": latest[0]["published"] if latest else None,
        "updatedAt": now,
        "sources": sources,
    }


@app.get("/api/indicators")
async def api_indicators():
    return {"indicators": db.get_indicators()}


@app.get("/api/sources")
async def api_sources():
    return {"sources": db.get_source_status()}


@app.get("/api/live")
async def api_live():
    return {"streams": LIVE_STREAMS}


@app.get("/api/watchlist")
async def api_get_watchlist():
    return watchlist.effective_watchlist()


@app.put("/api/watchlist")
async def api_put_watchlist(request: Request):
    body = await _json_body(request)
    countries = body.get("countries") or []
    keywords = body.get("keywords") or []
    min_severity = body.get("min_severity")
    saved = watchlist.save_watchlist(countries, keywords, min_severity)
    return saved


@app.delete("/api/watchlist")
async def api_delete_watchlist():
    return watchlist.reset_watchlist()


@app.get("/api/activity")
async def api_activity(request: Request):
    """Events per hour over the last N hours — powers the activity chart."""
    hours = _hours_param(request)
    since = int(time.time() * 1000) - hours * 3_600_000
    buckets = {h: 0 for h in range(hours)}
    for e in db.get_all_events_since(since):
        idx = min(hours - 1, max(0, int((e["published"] - since) / 3_600_000)))
        buckets[idx] += 1
    return {
        "hours": hours,
        "buckets": [{"hour": h, "count": buckets[h]} for h in range(hours)],
        "total": sum(buckets.values()),
    }


@app.get("/api/health")
async def api_health():
    """Uptime / liveness check — handy for the iOS app's optional push server URL."""
    return {
        "status": "ok",
        "total": db.count_events(),
        "updatedAt": int(time.time() * 1000),
        "uptimeSec": round(time.time() - _started_at),
    }


@app.get("/api/trends")
async def api_trends():
    since = int(time.time() * 1000) - 12 * 3_600_000
    events = db.get_events(since=since, limit=500)
    words: dict[str, int] = {}
    bigrams: dict[str, int] = {}
    import re as _re
    for e in events:
        toks = [t for t in _re.sub(r"[^a-z0-9 ]+", " ", e["title"].lower()).split()
                if len(t) > 3 and t not in STOPWORDS]
        for i, t in enumerate(toks):
            words[t] = words.get(t, 0) + 1
            if i > 0:
                bg = f"{toks[i - 1]} {t}"
                bigrams[bg] = bigrams.get(bg, 0) + 1
    top = lambda m, n: [{"term": k, "count": v} for k, v in
                        sorted(m.items(), key=lambda kv: kv[1], reverse=True)[:n]]
    return {"words": top(words, 15), "bigrams": top(bigrams, 10)}


# ---------------------------------------------------------------------------
# AI endpoints (from-scratch intelligence engine)
# ---------------------------------------------------------------------------

@app.get("/api/ai/briefing")
async def ai_briefing(request: Request):
    hours = _hours_param(request)
    return generate_briefing(_ai_events(hours), hours)


@app.get("/api/ai/summary")
async def ai_summary(request: Request):
    hours = _hours_param(request)
    return generate_world_summary(_ai_events(hours), hours)


@app.get("/api/ai/stories")
async def ai_stories(request: Request):
    hours = _hours_param(request)
    raw = request.query_params.get("limit", "20")
    try:
        limit = min(max(int(raw), 1), 50)
    except ValueError:
        limit = 20
    return {"stories": cluster_events(_ai_events(hours))[:limit]}


@app.get("/api/ai/watch")
async def ai_watch():
    events = db.get_all_events_since(int(time.time() * 1000) - 24 * 3_600_000)
    wl = watchlist.effective_watchlist()
    return {
        "watchlist": wl,
        "alerts": watch_alerts(events, wl),
        "term_stats": watch_term_stats(events, wl),
    }


@app.get("/api/ai/trends")
async def ai_trends():
    events = db.get_all_events_since(int(time.time() * 1000) - 24 * 3_600_000)
    return {"spikes": detect_spikes(events)}


@app.get("/api/stress")
async def api_stress(request: Request):
    """World Stress Index — 0-100 composite gauge + per-hour history."""
    hours = _hours_param(request)
    events = db.get_all_events_since(int(time.time() * 1000) - hours * 3_600_000)
    wl = watchlist.effective_watchlist()
    watch_count = len(watch_alerts(events, wl))
    return compute_stress(events, db.get_indicators(), watch_count=watch_count, hours=hours)


@app.get("/api/event/{event_id}")
async def api_event(event_id: str):
    """One event + the story cluster it belongs to (for detail modal + timelines)."""
    ev = db.get_event(event_id)
    if not ev:
        return {"event": None, "cluster": None, "related": []}
    events = db.get_all_events_since(int(time.time() * 1000) - 24 * 3_600_000)
    for c in cluster_events(events):
        if c["id"] == event_id or any(s["id"] == event_id for s in c["sample"]):
            related = [e for e in c["sample"] if e["id"] != event_id][:8]
            return {"event": ev, "cluster": c, "related": related}
    return {"event": ev, "cluster": None, "related": []}


# ---------------------------------------------------------------------------
# Push device registration + test
# ---------------------------------------------------------------------------

@app.post("/api/push/register")
async def push_register(request: Request):
    body = await _json_body(request)
    token = body.get("token")
    if not token or not re.fullmatch(r"[a-f0-9]{64}", token):
        return {"ok": False, "error": "invalid token"}
    db.register_device_token(token)
    return {"ok": True}


@app.post("/api/push/test")
async def push_test():
    tokens = db.get_device_tokens()
    payload = {
        "aps": {"alert": {"title": "🌍 World Intelligence", "body": "Test notification — push is working!"}, "sound": "default"},
        "url": None,
    }
    sent = 0
    for t in tokens:
        if send_push(t, payload, APNS):
            sent += 1
    return {"ok": True, "sent": sent, "total": len(tokens)}


@app.get("/api/search")
async def api_search(request: Request):
    q = (request.query_params.get("q") or "").strip()
    if not q:
        return {"events": [], "indicators": []}
    events = db.get_events(q=q, limit=100)
    indicators = [i for i in db.get_indicators() if q.lower() in i["name"].lower()]
    return {"events": events, "indicators": indicators}


@app.get("/api/export")
async def api_export(request: Request):
    """Download events as CSV (spreadsheets / research). Optional ?category= filter."""
    import csv as csv_mod
    import io as io_mod
    hours = _hours_param(request)
    since = int(time.time() * 1000) - hours * 3_600_000
    events = db.get_all_events_since(since)
    category = (request.query_params.get("category") or "").strip()
    if category:
        events = [e for e in events if e["category"] == category]
    buf = io_mod.StringIO()
    writer = csv_mod.writer(buf)
    writer.writerow(["published_utc", "category", "severity", "source", "title", "url", "summary", "lat", "lon"])
    for e in events:
        geo = e.get("geo") or {}
        writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(e["published"] / 1000)),
            e["category"], e["severity"], e["source"], e["title"],
            e.get("url") or "", (e.get("summary") or "").replace("\r", " ").replace("\n", " "),
            geo.get("lat", ""), geo.get("lon", ""),
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=world-intel.csv"},
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _TEMPLATES.TemplateResponse(
        request, "index.html", {"title": "World Intelligence"}
    )


# ---------------------------------------------------------------------------
# Push scan — major/watchlist events go out to registered devices
# ---------------------------------------------------------------------------

def _push_scan() -> None:
    last_check = int(time.time() * 1000)
    while True:
        time.sleep(5 * 60)
        if not APNS["enabled"]:
            continue
        tokens = db.get_device_tokens()
        if not tokens:
            continue
        since = last_check
        last_check = int(time.time() * 1000)
        fresh = db.get_events(since=since, limit=100)
        majors = [e for e in fresh if e["severity"] >= 4][:3]
        watch = [w["event"] for w in watch_alerts(fresh, watchlist.effective_watchlist())][:3]
        seen = set()
        for e in majors + watch:
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            payload = {
                "aps": {"alert": {"title": f"🌍 {e['category'].upper()}", "body": e["title"]}, "sound": "default"},
                "url": e.get("url"),
            }
            for t in tokens:
                threading.Thread(target=send_push, args=(t, payload, APNS), daemon=True).start()


def _lan_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        return None


_started_at = time.time()


def main() -> None:
    import sys
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    import uvicorn
    print(f"🌍 World Intelligence running at http://localhost:{PORT}")
    ip = _lan_ip()
    if ip:
        print(f"   On your network: http://{ip}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
