#!/bin/bash
set -e

# Toggle between direct postgres connection and pgbouncer
# This script should be run from the project root

# Check if .env-direct exists
if [ ! -f .env-direct ]; then
    echo "Creating .env-direct backup of current .env..."
    cp .env .env-direct
fi

# Check current connection type
if grep -q "DATABASE_URL=postgres://kitsune:kitsune@pgbouncer:6432/kitsune" .env; then
    echo "Currently using PgBouncer. Switching to direct Postgres connection..."
    cp .env-direct .env
    echo "Now using direct Postgres connection."
else
    echo "Currently using direct Postgres. Switching to PgBouncer..."
    cp .env-pgbouncer .env
    echo "Now using PgBouncer. Remember to ensure the pgbouncer service is running."
fi

echo "Done! You may need to restart your application for changes to take effect." 