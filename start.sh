#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5500}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python environment at $PYTHON_BIN"
  echo "Run: make setup"
  exit 1
fi

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${UI_PID:-}" ]]; then
    kill "$UI_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "Starting Medici API on http://127.0.0.1:${API_PORT} ..."
"$PYTHON_BIN" "$ROOT_DIR/pipeline_api_server.py" --host 127.0.0.1 --port "$API_PORT" &
API_PID=$!

echo "Starting Ledger UI server on http://127.0.0.1:${UI_PORT} ..."
"$PYTHON_BIN" -m http.server "$UI_PORT" --bind 127.0.0.1 --directory "$ROOT_DIR" &
UI_PID=$!

open_dashboard() {
  local dashboard_url="http://127.0.0.1:${UI_PORT}/branch_operations_dashboard.html"
  for _ in {1..30}; do
    if curl -fsS "$dashboard_url" >/dev/null 2>&1; then
      open "$dashboard_url"
      return 0
    fi
    sleep 1
  done

  echo "Could not confirm the dashboard was ready, so open this URL manually: $dashboard_url"
}

open_dashboard &

echo
echo "Stack is running:"
echo "  API: http://127.0.0.1:${API_PORT}"
echo "  UI : http://127.0.0.1:${UI_PORT}/branch_operations_dashboard.html"
echo "  Ledger: http://127.0.0.1:${UI_PORT}/transaction_ledger_view.html"
echo
echo "Press Ctrl+C to stop both servers."

wait "$API_PID" "$UI_PID"
