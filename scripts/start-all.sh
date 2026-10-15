#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# DocuTrace - start backend and frontend together (macOS / Linux / Git Bash).
#
# Usage (from the repository root):
#     bash scripts/start-all.sh
#
# Both servers run in the foreground of this shell; Ctrl+C stops both.
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "$ROOT/backend/app/main.py" ]]; then
  echo "[error] Could not find the backend at $ROOT/backend." >&2
  exit 1
fi
if [[ ! -f "$ROOT/frontend/package.json" ]]; then
  echo "[error] Could not find the frontend at $ROOT/frontend." >&2
  exit 1
fi

# Prefer the project virtualenv's uvicorn if one exists.
if [[ -x "$ROOT/backend/.venv/bin/uvicorn" ]]; then
  UVICORN="$ROOT/backend/.venv/bin/uvicorn"
else
  UVICORN="uvicorn"
fi

cleanup() {
  echo
  echo "Stopping DocuTrace..."
  # Kill the whole process group so Vite's child processes go too.
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting DocuTrace..."
echo "  backend  -> http://127.0.0.1:8000"
echo "  frontend -> http://127.0.0.1:5173"
echo

(cd "$ROOT/backend" && "$UVICORN" app.main:app --reload --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

# Wait for the API to answer before starting Vite, so the first page load is
# not a proxy error.
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "Backend is healthy."
    break
  fi
  sleep 1
done

(cd "$ROOT/frontend" && npm run dev) &
FRONTEND_PID=$!

echo "Both servers running. Press Ctrl+C to stop."
wait "$BACKEND_PID" "$FRONTEND_PID"
