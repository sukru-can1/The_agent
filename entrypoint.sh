#!/bin/sh
set -e

# Run migrations
uv run python migrations/migrate.py || echo 'Migration warning'

# Start in worker or webhook mode
if [ "$SERVICE_MODE" = "worker" ]; then
    echo "Starting worker (consumer + scheduler)..."
    exec uv run python -m agent1.worker.main
else
    echo "Starting webhook server..."
    exec uv run python -m uvicorn agent1.webhook.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}
fi
