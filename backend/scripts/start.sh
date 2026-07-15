#!/usr/bin/env sh
set -eu

if [ "${RUN_DB_INIT:-true}" = "true" ]; then
  PYTHONPATH=/app python /app/scripts/init_db.py
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
