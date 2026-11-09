#!/usr/bin/env bash
# Development mode: FastAPI (auto-reload) on :8000 and Vite on :5173. Both bind to localhost only.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Missing .venv. Run: python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt"; exit 1; }
[ -d frontend/node_modules ] || { echo "Missing frontend deps. Run: (cd frontend && npm install)"; exit 1; }

.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload &
API=$!
trap 'kill $API 2>/dev/null || true' EXIT INT TERM
(cd frontend && npm run dev)
