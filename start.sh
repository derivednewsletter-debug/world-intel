#!/usr/bin/env bash
# 🌍 World Intelligence — one-command start.
# Works on macOS, Linux, and Git Bash on Windows.
#   ./start.sh            → starts everything (first run sets up the env)
#   PORT=8080 ./start.sh  → optional: different port
set -euo pipefail

cd "$(dirname "$0")/backend"

# Pick the venv python (Windows/Git Bash uses Scripts/, unix uses bin/)
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
else
  echo "🔧 First run — creating the Python environment (one time)…"
  python3 -m venv .venv
  if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY=".venv/Scripts/python.exe"; fi
fi

# Install dependencies only when requirements.txt changed.
if [ ! -f ".venv/.reqstamp" ] || [ "requirements.txt" -nt ".venv/.reqstamp" ]; then
  echo "📦 Installing dependencies (one time)…"
  "$PY" -m pip install --quiet -r requirements.txt
  touch .venv/.reqstamp
fi

echo "🌍 World Intelligence → http://localhost:${PORT:-4173}"
echo "   (Ctrl+C to stop)"
exec "$PY" -m app.server
