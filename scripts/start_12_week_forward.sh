#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON="$ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "Create .venv and install requirements-app.txt first." >&2
  exit 1
fi

cd "$ROOT"
"$PYTHON" -m scripts.start_defensive_forward --db runtime/trader.db --capital 500
echo "Forward paper is active. Keep this process running."
echo "Dashboard: http://127.0.0.1:8765"
exec "$PYTHON" -m trader --db runtime/trader.db serve
