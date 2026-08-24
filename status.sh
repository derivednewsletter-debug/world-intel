#!/usr/bin/env bash
# World Intelligence - source health + event count at a glance.
# Usage: ./status.sh [url]   (defaults to http://localhost:4173)
set -u

URL="${1:-http://localhost:4173}"

# Prefer the project's venv python; fall back to a working system python
# (the Windows Store "python3" stub exists but does nothing).
PY=""
if [ -x "backend/.venv/Scripts/python.exe" ]; then
    PY="backend/.venv/Scripts/python.exe"
elif [ -x "backend/.venv/bin/python" ]; then
    PY="backend/.venv/bin/python"
else
    for c in python python3; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then
            PY="$c"; break
        fi
    done
fi
if [ -z "$PY" ]; then
    echo "  X no working python found - run ./start.sh once to create the environment"
    exit 1
fi

echo "World Intelligence - $URL"

if ! curl -s -m 10 "$URL/api/health" | "$PY" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
print("  status:", d["status"], " | ", format(d["total"], ","), "events | up", d["uptimeSec"] // 60, "min")
' 2>/dev/null; then
    echo "  X server not reachable - start it with ./start.sh (or start.bat)"
    exit 1
fi

echo ""
curl -s -m 10 "$URL/api/sources" | "$PY" -c '
import json, sys
srcs = json.load(sys.stdin)["sources"]
ok = [s for s in srcs if s["last_ok"]]
down = [s for s in srcs if not s["last_ok"]]
print("  sources:", len(ok), "/", len(srcs), "healthy")
for s in sorted(down, key=lambda x: x["source"]):
    err = (s.get("last_error") or "never ran").strip().replace(chr(10), " ")
    print("    X", s["source"], ":", err[:80])
' 2>/dev/null || true
