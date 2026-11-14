#!/bin/bash
set -e

echo "[entrypoint] Running database migrations..."
python -m alembic upgrade head || {
    echo "[entrypoint] Warning: Alembic migration reported an issue or already initialized, continuing..."
}

echo "[entrypoint] Starting application process: $@"
exec "$@"

