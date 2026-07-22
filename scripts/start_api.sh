#!/bin/sh
# api entrypoint, compose and Railway alike: alembic migrates on api start (5.11.1),
# then uvicorn serves. Railway injects PORT; compose takes the 8000 default.
set -e
alembic upgrade head
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
