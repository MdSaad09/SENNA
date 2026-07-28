#!/bin/sh
# The DB tests drop and recreate every table, so they run against their own database and
# senna.data.db.require_disposable refuses anything not named *_test. Creating it here
# means a fresh `docker compose up` is ready for `pytest tests/api` without a manual step.
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
    CREATE DATABASE ${POSTGRES_DB}_test OWNER $POSTGRES_USER;
SQL
