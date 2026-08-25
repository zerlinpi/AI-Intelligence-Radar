#!/bin/sh
set -e

# Run database migration before starting application
if [ -f scripts/migrate_db.py ]; then
  echo "Running database migration..."
  python scripts/migrate_db.py || {
    echo "Database migration failed"
    exit 1
  }
fi

echo "Starting AI Intelligence Radar..."
exec "$@"
