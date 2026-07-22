# F10 — Backend: API, worker, WebSocket, deploy skeleton — plan

Approved by Saad, 22 Jul 2026. Feature spec: docs/spec/features/F10-backend-serving.md.
Spec anchors: 5.9.2, 5.9.3, 5.11, E-15, E-16, F-23, F-26, F-27.

## Context

F08 promoted the frozen headline checkpoint (`senna-ppo-6b6edb78d84e-C-00835584`,
models/headline/); F09 distilled it into the fidelity-badged surrogate
(models/explain/<version>/) and put 14,460 cards into agent_decisions. F10 is the
serving layer over both: FastAPI + an RQ worker running the frozen triplet, WebSocket
streaming on a playback clock, versioned Redis caching, and a Railway deploy of the
skeleton — deployed early so deployment risk dies now, not in November.

The groundwork already exists: the triplet loader with training=False
(senna/train/checkpoints.py `load_triplet`), the deterministic eval policy head
(senna/train/evals.py `Sb3Policy`), the whole-race helper
(senna/strategy/rollout.py `run_episode`), the card builder with its version guard
(senna/explain/cards.py), card persistence with the purpose discriminator
(senna/explain/persist.py), the config fingerprint that becomes env_config_hash
(senna/config.py), SimulationRun/AgentDecision tables with alembic wired into CI,
docker-compose with postgres/redis/api/frontend, Dockerfile.api, and every serving
dependency already locked in requirements.txt. The worker/ directory is an empty
placeholder; api/main.py is a health-only stub. Nothing WebSocket-, RQ- or
LapFrame-shaped exists yet.

## Objective

Ship the 5.9.2 REST surface, the worker running the frozen model triplet, playback-clock
WS streaming from stored frames, E-15 versioned caching, and the deploy skeleton —
locally on compose and on Railway.

## Flagged spec divergences

Recorded here as the paper trail; added to INDEX's decisions log at /land.

1. **The 5.9.3 cache key collides as written.** `sim:{model_version}:{env_hash}:{seed}`
   has no scenario term — two circuits, same seed, one env_hash. E-15's requirement is
   that keys *include* model_version and env_config_hash, so the key becomes
   `sim:{model_version}:{env_hash}:{scenario_digest}:{seed}`, scenario_digest = sha256
   over the canonical request body minus seed/model_version. env_hash is read from the
   loaded triplet's manifest fingerprint, never recomputed at serve time.
2. **rival_band defaults disagree**: SimulationCreate defaults "test" (5.9.2), the env
   constructor defaults "train" (race_env.py). The API always passes the field
   explicitly; no env change.
3. **5.3.5's simulated-row laps columns** exist since F01, but serving frames go to a
   new lap_frames JSONB table matching the read pattern (paginated per-lap frames).
   Per-driver laps rows for simulated races are F14's evaluation concern.
4. **"22 entries" / grid le=22 vs era 2024.** physics_2024.yaml fields 20 cars, so an
   era-2024 run yields 20 CarState entries and grid_position must be <= the era's grid
   size (422 otherwise). The 5.9.2 wording assumes 2026; n_cars comes from the env.
5. **agent:decision vs sim:lap.** 5.8.2 streams live cards "in the agent:decision
   event"; 5.9.3's WS contract has no such event and puts the card in sim:lap. The WS
   contract section wins: cards ride sim:lap, agent:decision is not emitted.
6. **Local WS scheme.** The feature spec says relative /ws behind the vite proxy;
   master 5.11.2 says VITE_WS_BASE=ws://localhost:8000/ws locally. Master spec wins:
   no /ws proxy, compose sets VITE_WS_BASE=ws://localhost:8000/ws, prod builds get
   wss://<api>.up.railway.app/ws.
7. **Dockerfile.worker.** 5.11.1 names it, parenthetically "(same image as api)". Both
   services build Dockerfile.api with different start commands — one image, as the
   parenthetical and the feature spec intend; no literal second Dockerfile.

## Deliverables

### Config and contract
- `configs/serving.yaml` — every serving constant with provenance (table below).
- `configs/README.md`, root `CLAUDE.md`, `.claude/agents/spec-auditor.md` — a fourth
  provenance origin, **operational**: an explicit engineering default (timeout, page
  size, poll cadence), stated and reviewable, distinct from stylised visual choices.
  Saad's call, 22 Jul 2026, in preference to widening stylised.

### API (api/)
- `api/schemas.py` — the 5.9.2 models verbatim: SimulationCreate, JobAccepted,
  SimulationResult, LapFrame (CarState, AgentState, RaceEvent), DecisionCard,
  CircuitSummary, CircuitDetail, RaceDetail, ModelVersion, EnergyProfile,
  DegradationCurve, plus WS event envelopes.
- `api/main.py` (rewrite of the stub) — app factory; lifespan owns the async engine +
  redis client; CORS from serving.yaml; an X-Model-Version header stamped on every
  response by middleware (5.11.2's "part of every API response" without touching the
  5.9.2 shapes); static mount /api/v1/assets/circuits -> data/circuits, with gltf_url
  emitted **relative** so no server-side hostname can leak past the F-27 check.
- `api/deps.py` — request-scoped AsyncSession, redis, settings.
- `api/routes/` — circuits.py (summary + detail; detail embeds the F04 meta.json
  annotations — corners, braking_zones, xmode_sections — plus h_max_mj; coverage
  flags computed from what is built), races.py, simulations.py (a missing seed is
  drawn server-side *before* the cache key is built and echoed in SimulationResult;
  an explicit model_version must match a baked manifest or the POST 4xxs, None
  resolves to the served MODEL_VERSION), counterfactuals.py, agents.py, energy.py,
  tyres.py, health.py (manifest read only — no torch import in the API process).
- `api/ws.py` — /ws/simulations/{run_id}: playback clock (1x = simulated lap seconds;
  inter-frame delay = lap_time/speed), client:speed/pause/seek; sim:event messages
  derived from LapFrame.events during playback; if the run is still queued/running,
  waits on events:{run_id} then streams. Injectable timer so tests never sleep.

### Serving logic (senna/serve/, importable by api/ and worker/)
- `mapping.py` — SimulationCreate -> env construction: circuit validated against
  physics_params; era passthrough; rival_band explicit; weather_profile map
  (dry->dry, mixed/wet_risk->markov — approved Q2 — requested profile recorded
  verbatim in run config and echoed); grid_position validated against the era's grid
  size, then pinned via the new reset option.
- `frames.py` — `build_lap_frame(env, prev_snapshot)`. RaceState is lap-quantised and
  holds none of the CarState fields directly, so each is an honest derivation:
  - **s_track** is synthesised for display: each car's fractional lap progress when
    the leader crosses the line, from time gaps over the nominal lap time — a
    stylised mapping, constants in serving.yaml, pinned in [0, 1).
  - **in_pit and rival pit events** from diffing pit_count against the previous
    lap's snapshot — hence the prev_snapshot argument.
  - **gap_ahead_s** recomputed from cumulative_time_s + positions(); a test pins the
    ego's value against the env's own info["gap_ahead_s"].
  - **SC/VSC/red/weather RaceEvents** from track_status/weather transitions between
    snapshots.
  - **CarState.id** is the stable car index (ego is 0); liveries are F11's concern.
  Runs once per lap in the worker — never reachable from step(), nothing
  pandas-shaped.
- `loader.py` — resolve MODEL_VERSION ("dev-latest"/unset -> models/headline; an
  explicit version -> matching manifest under MODELS_DIR), load_triplet
  (training=False by construction), load surrogates **plus background.npz** (TreeSHAP
  needs the interventional background) and fidelity.json; enforce the E-15 version
  guard; process-level cache so the worker loads once.
- `cache.py` — the E-15 key builder (divergence 1) + TTL; env_hash always from the
  manifest fingerprint.

### Worker (worker/)
- `jobs.py` — run_simulation(run_id): mark running; build env; roll the whole race
  with the deterministic Sb3Policy head; per lap build LapFrame + DecisionCard
  (TreeSHAP top-k every lap; flip probes on pit decisions per 5.8.2); persist frames
  + cards + summary in one transaction; write the cache key; publish completion on
  events:{run_id}; status -> complete, or failed with the error recorded.
- `settings.py` — queue/connection plumbing; sets OMP_NUM_THREADS=1 before
  torch/xgboost import (the arm64 dual-OpenMP segfault, F09's guard).

### Env & schema changes
- `senna/env/race_env.py` — reset(options={"grid_position": n}) pins the ego's slot,
  rest permuted over the remainder on the same stream. Additive; twin path untouched.
- `senna/data/schema.py` + one alembic migration — SimulationRun gains **nullable**
  status/seed/circuit/purpose/summary JSONB/started_at/finished_at (F09's persist
  path and its config-JSONB discriminator untouched; serving endpoints filter
  status IS NOT NULL so eval-card rows 404 rather than 500); new LapFrameRow table
  (run_id FK, lap, frame JSONB, unique(run_id, lap)) — the E-16 source of truth.

### Deploy skeleton
- `Dockerfile.api` — additionally COPY migrations/, alembic.ini, worker/, scripts/,
  models/headline, models/explain/<version> (boosters, background.npz,
  background_composition.json, fidelity.json, manifest), data/circuits; entrypoint
  migrates then serves.
- `.dockerignore` (new) — .venv, wandb, data/cache, models/* except the baked dirs.
- `scripts/start_api.sh` / `scripts/start_worker.sh` — shared by compose and Railway;
  **both** run alembic upgrade head (idempotent), so a worker booting first on a
  fresh deploy cannot race the api's first migration.
- `docker-compose.yml` — worker service (same image, start_worker command);
  VITE_WS_BASE=ws://localhost:8000/ws on the frontend service (divergence 6).
- `docs/deploy.md` — the Railway runbook: two services from Dockerfile.api with
  different start commands, Postgres/Redis plugins, env vars per 5.11.2, healthcheck
  path, the redeploy drill, and the weather_profile mapping limitation (Q2). During
  /ship the deploy is `railway up` from the feature branch — no GitHub auto-deploy
  wiring, so the never-merge-during-/ship rule holds; auto-deploy from main can be
  wired after /land. Saad drives the Railway account and plugins (approved Q4);
  local compose is the demo fallback.
- `.env.example` — REDIS_URL, MODEL_VERSION, MODELS_DIR notes.
- `Makefile` — gains api, worker, up targets (new, not stubs).
- `.github/workflows/ci.yml` — redis:7-alpine service + REDIS_URL; frontend job gains
  the F-27 build check: production build, then grep for the hostname-shaped patterns
  actually used in compose — "api:8000", "redis://", "postgres://", "@postgres".
- `.gitignore` — precise negation patterns admitting exactly the frozen artifacts
  (approved Q1): models/headline/ (~1.9 MB), models/explain/
  senna-ppo-6b6edb78d84e-C-00835584/ minus holdout.npz/crosscheck.npz (~11 MB), the
  3 built ribbon GLBs + meta.json. The training and ablation run dirs stay ignored.

## Constants & configs (all in configs/serving.yaml)

| Name | Value | Origin |
|---|---|---|
| cache.ttl_days | 7 | sourced — E-15 / 5.9.3 backstop |
| cache.key_prefix | "sim" | sourced — 5.9.3 key scheme |
| channels.events_prefix | "events" | sourced — 5.9.3 |
| queue.name | "default" | sourced — 5.9.3 |
| queue.job_timeout_s | 600 | operational — RQ's silent 180 s default is the inline-constant defect; order-of-magnitude margin over a TreeSHAP-per-lap race |
| queue.result_ttl_s | 86400 | operational — results live in Postgres; RQ's copy is bookkeeping only |
| playback.speeds | [1, 5, 10, 30] | sourced — 5.9.3 client:speed set |
| playback.one_x_is | simulated lap seconds (1 wall s per sim s) | stylised — the E-16 clock definition, stated on screen in F13 |
| frames.s_track mapping | nominal lap time from scenario | stylised — display-only fractional-progress mapping |
| health.max_response_ms | 250 | operational — the F10 spec's "stated threshold" |
| frames.page_size | 100 | operational — /frames pagination default |
| cors.allow_origins | ["http://localhost:5173"] + CORS_ORIGIN env extension | sourced — 5.11.1 "CORS allowlist = frontend origin"; prod origin is deploy-time |
| live_cards.flip_on_pit_only | true | sourced — 5.8.2 flip probes "for headline decisions" |
| ws.status_poll_s | 0.5 | operational — wait cadence for a still-running job |

## Tests first

tests/api/ (TestClient + bare asyncio.run; DATABASE_URL/REDIS_URL skip guards per the
tests/explain/test_persist.py pattern; a conftest.py setting OMP_NUM_THREADS=1):
- test_schemas — SimulationCreate bounds (grid 1..22 for 2026, era/weather/rival
  literals, rival_band default "test"); explicit model_version matching a baked
  manifest accepted, unknown 4xx; None resolves to the served version.
- test_simulation_flow — POST /simulations -> rq SimpleWorker drains -> status
  complete -> /frames paginated (count == race_laps, from_lap/to_lap honoured) ->
  /decisions non-empty -> seed echoed. The F10 integration test.
- test_ws_stream — full ordered stream at 30x ending sim:complete; a sim:event
  emitted on a seed whose race contains SC or pit; client:seek(k) replays from k;
  client:pause halts emission; disconnect mid-stream + reconnect -> zero frames lost
  (E-16).
- test_cache — same body+seed -> same run_id; MODEL_VERSION bump -> miss (E-15);
  different circuit, same seed -> different key; TTL set to the yaml value.
- test_counterfactuals — body validation ({year, round, driver}); JobAccepted; the
  completed run's config records era "2024" and era_matched_model "pending-F14";
  frames retrievable via the simulations endpoints (20 cars).
- test_health_latency — /health under health.max_response_ms both while a WS stream
  runs and while a job is mid-flight (SimpleWorker on a thread) — the spec's
  "running simulation" wording covered directly, not by proxy.
- test_model_version_header — X-Model-Version present on every routed response.
- test_registry — /agents lists the baked model with eval points (promotion.json),
  fidelity (fidelity.json), config hash (manifest).
- test_circuits — count == circuits.yaml entries; coverage flags computed; unknown
  id 404; gltf_url only when the GLB exists and **relative** (no scheme, no host);
  detail embeds corners/braking_zones/xmode_sections + h_max_mj for a built circuit.
- test_tyres_energy — /tyres mirrors physics_params (a, b, low_confidence surfaced);
  /energy series length == laps, SOC within [0, 4], h_max from circuits.yaml.
- test_races — RaceDetail from seeded ingest fixtures; 404 on unknown year/round.

tests/serve/ (same conftest guard):
- test_frames — a stepped env yields n_cars CarState (22 for 2026), positions a
  permutation of 1..n, legal compounds, ego SOC in [0, 4], s_track in [0, 1); ego
  gap_ahead_s matches the env's info value; a pit lap flips in_pit via the pit_count
  diff. **Property test** (hypothesis): random legal action sequences -> those
  invariants hold on every lap's frame.
- test_mapping — SimulationCreate -> env kwargs; unknown circuit -> clean 404;
  era-2024 grid bound enforced (divergence 4); weather profile recorded verbatim.
- test_loader — dev-latest resolves to models/headline; explicit version resolves;
  mismatched surrogate refuses (E-15); background set loaded; **the F-23 serving
  cross-check**: loader's deterministic action == load_triplet's on a fixed
  obs+mask, on the real committed artifact.
- test_cache_key — key format (divergence 1), stable digest ordering, env_hash taken
  from the manifest.
- test_playback_clock — injected fake timer: inter-frame delay == lap_time/speed;
  mid-stream speed change; pause/resume.

tests/env/:
- test_reset_grid — options={"grid_position": 7} pins ego to 7, rest a permutation of
  the remainder; same seed+pin reproducible; twin path unaffected.

CI, not pytest: the F-27 build check (patterns above).

## Edge cases handled
- **E-15** — scenario-complete cache keys incl. model_version + env_config_hash; TTL
  7 d backstop; the surrogate-version guard (never explain a ghost); /agents and the
  X-Model-Version header surface the served version.
- **E-16** — worker persists everything immediately; the WS is a read-only playback
  clock over lap_frames; pause/scrub/reconnect tested as reads; producer speed never
  couples to playback speed.
- **E-02** — /energy ships h_max_mj from configs/circuits.yaml per event.
- **E-13** — /circuits computes counts and coverage from ingested/built artifacts.

## Acceptance checklist (Done means)
- [ ] POST /simulations -> worker -> frames -> WS round-trip streams locally (compose)
- [ ] The same round-trip streams on Railway (railway up from the feature branch);
      the public /api/v1/health URL is live — Saad drives the account/plugins step;
      local compose is the demo fallback if Railway slips
- [ ] The frozen triplet loads with training=False and matches training-eval actions
      on a fixed state (F-23 cross-check green)
- [ ] Kill + redeploy the Railway services: nothing lost — no mounted models, no
      local state; a changed MODEL_VERSION cold-starts its own cache namespace
- [ ] Test battery above green; spec-auditor + code-reviewer findings addressed

## Ship-process notes (Saad, 22 Jul 2026)
- `rm -rf .ruff_cache && make lint` before the final gate — the warm-cache I001 trap
  bites tests-first features (F08 precedent).
- After /land, check the Actions page deliberately: CI gains a Redis service in this
  feature, so the first main run exercises new infrastructure.

## Out of scope
- The six views (F11–F13). Frontend is touched only by compose/CI env plumbing.
- Evaluation content (F14): M1–M11, the era-matched Stage-C 2024 fine-tune. The
  /counterfactuals endpoint ships real plumbing but runs the frozen 2026 model on
  era-2024 physics, with the pending-F14 caveat recorded in the run config and
  echoed in the SimulationResult summary so no consumer can miss it (approved Q3).
- Writing simulated per-driver laps rows (the 5.3.5 columns) — F14's concern.
- Auth, rate limiting, multi-model concurrent serving, W&B anywhere in serving.

## Decisions (Saad, 22 Jul 2026)
1. Frozen artifacts committed via precise .gitignore negations — headline triplet,
   the one surrogate dir, the 3 GLBs; never the training/ablation run dirs.
2. weather_profile mapping approved (dry->dry, mixed/wet_risk->markov, recorded
   verbatim, limitation documented).
3. Counterfactuals: real plumbing with a loud pending-F14 caveat.
4. Railway handled by Saad, guided at the end of /ship; compose is the demo fallback.
5. Fourth provenance origin **operational** added to the interpretability contract
   (configs/README.md, CLAUDE.md, spec-auditor) rather than widening stylised.
