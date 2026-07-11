# F00 — Repo skeleton, CI & spec split

Depends on: —
Spec anchors: master spec Part 6.2 Phase 0, 5.9.1 (pinned stack), 5.11 (compose and services), docs/spec/README.md

## Goal
A repo that runs before it does anything: local compose brings up postgres, redis, a
hello-world FastAPI and a hello-world Vite app; CI runs pytest and vitest on push;
lockfiles pin the stack; and the master spec is split into per-section markdown so every
later session reads only what it needs.

## Deliverables
- Folder structure per the root CLAUDE.md repo map (senna/, api/, worker/, frontend/, configs/, tests/, docs/, notebooks/)
- docker-compose.yml: postgres:16-alpine, redis:7-alpine, api (uvicorn with /api/v1/health), frontend (vite dev server)
- Pinned lockfiles per spec 5.9.1 (pip-compile or uv lock; package-lock.json). React 18.3 + R3F 8 — never React 19
- GitHub Actions: pytest + vitest + lint on push
- docs/spec/5.x-*.md, 2-edge-cases.md and 8-assumptions.md extracted from the PDF in docs/spec/source/ (F1SIP -> SENNA in prose only)
- Makefile stubs: ingest / fit / train / eval / report (each echoes "not yet") — the reproducibility-pack skeleton (A-09)

## Out of scope
Any real ingestion, physics, env or UI code. Railway deployment (F10 owns it).

## Constants & configs
None beyond the pins — the pins ARE this feature's constants. Record the exact SB3 +
sb3-contrib pair chosen (5.9.1: verify the latest matching minors now, freeze in the lockfile).

## Tests first
- test_health_endpoint returns 200 with {"status": "ok"} locally
- CI runs one trivial pytest and one trivial vitest and goes green
- A check script: every "Spec anchors" file referenced by docs/spec/features/*.md exists on disk

## Done means
- `docker compose up` green on all four services; /api/v1/health reachable from the host browser
- CI green on the first push
- Lockfiles committed; a fresh clone reproduces the environment
- All spec section files exist and INDEX.md links resolve
- No "F1SIP" remains in prose anywhere in the repo

## Notes for the plan session
The PDF must sit in docs/spec/source/ before /ship. Extract faithfully — the 5.2, 5.5.1,
5.5.4 and 5.12 tables are load-bearing; carry them over intact. MaskablePPO lives in
sb3-contrib and its minor version must match stable-baselines3's — check before locking.
