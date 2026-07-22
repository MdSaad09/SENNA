#!/bin/sh
# worker entrypoint. The migration is idempotent and deliberate: on a fresh deploy
# the worker can boot before the api's first migration, and a job that lands on a
# missing lap_frames table would fail for no honest reason.
set -e
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"  # the F09 arm64/openmp landmine
alembic upgrade head
QUEUE="$(python -c "from senna import config; print(config.load('serving')['queue']['name'])")"
# SimpleWorker on purpose: the default worker forks a work horse per job, which
# throws away the process-level model/explainer caches and re-imports torch every
# race. One process, loaded once (F-26); the platform restarts it if a job kills it.
exec rq worker -w rq.SimpleWorker --url "$REDIS_URL" "$QUEUE"
