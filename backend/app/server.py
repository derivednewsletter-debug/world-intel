"""FastAPI server — REST API + AI endpoints + push + the Jinja2 dashboard."""
import asyncio
import json
import re
import socket
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from . import db, watchlist
from .ai.engine import (STOPWORDS, cluster_events, detect_spikes, generate_briefing,
                        generate_world_summary, watch_alerts, watch_term_stats)
from .ai.stress import compute_stress
from .collectors import run_all
from concurrent.futures import ThreadPoolExecutor
from .eventhub import hub

from .config import APNS, CATEGORIES, HOST, LIVE_STREAMS, PORT
from .push.apns import send_push
from .scheduler import start_scheduler, stop_scheduler

APP_VERSION = "0.3.0"

_push_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="push")

# Boot progress tracker — frontend can poll this to show a loading bar.
_boot_state = {"phase": "init", "progress": 0, "message": "Starting…", "done": False}
_boot_lock = threading.Lock()


def _set_boot(phase: str, progress: int, message: str) -> None:
    with _boot_lock:
        _boot_state.update(phase=phase, progress=progress, message=message)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Boot on startup: init the DB, start the scheduler, kick off the first
    collection and the push scan. Everything shuts down cleanly on exit."""
    _set_boot("db", 10, "Initializing database…")
    db.init_db()
    _set_boot("scheduler", 20, "Starting scheduler…")
    start_scheduler()
    _set_boot("collecting", 30, "Collecting from all sources…")
    threading.Thread(target=_push_scan, daemon=True).start()
    threading.Thread(target=_boot_collect, daemon=True).start()
    yield
    stop_scheduler()


def _boot_collect() -> None:
    """Run all collectors at boot, updating progress as each group finishes."""
    try:
        from .collectors import (run_rss, run_disasters, run_fred, run_firms,
                                 run_weather, run_spaceweather, run_watch_feed, run_money)
        from .collectors.gdelt import run_gdelt_doc, run_gdelt_points
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Phase 1: Fast sources in parallel (RSS, weather, disasters, money, etc.)
        fast_jobs = [run_rss, run_disasters, run_weather, run_spaceweather,
                     run_watch_feed, run_money]
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(fn): fn.__name__ for fn in fast_jobs}
            done = 0
            for f in as_completed(futures):
                done += 1
                pct = 30 + int(50 * done / len(futures))
                _set_boot("collecting", pct, f"Collected {done}/{len(futures)} fast sources…")
                # Publish any new events to SSE subscribers
                try:
                    result = f.result()
                except Exception:  # noqa: BLE001
                    pass

        # Phase 2: FRED + FIRMS (need API keys, may skip)
        key_jobs = [run_fred, run_firms]
        done = 0
        for fn in key_jobs:
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass
            done += 1
            _set_boot("collecting", 80 + done * 5, f"Key sources {done}/{len(key_jobs)}…")

        # Phase 3: GDELT (rate-limited, sequential)
        _set_boot("collecting", 90, "Collecting GDELT (rate-limited)…")
        try:
            run_gdelt_doc()
        except Exception:  # noqa: BLE001
            pass
        try:
            run_gdelt_points()
        except Exception:  # noqa: BLE001
            pass

        _set_boot("done", 100, "Dashboard ready!")
        with _boot_lock:
            _boot_state["done"] = True
        # Publish stats so SSE clients get a fresh snapshot
        hub.publish_stats({"type": "boot_complete", "total": db.count_events()})
    except Exception as err:  # noqa: BLE001
        _set_boot("error", 100, f"Collection error: {err}")
        with _boot_lock:
            _boot_state["done"] = True


app = FastAPI(title="World Intelligence", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Simple in-memory rate limiter (sliding window per IP)
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter: max `limit` requests per `window` seconds.
    Only applied to mutation endpoints (PUT/POST/DELETE) to prevent abuse.
    Read endpoints are unlimited — the dashboard is a personal tool."""

    def __init__(self, app, limit: int = 30, window: float = 60.0):
        super().__init__(app)
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()
        # Cleanup old entries every 5 minutes.
        self._last_cleanup = time.time()

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request, call_next):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)
        ip = self._client_ip(request)
        now = time.time()
        with self._lock:
            # Periodic cleanup.
            if now - self._last_cleanup > 300:
                self._last_cleanup = now
                cutoff = now - self.window
                for k in list(self._hits):
                    self._hits[k] = [t for t in self._hits[k] if t > cutoff]
                    if not self._hits[k]:
                        del self._hits[k]
            cutoff = now - self.window
            self._hits[ip] = [t for t in self._hits[ip] if t > cutoff]
            if len(self._hits[ip]) >= self.limit:
                retry = self._hits[ip][0] + self.window - now
                return Response(
                    content='{"error":"rate limit exceeded","retry":' + str(int(retry) + 1) + '}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(int(retry) + 1)},
                )
            self._hits[ip].append(now)
        return await call_next(request)


app.add_middleware(RateLimitMiddleware, limit=60, window=60.0)

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
    by_category = db.count_events_by_category()
    # Fill in zeros for categories with no events yet.
    for c in CATEGORIES:
        by_category.setdefault(c, 0)
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
    buckets = db.get_activity_buckets(since, hours)
    return {
        "hours": hours,
        "buckets": buckets,
        "total": sum(b["count"] for b in buckets),
    }


@app.get("/api/health")
async def api_health():
    """Uptime / liveness check — handy for the iOS app's optional push server URL."""
    import os
    db_size = 0
    try:
        from .config import DB_PATH
        db_size = os.path.getsize(DB_PATH)
    except (OSError, ImportError):
        pass
    sources = db.get_source_status()
    healthy = sum(1 for s in sources if s["last_ok"])
    return {
        "status": "ok",
        "version": APP_VERSION,
        "total": db.count_events(),
        "sources": {"healthy": healthy, "total": len(sources)},
        "dbSizeBytes": db_size,
        "updatedAt": int(time.time() * 1000),
        "uptimeSec": round(time.time() - _started_at),
    }


@app.get("/api/trends")
async def api_trends():
    since = int(time.time() * 1000) - 12 * 3_600_000
    events = db.get_events(since=since, limit=500)
    words: dict[str, int] = {}
    bigrams: dict[str, int] = {}
    for e in events:
        toks = [t for t in re.sub(r"[^a-z0-9 ]+", " ", e["title"].lower()).split()
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
    """One event + related events by title similarity (for detail modal + timelines)."""
    ev = db.get_event(event_id)
    if not ev:
        return {"event": None, "cluster": None, "related": []}
    all_related = db.get_related_events(event_id)
    related = [e for e in all_related if e["id"] != event_id][:8]
    # Build a timeline from all related events (sorted chronologically).
    timeline = [{"published": e["published"], "title": e["title"],
                 "source": e["source"], "url": e.get("url"),
                 "severity": e["severity"]}
                for e in sorted(all_related, key=lambda e: e["published"])][:20]
    cluster = {"id": event_id, "timeline": timeline} if len(timeline) > 1 else None
    return {"event": ev, "cluster": cluster, "related": related}


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


@app.get("/api/startup")
async def api_startup():
    """Boot progress — frontend polls this on load to show a loading bar."""
    with _boot_lock:
        return dict(_boot_state)


@app.get("/api/events/stream")
async def api_events_stream(request: Request):
    """Server-Sent Events stream — pushes new events to the browser in real-time."""
    sub_id, queue = hub.subscribe()

    async def event_generator():
        try:
            # Send initial snapshot so the client has something immediately.
            yield f"event: connected\ndata: {json.dumps({'subscribers': hub.subscriber_count})}\n\n"
            while True:
                # Check if client disconnected.
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: {payload['type']}\ndata: {json.dumps(payload['data'])}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment every 30s.
                    yield f": keepalive {int(time.time())}\n\n"
        finally:
            hub.unsubscribe(sub_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
                _push_pool.submit(send_push, t, payload, APNS)


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
