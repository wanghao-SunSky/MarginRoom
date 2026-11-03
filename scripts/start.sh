#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv sync
if [ ! -f web/dist/index.html ]; then
  if [ -x /usr/local/opt/node@22/bin/node ]; then export PATH="/usr/local/opt/node@22/bin:$PATH"; fi
  (cd web && npm ci && npm run build)
fi
exec uv run uvicorn backend.app:app --host 127.0.0.1 --port "${READING_PORT:-8765}"
