#!/bin/sh
# worker entrypoint. The migration is idempotent and deliberate: on a fresh deploy
# the worker can boot before the api's first migration, and a job that lands on a
# missing lap_frames table would fail for no honest reason.
set -e
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"  # the F09 arm64/openmp landmine
alembic upgrade head
QUEUE="$(python -c "from senna import config; print(config.load('serving')['queue']['name'])")"
exec rq worker --url "$REDIS_URL" "$QUEUE"
