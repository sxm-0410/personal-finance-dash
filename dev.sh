#!/usr/bin/env bash
# Start the backend (FastAPI :8000) and frontend (Vite :5173) together.
# Ctrl-C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.local/bin:$PATH"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "→ Backend on http://localhost:8000  (docs at /docs)"
(
  cd "$ROOT/backend"
  uv run alembic upgrade head
  uv run uvicorn app.main:app --reload --port 8000
) &

echo "→ Frontend on http://localhost:5173"
(
  cd "$ROOT/frontend"
  npm run dev
) &

wait
