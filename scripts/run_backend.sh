#!/usr/bin/env bash
set -euo pipefail

# Simple runner for the Aura backend
# - Activates root .venv if present (and not already active)
# - Checks Python >= 3.10
# - Ensures uvicorn is installed
# - Runs uvicorn pointing to the backend app dir

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/AURA/aura-backend"

if [[ ! -d "$BACKEND_DIR/app" ]]; then
  echo "Backend directory not found at: $BACKEND_DIR" >&2
  exit 1
fi

# Activate repo venv if available and not already active
if [[ -z "${VIRTUAL_ENV:-}" && -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  echo "Activating venv: $ROOT_DIR/.venv"
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
fi

PY="${PYTHON:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python not found in PATH. Ensure a venv is activated." >&2
  exit 1
fi

# Check Python version >= 3.10
MAJOR_MINOR="$($PY - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

MAJOR="${MAJOR_MINOR%%.*}"
MINOR="${MAJOR_MINOR#*.}"

if (( MAJOR < 3 )) || { (( MAJOR == 3 )) && (( MINOR < 10 )); }; then
  echo "Python 3.10+ required. Current: $MAJOR_MINOR" >&2
  echo "Create a new venv with Python 3.11 and reinstall deps." >&2
  echo "Example: python3.11 -m venv .venv && source .venv/bin/activate" >&2
  exit 1
fi

# Check uvicorn installed in current interpreter
if ! $PY -c "import uvicorn" >/dev/null 2>&1; then
  echo "Uvicorn not installed in this environment." >&2
  echo "Install deps with:" >&2
  echo "  $PY -m pip install -r $BACKEND_DIR/requirements.txt" >&2
  exit 1
fi

PORT="${PORT:-8000}"
echo "Running backend on http://127.0.0.1:$PORT"
echo "Working dir: $BACKEND_DIR (ensures .env is loaded)"
cd "$BACKEND_DIR"
exec "$PY" -m uvicorn app.main:app --reload --port "$PORT"
