# Deploying SENNA's serving layer

**Local compose is the supported, verified target** (decision, 22 Jul 2026 — INDEX
decisions log): the dissertation deliverable is a reproducible codebase plus the
presentation video, and a marker can run the full stack from a clean clone. The
Railway section below keeps the layer deployment-ready per 5.11.1, but it has NOT
been executed against a real Railway project — treat it as a runbook, not a record.

Both targets run the same image from `Dockerfile.api` — the api and the worker
differ only in start command, and the frozen model triplets (headline and era2024),
their surrogates and the built ribbons are baked in at `/app/models` and
`/app/data/circuits` (F-26: ephemeral filesystems, no serving artifact is ever
mounted; also exactly what makes the clean-clone compose run work). The one mount
in local compose is the frontend service itself — a vite dev server over a
`./frontend` bind mount, which is a dev convenience, not a serving artifact.

## Local (docker compose)

    docker compose up --build          # postgres, redis, api, worker, frontend
    curl localhost:8000/api/v1/health  # {"status":"ok","model_version":"senna-ppo-..."}
    open http://localhost:5173         # the dashboard (vite dev server)

The api entrypoint runs `alembic upgrade head` before serving; the worker runs the
same migration idempotently in case it boots first on a fresh database. A smoke
round trip:

    curl -s -X POST localhost:8000/api/v1/simulations \
      -H 'content-type: application/json' \
      -d '{"circuit_id": "bahrain_grand_prix", "grid_position": 5, "seed": 42}'
    # then, with the returned run_id:
    curl -s localhost:8000/api/v1/simulations/<run_id>          # status: complete
    curl -s "localhost:8000/api/v1/simulations/<run_id>/frames?from_lap=1&to_lap=3"
    npx wscat -c ws://localhost:8000/ws/simulations/<run_id>    # sim:lap stream

## Railway (unverified runbook — deploy deferred by decision)

One project, four services. Saad drives the dashboard steps (account, plugins);
the repo carries everything else. Revisit only if a live URL is wanted before the
viva.

1. **Plugins**: add Railway Postgres and Railway Redis. They inject `DATABASE_URL`
   and `REDIS_URL` as service references.
2. **api service**: deploy from this repo with `Dockerfile.api`. Settings:
   - start command: `scripts/start_api.sh` (the Dockerfile default; Railway's PORT
     is honoured)
   - healthcheck path: `/api/v1/health`
   - env: `DATABASE_URL`, `REDIS_URL` (plugin references), `CORS_ORIGIN` = the
     frontend's public origin once F11 deploys it
3. **worker service**: same repo, same Dockerfile, start command
   `scripts/start_worker.sh`, same `DATABASE_URL`/`REDIS_URL`. No public domain.
4. **frontend** (F11): static build with `VITE_API_BASE=https://<api>.up.railway.app/api`
   and `VITE_WS_BASE=wss://<api>.up.railway.app/ws` — browser-reachable URLs only,
   baked at build time (F-27), wss or browsers block mixed content (5.11.2).

`WANDB_API_KEY` is absent from every serving service by design (F-26).
`MODEL_VERSION` may be set to pin the served triplet; unset means the promoted
headline, and a version the image does not bake fails at startup rather than
falling back.

During /ship the deploy runs `railway up` from the feature branch, so nothing
auto-deploys from an unmerged main; wiring GitHub main auto-deploy is a post-/land
step in the dashboard.

### The redeploy drill (the F10 acceptance item)

Delete and redeploy the api and worker services, then re-run the smoke round trip
with the same body. Nothing should be lost or rebuilt by hand: models come from the
image, state from the plugins — and the same request under the same MODEL_VERSION
hits the E-15 cache, while a bumped MODEL_VERSION cold-starts its own namespace.

## Known limitation, stated on purpose

`weather_profile` "mixed" and "wet_risk" both run the env's markov weather engine
(decision Q2, 22 Jul 2026) — the env exposes two weather modes, not three. The
requested profile is recorded verbatim on the run and echoed by the API, so the
distinction survives in the data even though the physics does not yet honour it.
