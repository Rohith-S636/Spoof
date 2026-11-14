#!/bin/sh
# Starts the central stand-in (port 9000) and the kiosk (port 8000).
# Open http://localhost:8000  — stop with Ctrl+C.
cd "$(dirname "$0")/../backend"
PY=../.venv/bin/python
$PY -m uvicorn central:app --port 9000 --log-level warning &
CENTRAL=$!
trap 'kill $CENTRAL 2>/dev/null' EXIT
$PY -m uvicorn main:app --port 8000 --log-level warning
