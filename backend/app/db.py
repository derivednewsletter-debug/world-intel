"""SQLite data layer — thread-local connections, batch upsert, WAL mode."""
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .config import DB_PATH, RETENTION_DAYS
from .dedupe import normalize_title

# Thread-local storage so each thread gets its own connection.
_tls = threading.local()

_SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  category TEXT NOT NULL,
  severity INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL,
  title_norm TEXT NOT NULL DEFAULT '',
  url TEXT,
  summary TEXT,
  image TEXT,
  published INTEGER NOT NULL,
  lat REAL,
  lon REAL,
  place TEXT,
  fetched INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_published ON events(published DESC);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_title_norm ON events(title_norm);

CREATE TABLE IF NOT EXISTS indicators (
  series_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  unit TEXT,
  latest_value REAL,
  latest_date TEXT,
  updated INTEGER NOT NULL,
  history TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_tokens (
  token TEXT PRIMARY KEY,
  registered INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS source_status (
  source TEXT PRIMARY KEY,
  last_run INTEGER,
  last_ok INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  count INTEGER NOT NULL DEFAULT 0,
  cooldown_until INTEGER
);

CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    """Return a thread-local connection, reusing it across calls.

    Detects when DB_PATH has changed (e.g. in tests) and reconnects.
    """
    conn = getattr(_tls, "conn", None)
    conn_path = getattr(_tls, "db_path", None)
    if conn is not None and conn_path == DB_PATH:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            pass  # closed or wrong thread — make a new one
    # Close any stale connection to a different path.
    if conn is not None and conn_path != DB_PATH:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    _tls.conn = conn
    _tls.db_path = DB_PATH
    return conn


def _migrate(c: sqlite3.Connection) -> None:
    cols = {row["name"] for row in c.execute("PRAGMA table_info(events)").fetchall()}
    if "title_norm" not in cols:
        c.execute("ALTER TABLE events ADD COLUMN title_norm TEXT NOT NULL DEFAULT ''")
    if "image" not in cols:
        c.execute("ALTER TABLE events ADD COLUMN image TEXT")
    src_cols = {row["name"] for row in c.execute("PRAGMA table_info(source_status)").fetchall()}
    if "cooldown_until" not in src_cols:
        c.execute("ALTER TABLE source_status ADD COLUMN cooldown_until INTEGER")


def init_db() -> None:
    c = _conn()
    c.executescript(_SCHEMA)
    _migrate(c)
    # Checkpoint WAL to prevent unbounded growth on restart.
    try:
        c.execute("PRAGMA wal_checkpoint(PASSIVE)")
    except Exception:  # noqa: BLE001
        pass


def _to_event(row: sqlite3.Row) -> dict:
    ev = {
        "id": row["id"],
        "source": row["source"],
        "category": row["category"],
        "severity": row["severity"],
        "title": row["title"],
        "url": row["url"],
        "summary": row["summary"],
        "image": row["image"],
        "published": row["published"],
    }
    if row["lat"] is not None and row["lon"] is not None:
        ev["geo"] = {"lat": row["lat"], "lon": row["lon"], "place": row["place"]}
    return ev


def upsert_event(ev: dict) -> bool:
    """Insert an event; dedupes on id and on identical normalized title within 24h."""
    norm = normalize_title(ev["title"])
    c = _conn()
    dup = c.execute(
        "SELECT id FROM events WHERE title_norm = ? AND published >= ? LIMIT 1",
        (norm, int(time.time() * 1000) - 24 * 3600_000),
    ).fetchone()
    if dup:
        return False
    cur = c.execute(
        """INSERT OR IGNORE INTO events
           (id, source, category, severity, title, title_norm, url, summary, image, published, lat, lon, place, fetched)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ev["id"],
            ev["source"],
            ev["category"],
            ev["severity"],
            ev["title"],
            norm,
            ev.get("url"),
            ev.get("summary"),
            ev.get("image"),
            ev["published"],
            (ev.get("geo") or {}).get("lat"),
            (ev.get("geo") or {}).get("lon"),
            (ev.get("geo") or {}).get("place"),
            int(time.time() * 1000),
        ),
    )
    return cur.rowcount > 0


def upsert_events_batch(events: list[dict]) -> tuple[int, list[dict]]:
    """Insert many events in one transaction — much faster than one-at-a-time.
    Returns (count, inserted_events) so collectors can publish new events
    to the real-time SSE hub."""
    if not events:
        return 0, []
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - 24 * 3600_000
    c = _conn()
    n = 0
    inserted = []
    with c:
        # Fetch all existing norms in one shot for dedup.
        existing = {
            row[0]
            for row in c.execute(
                "SELECT title_norm FROM events WHERE published >= ?", (cutoff,)
            ).fetchall()
        }
        for ev in events:
            norm = normalize_title(ev["title"])
            if norm in existing:
                continue
            existing.add(norm)
            c.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, category, severity, title, title_norm, url, summary, image, published, lat, lon, place, fetched)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ev["id"],
                    ev["source"],
                    ev["category"],
                    ev["severity"],
                    ev["title"],
                    norm,
                    ev.get("url"),
                    ev.get("summary"),
                    ev.get("image"),
                    ev["published"],
                    (ev.get("geo") or {}).get("lat"),
                    (ev.get("geo") or {}).get("lon"),
                    (ev.get("geo") or {}).get("place"),
                    now_ms,
                ),
            )
            n += 1
            inserted.append(ev)
    return n, inserted


def _escape_like(s: str) -> str:
    """Escape LIKE wildcards so user search input is matched literally."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_events(category: Optional[str] = None, q: Optional[str] = None, since: Optional[int] = None,
               limit: int = 200, offset: int = 0, with_geo: bool = False,
               min_severity: Optional[int] = None) -> list:
    conds, params = [], []
    if category:
        conds.append("category = ?")
        params.append(category)
    if since:
        conds.append("published >= ?")
        params.append(since)
    if q:
        conds.append("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')")
        params.extend([f"%{_escape_like(q)}%", f"%{_escape_like(q)}%"])
    if with_geo:
        conds.append("lat IS NOT NULL AND lon IS NOT NULL")
    if min_severity is not None:
        conds.append("severity >= ?")
        params.append(min_severity)
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    limit = min(max(limit, 1), 500)
    c = _conn()
    rows = c.execute(
        f"SELECT * FROM events {where} ORDER BY published DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [_to_event(r) for r in rows]


def count_events(category: Optional[str] = None, q: Optional[str] = None, since: Optional[int] = None,
                 min_severity: Optional[int] = None) -> int:
    conds, params = [], []
    if category:
        conds.append("category = ?")
        params.append(category)
    if since:
        conds.append("published >= ?")
        params.append(since)
    if q:
        conds.append("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')")
        params.extend([f"%{_escape_like(q)}%", f"%{_escape_like(q)}%"])
    if min_severity is not None:
        conds.append("severity >= ?")
        params.append(min_severity)
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    c = _conn()
    row = c.execute(f"SELECT COUNT(*) AS c FROM events {where}", params).fetchone()
    return row["c"]


def count_events_by_category() -> dict:
    """Count events per category in one query — avoids N separate queries."""
    c = _conn()
    rows = c.execute("SELECT category, COUNT(*) AS c FROM events GROUP BY category").fetchall()
    return {r["category"]: r["c"] for r in rows}


def get_activity_buckets(since_ms: int, hours: int) -> list:
    """Events per hour bucket using SQL — avoids fetching all events into Python.
    Returns a list of {hour: <epoch_ms>, count: <int>} dicts."""
    c = _conn()
    # SQLite's strftime works on epoch seconds, not ms.
    since_sec = since_ms // 1000
    bucket_size = 3600  # 1 hour in seconds
    rows = c.execute(
        "SELECT (published / 1000) AS ts FROM events WHERE published >= ?",
        (since_ms,),
    ).fetchall()
    buckets = {h: 0 for h in range(hours)}
    for row in rows:
        ts = row["ts"]
        idx = min(hours - 1, max(0, (ts - since_sec) // bucket_size))
        buckets[idx] += 1
    return [{"hour": since_ms + h * 3_600_000, "count": buckets[h]} for h in range(hours)]


def get_event(event_id: str) -> Optional[dict]:
    c = _conn()
    row = c.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return _to_event(row) if row else None


def get_related_events(event_id: str, hours: int = 24) -> list:
    """Find events related to a given event by normalized-title similarity.
    Much faster than re-clustering all events for the detail modal."""
    c = _conn()
    target = c.execute("SELECT title_norm FROM events WHERE id = ?", (event_id,)).fetchone()
    if not target:
        return []
    norm = target["title_norm"]
    since = int(time.time() * 1000) - hours * 3_600_000
    # Exact norm match first — same story from different outlets.
    rows = c.execute(
        "SELECT * FROM events WHERE title_norm = ? AND published >= ? ORDER BY published DESC",
        (norm, since),
    ).fetchall()
    if len(rows) >= 2:
        return [_to_event(r) for r in rows]
    # Fallback: prefix match on the first 60 chars of the normalized title.
    prefix = norm[:60]
    rows = c.execute(
        "SELECT * FROM events WHERE title_norm LIKE ? AND published >= ? ORDER BY published DESC LIMIT 30",
        (prefix + "%", since),
    ).fetchall()
    return [_to_event(r) for r in rows]


def get_all_events_since(since_ms: int) -> list:
    """Every event since a timestamp — pages through the whole result set, no cap.
    Used by the AI so the briefing/summary genuinely reads all current events."""
    out: list = []
    offset = 0
    while True:
        page = get_events(since=since_ms, limit=500, offset=offset)
        out.extend(page)
        if len(page) < 500:
            break
        offset += len(page)
    return out


def prune_events(keep_ms: int) -> int:
    cutoff = int(time.time() * 1000) - keep_ms
    c = _conn()
    cur = c.execute("DELETE FROM events WHERE published < ?", (cutoff,))
    return cur.rowcount


def set_indicator(ind: dict) -> None:
    c = _conn()
    c.execute(
        """INSERT OR REPLACE INTO indicators
           (series_id, name, category, unit, latest_value, latest_date, updated, history)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ind["series_id"], ind["name"], ind["category"], ind.get("unit"),
         ind.get("latest_value"), ind.get("latest_date"), int(time.time() * 1000),
         json.dumps(ind.get("history", []))),
    )


def get_indicator(series_id: str) -> Optional[dict]:
    """Look up a single indicator by series_id — avoids loading all indicators."""
    c = _conn()
    row = c.execute("SELECT * FROM indicators WHERE series_id = ?", (series_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["history"] = json.loads(d["history"])
    return d


def get_indicators() -> list:
    c = _conn()
    rows = c.execute("SELECT * FROM indicators").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["history"] = json.loads(d["history"])
        out.append(d)
    return out


def set_source_status(source: str, last_ok: bool, last_error: Optional[str] = None,
                      count: int = 0, cooldown_until: Optional[int] = None) -> None:
    c = _conn()
    c.execute(
        """INSERT OR REPLACE INTO source_status (source, last_run, last_ok, last_error, count, cooldown_until)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (source, int(time.time() * 1000), 1 if last_ok else 0, last_error, count, cooldown_until),
    )


def get_source_status() -> list:
    c = _conn()
    rows = c.execute("SELECT * FROM source_status").fetchall()
    return [dict(r) for r in rows]


def is_in_cooldown(source: str) -> bool:
    c = _conn()
    row = c.execute("SELECT cooldown_until FROM source_status WHERE source = ?", (source,)).fetchone()
    return bool(row and row["cooldown_until"] and row["cooldown_until"] > time.time() * 1000)


def set_cooldown(source: str, minutes: int) -> None:
    c = _conn()
    c.execute(
        """INSERT INTO source_status (source, cooldown_until, last_ok, count) VALUES (?, ?, 0, 0)
           ON CONFLICT(source) DO UPDATE SET cooldown_until = excluded.cooldown_until""",
        (source, int(time.time() * 1000) + minutes * 60_000),
    )


def register_device_token(token: str) -> None:
    c = _conn()
    c.execute("INSERT OR REPLACE INTO device_tokens (token, registered) VALUES (?, ?)", (token, int(time.time())))


def get_device_tokens() -> list:
    c = _conn()
    rows = c.execute("SELECT token FROM device_tokens").fetchall()
    return [r["token"] for r in rows]


def get_kv(key: str) -> str | None:
    c = _conn()
    row = c.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_kv(key: str, value: str) -> None:
    c = _conn()
    c.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, value))
