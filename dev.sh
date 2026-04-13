#!/usr/bin/env bash
set -euo pipefail

VENV_DIR=".venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# Install/sync deps
pip install -q -e ".[dev]"

# Dev defaults — override via env
export POWERADMIN_DATABASE_PATH="${POWERADMIN_DATABASE_PATH:-./dev.db}"
export POWERADMIN_SECRET_KEY="${POWERADMIN_SECRET_KEY:-dev-secret-key-change-in-prod}"
export POWERADMIN_DEFAULT_ADMIN_PASSWORD="${POWERADMIN_DEFAULT_ADMIN_PASSWORD:-admin}"

echo "DB: $POWERADMIN_DATABASE_PATH"
echo "Starting FastAPI dev server at http://localhost:8080"

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --reload \
    --reload-dir app
