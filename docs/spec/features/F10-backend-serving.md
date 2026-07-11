# F10 — Backend: API, worker, WebSocket, deploy skeleton

Depends on: F07, F09
Spec anchors: 5.9.2, 5.9.3, 5.11, E-15, E-16, F-23, F-26, F-27

## Goal
The serving layer: FastAPI plus an RQ worker running the frozen model triplet,
playback-clock WebSocket streaming from stored frames, versioned caching — deployed
early so deployment risk dies now, not in November.

## Deliverables
- REST endpoints per 5.9.2 with the given Pydantic shapes: circuits, races, simulations (create/status/frames/decisions), counterfactuals, agents registry, energy, tyres, health
- Worker: runs the whole race immediately, persists every LapFrame and DecisionCard, publishes to Redis; the API streams to browsers on a playback clock (1x/5x/10x/30x) reading stored frames — pause, scrub and reconnect all replay from the same store (E-16)
- Redis cache keyed sim:{model_version}:{env_hash}:{seed} with a 7-day TTL backstop (E-15); queue and pub/sub channels per 5.9.3
- The model triplet baked into the worker image at /app/models; MODEL_VERSION selects it (F-26 — Railway filesystems are ephemeral, so nothing is mounted)
- Environment scheme per 5.11.2: relative /api and /ws behind a local proxy; the public Railway URL and wss:// in production builds (F-27); WANDB_API_KEY absent from serving
- Railway deploy of the skeleton; alembic migrates on api start; the Makefile targets become real where they can

## Out of scope
All six views (F11–F13); evaluation content (F14).

## Constants & configs
- Cache TTL, playback speeds, CORS allowlist — sourced 5.9/5.11 — configs/serving.yaml

## Tests first
- Integration: POST /simulations -> worker -> frames retrievable -> WS streams on the playback clock; disconnect mid-race, reconnect, zero frames lost (E-16)
- Cache: identical request body under a new MODEL_VERSION is a cache miss (E-15)
- Build check: the production frontend bundle contains no Docker-internal hostname (F-27)
- Event loop: a running simulation never blocks /health beyond a stated threshold

## Done means
- A full simulation round-trip streams over WS locally and on Railway; the public health URL is live
- The frozen triplet loads with training=False and matches training-eval actions on a fixed state (the F-23 cross-check)
- A redeploy loses nothing that matters — no mounted models, no local state

## Notes for the plan session
Worker and api share one image; keep the boundary at the queue. Deploy the ugly skeleton
the same week — that is the entire point of this feature's position in the order.
