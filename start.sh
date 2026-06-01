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

echo "Starting Ledger UI server on http://127.0.0.1:${UI_PORT} ..."

# Find local IP for sharing
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ifconfig | awk '/inet / && $2 != "127.0.0.1" {print $2; exit}')
if [[ -z "$LOCAL_IP" ]]; then LOCAL_IP="127.0.0.1"; fi


# Helper to check if a port is open (server running)
is_port_open() {
  local port="$1"
  nc -z 127.0.0.1 "$port" >/dev/null 2>&1
}

# Detect running API server
if is_port_open "$API_PORT"; then
  API_RUNNING=1
  echo "Detected running API server on port $API_PORT."
else
  API_RUNNING=0
  echo "Starting Medici API on http://0.0.0.0:${API_PORT} (accessible at http://${LOCAL_IP}:${API_PORT}) ..."
  "$PYTHON_BIN" "$ROOT_DIR/pipeline_api_server.py" --host 0.0.0.0 --port "$API_PORT" &
  API_PID=$!
fi

# Detect running UI server
if is_port_open "$UI_PORT"; then
  UI_RUNNING=1
  echo "Detected running UI server on port $UI_PORT."
else
  UI_RUNNING=0
  echo "Starting Ledger UI server on http://0.0.0.0:${UI_PORT} (accessible at http://${LOCAL_IP}:${UI_PORT}) ..."
  "$PYTHON_BIN" -m http.server "$UI_PORT" --bind 0.0.0.0 --directory "$ROOT_DIR" &
  UI_PID=$!
fi

open_dashboard() {
  local dashboard_url="http://${LOCAL_IP}:${UI_PORT}/branch_operations_dashboard.html"
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
echo "  API:     http://${LOCAL_IP}:${API_PORT}  (or http://localhost:${API_PORT})"
echo "  UI :     http://${LOCAL_IP}:${UI_PORT}/branch_operations_dashboard.html  (or http://localhost:${UI_PORT}/branch_operations_dashboard.html)"
echo "  Manager: http://${LOCAL_IP}:${UI_PORT}/branch_operations_dashboard.html?role=branch_manager&branch=Florence&manager=Florence%20Manager"
echo "  Ledger Manager: http://${LOCAL_IP}:${UI_PORT}/transaction_ledger_view.html?role=branch_manager&branch=Florence"
echo "  Ledger:  http://${LOCAL_IP}:${UI_PORT}/transaction_ledger_view.html  (or http://localhost:${UI_PORT}/transaction_ledger_view.html)"
echo
echo "Share the http://${LOCAL_IP} URLs with your teammates."
if [[ $API_RUNNING -eq 1 ]]; then
  echo "API server was already running. Not started by this script."
fi
if [[ $UI_RUNNING -eq 1 ]]; then
  echo "UI server was already running. Not started by this script."
fi
echo "Press Ctrl+C to stop any servers started by this script."


# Only wait on servers started by this script
if [[ $API_RUNNING -eq 0 && $UI_RUNNING -eq 0 ]]; then
  wait "$API_PID" "$UI_PID"
elif [[ $API_RUNNING -eq 0 ]]; then
  wait "$API_PID"
elif [[ $UI_RUNNING -eq 0 ]]; then
  wait "$UI_PID"
else
  # Both were already running; just wait for user to exit
  while true; do sleep 3600; done
fi
