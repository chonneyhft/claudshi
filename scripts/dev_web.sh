#!/usr/bin/env bash
# Run the API + web dev server together. Ctrl-C stops both.
set -euo pipefail

cd "$(dirname "$0")/.."

cleanup() {
  echo
  echo "shutting down…"
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [ ! -d web/node_modules ]; then
  echo "→ installing web dependencies"
  (cd web && npm install)
fi

echo "→ starting FastAPI on http://127.0.0.1:8000"
.venv/bin/uvicorn api.server:app --port 8000 --reload --log-level warning &

echo "→ starting Vite on http://127.0.0.1:5173"
(cd web && npm run dev) &

wait
