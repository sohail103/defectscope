#!/usr/bin/env bash
# Single-process mode: builds the frontend once and serves everything from http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Missing .venv. Run: python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt"; exit 1; }
if [ ! -d frontend/dist ]; then
  (cd frontend && npm install && npm run build)
fi
echo "DefectScope running at http://127.0.0.1:8000"
exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
