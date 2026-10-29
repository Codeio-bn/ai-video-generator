#!/usr/bin/env bash
# SCP Video Studio — dev launcher (Linux/macOS)
# Starts BOTH servers in one command: the FastAPI backend (hot reload) and the
# Vite frontend dev server. One Ctrl+C stops both.
# Run from anywhere:  ./scripts/dev.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
py="$root/.venv/bin/python"

if [ ! -x "$py" ]; then
    echo "Python venv not found. Run ./scripts/setup.sh first." >&2
    exit 1
fi
if [ ! -d "$root/frontend/node_modules" ]; then
    echo "Frontend deps not installed. Run ./scripts/setup.sh first." >&2
    exit 1
fi

pids=()
cleanup() {
    # Each server runs in its own session, so a negative PID kills the whole
    # process group (uvicorn's reloader spawns children we also want gone).
    for pid in "${pids[@]}"; do
        kill -- -"$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    echo
    echo "Stopped both servers."
}
trap cleanup EXIT INT TERM

setsid bash -c "cd '$root/backend' && exec '$py' -m uvicorn app.main:app --reload --reload-dir app --port 8000" &
pids+=($!)

setsid bash -c "cd '$root/frontend' && exec npm run dev" &
pids+=($!)

echo
echo "  Backend   http://127.0.0.1:8000  (API, hot reload)"
echo "  Frontend  http://127.0.0.1:5173  <- open this one"
echo "  Press Ctrl+C to stop both."
echo

# Wait for either server to exit; the EXIT trap then stops the other.
wait -n
