#!/bin/bash
# connect_servers.sh
# Ensures both API and UI servers are running on the correct local addresses for MediciMess

set -e

API_HOST="127.0.0.1"
API_PORT="8000"
UI_HOST="127.0.0.1"
UI_PORT="5500"

# Activate virtual environment if present
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

# Start Medici API Server
if ! lsof -i :$API_PORT | grep LISTEN > /dev/null; then
    echo "Starting Medici API Server on $API_HOST:$API_PORT..."
    nohup .venv/bin/python pipeline_api_server.py --host $API_HOST --port $API_PORT > api_server.log 2>&1 &
    sleep 2
else
    echo "Medici API Server already running on $API_HOST:$API_PORT."
fi

# Start Ledger UI Server
if ! lsof -i :$UI_PORT | grep LISTEN > /dev/null; then
    echo "Starting Ledger UI Server on $UI_HOST:$UI_PORT..."
    nohup .venv/bin/python -m http.server $UI_PORT --bind $UI_HOST > ui_server.log 2>&1 &
    sleep 2
else
    echo "Ledger UI Server already running on $UI_HOST:$UI_PORT."
fi

echo "\nServers are running!"
echo "- API:    http://$API_HOST:$API_PORT"
echo "- Ledger: http://$UI_HOST:$UI_PORT"
echo ""
echo "Share these URLs with your teammate to ensure you are both connected to the same local servers."
