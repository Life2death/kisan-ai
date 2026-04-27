#!/bin/bash
set -e

echo "Waiting for database to be reachable..."
MAX_RETRIES=15
RETRY_DELAY=5

for i in $(seq 1 $MAX_RETRIES); do
    if alembic upgrade head 2>&1; then
        echo "Migrations applied successfully."
        break
    fi

    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "Database unreachable after $MAX_RETRIES attempts. Exiting."
        exit 1
    fi

    echo "Attempt $i/$MAX_RETRIES failed — retrying in ${RETRY_DELAY}s..."
    sleep "$RETRY_DELAY"
done

exec uvicorn src.main:app --host 0.0.0.0 --port 8000
