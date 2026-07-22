# F10 — Backend serving: the API, the worker and the playback clock

## What we built and why

Until now the race only existed inside a Python process you launched by hand. F10
gives it an address. You POST a race request — circuit, grid slot, weather, seed — and
get back a ticket. A worker process picks the ticket up, runs the whole race with the
frozen F08 headline model, builds a frame and a decision card for every lap using
F09's own helpers, and writes it all to Postgres. Then any number of browsers can open
a WebSocket and watch the race play back lap by lap, pause it, scrub it, speed it up.

The load-bearing sentence in that paragraph is "writes it all to Postgres, then
watch". The simulation and the viewing are two different jobs on two different clocks.
The worker finishes a 57-lap race in seconds; the viewer watches it for minutes at 1x.
Divorcing them (E-16) is what makes reconnect free — a dropped socket lost nothing,
because the socket never owned anything.

The same layer answers everything else the frontend will need: the circuit library
with its ribbons, the tyre and energy curves, the model registry with its fidelity
badge, and a health check that must answer in 250 ms even while a race is running.
And the whole thing deploys — one Docker image, two start commands, pushed to Railway
now rather than in November, because the plan's stated purpose was to kill deployment
risk early. Three of the deepest lessons in this feature came from exactly that: bugs
that no unit test saw and a fresh `docker compose up` found in minutes.

## New ideas in this feature

**FastAPI and who owns the event loop (F-26).** FastAPI is a web framework that runs
every request handler as a coroutine on one asyncio event loop — the same async/await
machinery from F01, now serving HTTP. The new consequence: that one loop also runs
every open WebSocket, so any handler that computes for 30 seconds freezes every
connected stream and the health check with them. Mental model: one chef, many orders;
`await` is the chef putting a pan down to start another order, and a simulation in a
handler is the chef leaving to drive a race. Smallest example: even reading
`manifest.json` in the POST handler goes through `run_in_threadpool`, because file IO
blocks and the loop must never wait on it. The viva answer: **the API process never
simulates because every handler and every WebSocket share one event loop, and a race
in a handler would stall every connected client (F-26). Simulation lives in a separate
worker process; the handler only validates, records and enqueues.**

**Pydantic response models as a contract (5.9.2).** Pydantic classes declare a shape —
fields, types, bounds — and validate anything crossing the boundary against it, in
both directions. `api/schemas.py` is 5.9.2 written down verbatim, and api/CLAUDE.md's
rule is that you change the spec before you change a shape, because the frontend will
be built against exactly these fields. The detail worth stealing is on
`SimulationCreate`:

```python
    # forbid, or a typo like "wether_profile" silently becomes a dry race
    model_config = ConfigDict(extra="forbid")
```

Pydantic's default is to ignore unknown fields. With the default, a client typo drops
the field, the schema default fills in `"dry"`, and someone spends an afternoon
wondering why their wet race isn't wet. `extra="forbid"` turns the typo into a 422
with the field named.

**RQ job queues, and one image with two commands (5.9.3, F-26).** RQ ("Redis Queue")
is about as small as a job queue gets: `enqueue("worker.jobs.run_simulation", run_id)`
writes a function path and its arguments into a Redis list, and a worker process —
anywhere, any machine — pops and calls it. The API and the worker are two containers
built from the *same* `Dockerfile.api` with different start commands (plan divergence
7), so they can never disagree about code, configs or baked models; the image is the
unit of deployment, the command is the role. The worker is where torch, the env and
TreeSHAP live; the API process never imports torch at all, which
`test_read_manifest_answers_without_importing_torch` pins.

**Redis wearing three hats.** One Redis instance is simultaneously the job queue (RQ's
lists), the E-15 result cache (`sim:...` keys with a 7-day TTL), and a pub/sub
notice board (`events:{run_id}`, where the worker publishes "complete" so a WebSocket
that connected early wakes instantly instead of polling hard). Three roles, one
`REDIS_URL`, every prefix and TTL named in `configs/serving.yaml`. The distinction to
hold on to: the queue and pub/sub are *coordination* — losing Redis loses nothing but
time — while Postgres holds every result, which is why `result_ttl_s` can be a mere
day of bookkeeping (its provenance comment says exactly that).

**Versioned cache keys (E-15).** Same request, same model, same physics: the answer is
deterministic, so cache it. The key is
`sim:{model_version}:{env_hash}:{scenario_digest}:{seed}`, and every segment earns its
place: model version and env config hash come from the served triplet's manifest —
never recomputed at serve time — so a retrain or a physics change cold-starts a fresh
namespace and no stale race can outlive the model that produced it. The scenario
digest is plan divergence 1: 5.9.3's key as written has no scenario term, so Bahrain
and Monaco on seed 42 would have collided into one cached race. The viva answer:
**every cache key embeds the model version and env config hash read from the served
manifest, so retiring a model retires its cache by construction rather than by a
flush someone must remember (E-15). The scenario digest was added because the spec's
key as written collides two circuits on the same seed — flagged as a divergence, not
silently fixed.**

**WebSockets versus REST, and the playback clock (E-16).** REST is request-response:
the client asks, the server answers, the connection is done. A WebSocket stays open in
both directions, which is what a live race feed needs. The idea that makes SENNA's
socket boring — in the best sense — is that it is not live at all: the worker persisted
the whole race before playback, and the socket is a *view* that reads stored rows on a
timer. 1x means one wall second per simulated second, so the inter-frame delay is the
circuit's fitted lap time divided by the client's speed. The viva answer: **the worker
runs the race to completion into Postgres immediately, and the WebSocket is a
read-only playback clock over those rows, so pause, scrub and reconnect are all reads
and producer speed never couples to playback speed (E-16). A dropped socket loses
nothing because the socket never held anything.**

**Baked artifacts on an ephemeral filesystem (F-26).** Railway containers keep no disk
between deploys, so nothing may be mounted or downloaded at boot: the frozen triplet,
the surrogate set and the three built ribbons are `COPY`'d into the image (committed
via precise `.gitignore` negations — decision 1). A redeploy reproduces the exact
serving state from the repo, and `MODEL_VERSION` can only select among what the image
bakes; an unknown version fails at startup instead of silently falling back.

**The fourth provenance origin: operational.** `configs/serving.yaml` needed numbers
that are neither sourced, fitted nor stylised — a job timeout, a page size, a poll
cadence. Rather than stretch "stylised" (which the UI labels as a visual choice),
Saad approved a fourth origin: an explicit engineering default whose comment states
the sizing rationale. `job_timeout_s: 600` is the type specimen — RQ's own default is
a *silent* 180 s, which is precisely the inline-constant defect the contract exists
to kill.

Already in the ledger and only name-checked here: async/await and asyncpg (F01),
alembic migrations (F01), compose services and healthchecks (F00), the F-27 browser
boundary (F00), delete-and-reload idempotency (F01), the F-23 checkpoint triplet
(F07), and F09's whole card pipeline, which this feature reuses wholesale.

## The code, guided

Reading order follows one request: contract, POST, key, loader, worker, frames,
socket — then the two boot-time war stories.

### api/schemas.py and api/main.py — the contract and the shell

`schemas.py` is 5.9.2 transcribed: `SimulationCreate` through `DegradationCurve`, with
the comments carrying the spec cross-references. `main.py` is the app factory:
lifespan owns the async engine, the redis client and the RQ queue handle; CORS comes
from serving.yaml plus a deploy-time `CORS_ORIGIN`; middleware stamps
`X-Model-Version` on every response including errors ("a version-less 404 is still an
answer someone will screenshot"); the ribbon directory mounts at
`/api/v1/assets/circuits` and `gltf_url` is emitted relative so no server-side
hostname can leak past F-27. One line matters for tests:
`app.state.playback_sleep = asyncio.sleep` — the WS clock is injectable, so the test
suite replays a 57-lap race in milliseconds and no test ever sleeps (F01's injectable
clock, again).

### api/routes/simulations.py — the POST flow

`enqueue_run` is the core of the serving API and worth every line.

```python
    manifest = await run_in_threadpool(_validated_manifest, req)
    if req.seed is None:
        # drawn before the key is built, so the echoed seed is the one that runs
        bound = serving_config()["seeds"]["draw_bound"]
        req = req.model_copy(update={"seed": secrets.randbelow(bound)})
```

Line one: manifest and scenario reads are file IO, so they leave the event loop
(F-26). Then the seed. 5.9.2 says a missing seed is drawn server-side and echoed
back, and the draw happens *here*, before the cache key exists, because the key's last
segment is the seed — a `None` seed would give every anonymous request the same key,
and `sim_cache_key` raises if you try (the guard is in `cache.py`). `draw_bound` is
2³¹ because the seed lands in a signed-int32 column; even that number lives in yaml
with its reason. `model_copy` because Pydantic models are treated as immutable
requests, not scratch space.

```python
    cached = await redis.get(key)
    if cached is not None:
        ...
        if hit is not None and hit.status == "complete":
            return JobAccepted(run_id=hit.id)
        if hit is not None and not run_is_stale(hit, queue_cfg=queue_cfg):
            return JobAccepted(run_id=hit.id)  # queued/running and fresh: dedupe in flight
        # the run behind the key is dead — failed, deleted, or a work horse that
        # never reported. The key must not answer for it for 7 days (E-15).
        await redis.delete(key)
```

A cache hit is not trusted, it is *checked*: the row behind the key must exist and be
either complete or honestly in flight. `run_is_stale` is the recovery rule — a
queued/running row older than two job budgets (`stale_after_timeouts ×
job_timeout_s`, both in yaml) means the worker died before it could report: OOM, a
platform SIGKILL, a redeploy mid-job. Without this branch, that key answers with a
corpse for seven days and the WS waits on a race that will never finish. This was a
review-battery catch, not first-draft code.

```python
    prior = await redis.set(key, run_id, nx=True, ex=ttl_seconds(), get=True)
    if prior is not None:
        # an identical request won the NX race between our GET and SET: keep the
        # winner, drop our orphan row, enqueue nothing
        async with engine.begin() as conn:
            await conn.execute(delete(SimulationRun).where(SimulationRun.id == run_id))
        return JobAccepted(run_id=int(prior))
```

Two identical requests can both pass the `GET` above before either writes. `NX` makes
the `SET` an atomic claim — succeed only if the key is absent — and `GET=True` returns
the incumbent when the claim fails, in one round trip. The loser deletes its own
queued row and returns the winner's id, so double-clicking "simulate" costs one row
insert and zero races. Only after winning the claim does the job get enqueued, with
the timeout and TTLs from yaml.

The read endpoints below are scaffolding with one deliberate clause: every serving
read filters `status IS NOT NULL`, because F09's 14,460 eval-card rows share these
tables under their own purpose and have no status — they should 404 here, not 500.

### senna/serve/cache.py — the key, line by line

```python
_SCENARIO_FIELDS = ("circuit_id", "era", "grid_position", "weather_profile", "rival_band")

def sim_cache_key(model_version: str, env_hash: str, req) -> str:
    if req.seed is None:
        raise ValueError("seed must be drawn before the cache key is built — ...")
    scenario = {name: getattr(req, name) for name in _SCENARIO_FIELDS}
    digest = hashlib.sha256(
        json.dumps(scenario, sort_keys=True).encode()
    ).hexdigest()[:16]
    prefix = _serving()["cache"]["key_prefix"]
    return f"{prefix}:{model_version}:{env_hash}:{digest}:{req.seed}"
```

`_SCENARIO_FIELDS` is every request field that changes the race, and nothing else:
seed is excluded because it gets its own segment (so you can eyeball two keys and see
"same scenario, different seed"), and model_version is excluded because the *resolved*
version from the manifest forms the second segment — the request's own field might be
`None`. The raise restates the POST-flow invariant at the place it would be violated.
`sort_keys=True` makes the digest independent of field order, pinned by
`test_the_digest_is_stable_under_field_reordering`; 16 hex chars is plenty against
accidental collision among a handful of scenarios. `test_every_scenario_field_moves_the_digest`
walks the tuple and proves each field actually moves the key — the regression test for
divergence 1 itself.

### senna/serve/loader.py — the frozen artifacts, loaded once

`resolve_version` implements 5.11.2's alias rules: `None` and `"dev-latest"` mean the
promoted headline; an explicit version must equal what this image bakes or
`UnknownModelVersionError` (the POST's 422, the startup's loud failure). `read_manifest`
is the API-process path — /health and /agents answer from the manifest alone.

`load_serving_model` is the worker-process path, and its structure is the point:

```python
@lru_cache(maxsize=4)
def _load(root: str, triplet: str) -> ServingModel:
    # heavy imports stay inside: the API imports this module for read_manifest and
    # must never pull torch into its process
    from stable_baselines3.common.vec_env import DummyVecEnv
    ...
    model, venv = load_triplet(triplet_dir, DummyVecEnv([lambda: F1RaceEnv(circuit, "2026")]))

    boosters, surrogate_version = load_surrogates(surrogate_dir)
    if surrogate_version != model_version:
        raise VersionMismatchError(...)
    background = np.load(surrogate_dir / "background.npz")["states"]
```

The `lru_cache` is the process-level "load once" (F-26) — and the public wrapper
resolves the version *before* caching so `None`, `"dev-latest"` and the explicit baked
name all share one entry. `load_triplet` is F07's loader, which sets `training=False`
on the VecNormalize statistics by construction: serving must never update the
normalisation the model was frozen with. The surrogate guard is F09's E-15 rule
applied at load time — never explain a ghost — and `background.npz` rides along
because TreeSHAP's attributions are meaningless without the documented background
(F09). `test_the_served_action_matches_the_training_eval_loader` is the F-23
acceptance cross-check: on a fixed obs and mask, this loader's deterministic action
equals the training-side loader's, on the real committed artifact.

### worker/jobs.py — the job, and the linter war story

The file opens with a scar:

```python
import os

# arm64 landmine: torch and xgboost each bundle libomp, and two OpenMP runtimes in
# one process segfault — set before either loads. A bare statement, not an import
# whose position a lint autofix can shuffle below the torch imports (it did).
os.environ.setdefault("OMP_NUM_THREADS", "1")

import asyncio
```

War story three, in full. The guard originally lived in `worker/settings.py`, imported
first so it ran before torch. Then `ruff --fix` sorted the imports — `worker` sorts
after `senna`, whose modules import torch — and the guard now ran *after* the thing it
guards against, recreating the exact arm64 segfault F09 documented. The fix is a bare
statement between two import blocks, which no import sorter will ever move. The
lesson generalises: a linter's autofix edits meaning, not just style, and "imports are
reorderable" is only true when imports have no side effects — which an environment
guard, by definition, has.

`run_simulation` itself is a thin sync shell (RQ calls plain functions) around an
async `_run`, with the failure path mirrored: on any exception the run row is marked
failed with the error recorded, the cache key is *deleted* so a retry re-runs instead
of hitting a corpse (E-15), and `events:{run_id}` gets "failed" so a waiting socket
learns immediately. The happy path's persistence is one transaction:

```python
        async with engine.begin() as conn:
            # rewrite, never append: a retried job lands on the same rows
            await conn.execute(delete(LapFrameRow).where(LapFrameRow.run_id == run_id))
            await conn.execute(delete(AgentDecision).where(AgentDecision.run_id == run_id))
            await conn.execute(insert(LapFrameRow), [...])
            if cards:
                await conn.execute(insert(AgentDecision), [...])
            await conn.execute(update(SimulationRun)...values(status="complete", ...))
```

F01's delete-and-reload idempotency, verbatim: a job RQ retried after a half-write
lands on clean rows, and a reader can never observe frames without their status —
either the transaction committed whole or it never happened. The status flip to
"complete" rides in the same commit as the data, so "complete" *means* readable.

`_cards_for` is why F09 was worth building carefully: the live cards are the same
`build_card`, `top_drivers`, `flip_lines_for`, `pit_mask_fn` and `DecisionLogger` that
carded the eval races — one card pipeline, two callers, zero drift between what the
dashboard shows and what the dissertation evaluated. Two serving-specific choices:
TreeSHAP runs on the whole race's states in one batched call per head, and flip
probes run only on pit laps (`flip_on_pit_only`, sourced to 5.8.2's "headline
decisions" — a stay-out lap gets drivers but no sweep, because sweeping 32 features
on 57 laps would buy latency with no headline to explain).

### senna/serve/frames.py — honest pixels from a lap-quantised state

The env advances a lap at a time and holds no mid-lap position, but the dashboard
needs cars on a ribbon. Every `CarState` field is therefore a stated derivation, and
this function is the one place serving code touches `env._state` — once per lap in
the worker, never from `step()`.

```python
    rank = state.positions()
    by_rank = np.argsort(rank, kind="stable")

    gaps = np.empty(n)
    gaps[by_rank[0]] = np.nan  # the leader has nobody ahead
    for place in range(1, n):
        car, ahead = by_rank[place], by_rank[place - 1]
        gaps[car] = state.cumulative_time_s[car] - state.cumulative_time_s[ahead]
```

`by_rank` turns "rank of each car" into "car at each rank" so the loop can walk the
field in running order. Each car's gap is its cumulative time minus the car one place
ahead — the *same* arithmetic as the env's own `_gaps_ahead`, deliberately, and
`test_lap_frames` pins the ego's displayed gap bit-identical to `info["gap_ahead_s"]`
so there is one gap definition in the system, not a second one free to drift.

```python
    leader_time = state.cumulative_time_s[by_rank[0]]
    to_leader = state.cumulative_time_s - leader_time
    s_track = (1.0 - to_leader / env.scenario.t0_s) % 1.0
    parked = prev.s_track if prev is not None else np.zeros(n)
    s_track = np.where(state.retired, parked, s_track)
```

`s_track` is the display-only lap fraction, and its formula is honest about being
synthetic: when the leader crosses the line, a car `to_leader` seconds behind is
placed that fraction of a nominal lap (`t0_s`, the circuit's fitted lap time) short of
the line. `1.0 −` because behind means less progress; `% 1.0` because a car more than
a lap down should wrap to somewhere on the ribbon, not go negative. The `retired` line
exists because a dead car's cumulative clock froze — leave the formula running and the
wreck orbits the track as the leader's time grows, so a retired car keeps the fraction
it died with. All of it is flagged stylised in serving.yaml (F04's rule: the UI never
shows decoration as data), and F11 will label the interpolation illustrative.

```python
    stopped = (state.pit_count > (prev.pit_count if prev is not None else 0))
```

The env has no `in_pit` flag; what it has is a monotone per-car stop counter. Diffing
it against the previous lap's snapshot yields "pitted this lap" for all 22 cars in one
vectorised comparison — which is why the builder takes and returns a `LapSnapshot`
(pit counts, track status, weather, parked fractions). The same snapshot-diff pattern
produces the `RaceEvent` list in `_events`: SC/VSC on a status *transition* rather
than every yellow lap, weather on a change with the old and new state in the detail,
one pit event per stopped car. In the car dict, `gap_ahead_s` is `None` for the leader
and for retired cars — the frozen clock would otherwise print a nonsense, even
negative, gap.

### api/ws.py — the two-future dance

The socket's problem: while a frame's delay ticks down (a full lap of wall clock at
1x), the client may send pause, seek or a speed change, and it must take effect *now*.
Reading and ticking are therefore two futures raced against each other.

```python
        while index < len(frames):
            if paused:
                # the clock stops dead: no frames, and playback_sleep is not called
                # again until a client message resumes or seeks
                await asyncio.wait({receive})
                handle(client_message(receive))
                receive = asyncio.ensure_future(ws.receive_json())
                continue
```

Paused is the simple case: the only thing worth waiting on is the client. No timer
exists while paused, which is what `test_pause_halts_the_playback_clock` asserts by
counting calls to the injected sleep. After every consumed message, a *new* receive
future is created — a future is one-shot, and reusing a done one returns the same
message forever.

```python
            frame = frames[index]
            await ws.send_json({"type": "sim:lap", "frame": frame,
                                "card": cards.get(frame["lap"])})
            for event in frame["events"]:
                await ws.send_json({"type": "sim:event", **event})
            index += 1

            tick = asyncio.ensure_future(
                ws.app.state.playback_sleep(frame_delay_s(nominal_lap_s, speed))
            )
            done, _ = await asyncio.wait({receive, tick},
                                         return_when=asyncio.FIRST_COMPLETED)
```

Send the frame with its card riding along (divergence 5: cards travel in `sim:lap`;
there is no `agent:decision` event), then the lap's events as `sim:event` messages.
Then start the timer and wait for *either* future. `FIRST_COMPLETED` is the whole
trick: the coroutine sleeps, but wakes for whichever happens first.

```python
            interrupted = False
            if receive in done:
                interrupted = handle(client_message(receive))
                receive = asyncio.ensure_future(ws.receive_json())
            if interrupted:
                # at 1x a tick is a whole lap of wall clock — a seek or speed
                # change that waited it out would make scrubbing unusable (E-16)
                tick.cancel()
            elif not tick.done():
                await tick
```

If the client spoke, `handle` applies the message and reports whether the current
tick is now wrong — a seek moved `index`, a speed change moved the tempo. If so the
tick is cancelled outright; the first draft awaited it anyway, and the review battery
flagged that a scrub at 1x would wait out a full lap of wall clock before taking
effect. If the
message changed nothing (or was malformed — ignored, never a server traceback), the
remaining tick is awaited so the frame rate holds. Seek itself is one line inside
`handle`: clamp `lap − 1` into range and set `index`, because replaying from lap k is
just *reading the list from a different offset*. That sentence is E-16 doing its job.

A socket that arrives before the run finishes goes through `_await_completion`:
subscribe to `events:{run_id}`, re-check the row, and block on `pubsub.get_message`
with `status_poll_s` as only the re-check pace — the publish wakes it instantly. The
wait is bounded by the same `run_is_stale` rule as the POST, so a dead worker cannot
hold a socket open for days. And on `WebSocketDisconnect` the handler just returns:
nothing to recover, the next socket replays from the same store
(`test_reconnect_after_a_drop_replays_with_zero_frames_lost`).

### migrations/env.py — war story one: who owns the transaction

Both entrypoint scripts run `alembic upgrade head` before their real work, because on
a fresh deploy either service may boot first and a worker job landing on a missing
`lap_frames` table would fail for no honest reason. The compose smoke then found the
obvious consequence: on a fresh database the api and worker boot *together*, both read
"no revision", and both issue the same ALTERs — one wins, one crashes.

```python
def _run_sync_migrations(connection) -> None:
    from sqlalchemy import text

    # session-scoped: released when this connection closes, even on a crash. The
    # commit matters — it ends the transaction the lock select implicitly opened,
    # or alembic treats that transaction as caller-owned and never commits its own
    # work (the upgrade then rolls back silently on close, exit code 0)
    connection.execute(text("select pg_advisory_lock(:key)"), {"key": _MIGRATION_LOCK})
    connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
```

A Postgres advisory lock is an application-defined mutex the database holds for you:
any migrator that arrives second blocks on this line until the first finishes, and a
session-scoped lock releases itself if the holder crashes. Any constant identifies
the lock (this one spells SENNA in hex); it only has to be the same in every migrator.

The `commit()` is the deeper half of the story. Executing the lock SELECT implicitly
opened a transaction on the connection — and alembic, handed a connection with a
transaction already in progress, politely assumes the *caller* owns it and will
commit. The caller never did. The upgrade ran, rolled back on close, and exited 0:
schema unchanged, no error anywhere, discovered only because the next boot tried to
migrate again. The commit ends the incidental transaction and hands ownership back,
so alembic begins and commits its own. Lesson worth keeping: "who owns this
transaction" is a real interface question between libraries, and getting it wrong
here failed *silently in the successful direction*.

### scripts/start_worker.sh — war story two: test doubles hide topology

```sh
# SimpleWorker on purpose: the default worker forks a work horse per job, which
# throws away the process-level model/explainer caches and re-imports torch every
# race. One process, loaded once (F-26); the platform restarts it if a job kills it.
exec rq worker -w rq.SimpleWorker --url "$REDIS_URL" "$QUEUE"
```

RQ's default worker forks a fresh child process per job — good isolation, and it
means every process-level cache in this feature (`lru_cache` in the loader, the
explainer dict in jobs.py) was being built, used once, and discarded with the child.
Every race paid the full torch import and triplet load. No test saw it, because the
test suite drains jobs with `SimpleWorker` *in-process* — the standard RQ testing
pattern, and precisely the topology production didn't have. The compose smoke's
timings gave it away. `SimpleWorker` in production runs jobs in the worker's own
process: caches survive, and crash isolation is delegated to the platform's restart
policy, which compose and Railway both provide. The lesson: a test double that
simplifies process topology can hide bugs that only exist *because* of process
topology; the honest check is the real `docker compose up`, which is why the
acceptance checklist demands the round trip on compose and Railway, not just pytest.

### The deploy skeleton

Block-level, because it is wiring: `Dockerfile.api` copies code, configs, migrations
and the baked artifacts (with a comment carrying F-26's why), installs `libgomp1`
because slim images ship without xgboost's OpenMP runtime, and defaults to the api
start script; compose gains the worker service running the same image with the worker
command, plus `VITE_WS_BASE=ws://localhost:8000/ws` (divergence 6 — the master spec's
scheme, browser-reachable per F-27); CI gains a redis service and the F-27 build
check, which greps the production frontend bundle for the hostname shapes compose
actually uses server-side (`api:8000`, `redis://`, `postgres://`, `@postgres`) and
fails if any escaped into the browser's world. `docs/deploy.md` is the Railway
runbook, including the redeploy drill that proves nothing lives outside the image and
the plugins.

## How it connects

```
 browser (F11+)  ── VITE_API_BASE / VITE_WS_BASE only (F-27) ──┐
                                                               ▼
 ┌─ api: FastAPI, one event loop (F-26) ────────────────────────────────┐
 │  POST /simulations: validate → draw seed → E-15 key → NX claim →     │
 │    enqueue          GET /simulations /frames /decisions /circuits    │
 │  ws.py: playback clock over stored frames — pause/seek/speed (E-16)  │
 └────┬──────────────────────────┬──────────────────────────────────────┘
      │ Redis: queue + cache     │ Postgres: simulation_runs,
      │        + events:{run_id} │ lap_frames, agent_decisions (5.3.5)
      ▼                          ▲
 ┌─ worker: same image, SimpleWorker, loads once (F-26) ────────────────┐
 │  frozen triplet (F-23, training=False) + surrogates (E-15 guard)     │
 │  roll race → frames.py + F09's card pipeline → one transaction       │
 │  set cache key · publish complete/failed                             │
 └──────────────────────────────────────────────────────────────────────┘
```

F08 supplied the model, F09 the explanation machinery; F10 puts both behind HTTP.
F11–F13 consume every endpoint drawn here, and F14's counterfactual evaluation will
ride the same POST flow with its pending-F14 caveat already recorded in run configs
and summaries.

## Try it yourself

All commands from the repo root.

1. **Run the serving suite.** `docker compose up -d postgres redis`, then
   `DATABASE_URL=postgresql+asyncpg://senna:senna@localhost:5432/senna \
   REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m pytest tests/serve tests/api -q`.
   Without the env vars most of tests/api skips — the guards are the point, read one.
   The full round trip carries the slow marker (it runs the real triplet with TreeSHAP
   every lap); add `-m slow` to include it. You'll know it worked when the fast set is
   green and you can say which fixture swaps `playback_sleep` and why no WS test
   sleeps a real lap.

2. **The compose round trip.** `docker compose up --build`, then the smoke from
   `docs/deploy.md`: POST a Bahrain race with seed 42, GET the run until complete, GET
   three frames, then `npx wscat -c ws://localhost:8000/ws/simulations/<run_id>`.
   While it streams, paste `{"type":"client:speed","speed":30}`, then
   `{"type":"client:pause"}`, then `{"type":"client:seek","lap":40}`. You'll know it
   worked when the pause stops the feed dead, the seek resumes from lap 40
   immediately (that immediacy is the cancelled tick), and POSTing the identical body
   again returns the same run_id without the worker logging a second race.

3. **Predict a config change.** In `configs/serving.yaml`, set `frames.page_size`
   from 100 to 10. Before touching anything else, write down what
   `curl ".../simulations/<run_id>/frames"` now returns for a 57-lap race, and what
   `from_lap=10&to_lap=19` returns. Check against a running stack. You'll know it
   worked when the default read comes back with laps 1–10 only — the cap clamps
   `to_lap` — and you can name which assertion in
   `test_post_drain_and_read_back_the_whole_round_trip` this would fail. Revert.

4. **Break divergence 1.** In `senna/serve/cache.py`, drop the digest segment from the
   returned key (`f"{prefix}:{model_version}:{env_hash}:{req.seed}"`), then run
   `.venv/bin/python -m pytest tests/serve/test_cache_key.py -q`. You'll know it
   worked when `test_the_key_has_the_five_agreed_segments` and
   `test_every_scenario_field_moves_the_digest` both fail — the second one is the
   5.9.3 collision itself: Bahrain and Monaco on seed 42 becoming one cached race.
   Revert.

5. **Break the stale-run recovery.** In `api/routes/simulations.py`, make
   `run_is_stale` return `False` unconditionally, then run
   `.venv/bin/python -m pytest tests/api/test_cache.py -q` (env vars as in
   exercise 1). You'll know it worked when
   `test_a_stranded_key_for_a_dead_run_is_a_miss` fails, and you can say in one
   sentence what a user would experience for the next seven days if this shipped.
   Revert.

## Check yourself

1. Why must a request handler never run a simulation — and why does even reading
   `manifest.json` in the POST handler go through `run_in_threadpool`?

2. Walk the POST flow: why is a missing seed drawn *before* the cache key is built,
   and what exact race does `redis.set(key, run_id, nx=True, get=True)` close?

3. Defend this design choice: the WebSocket replays stored rows on a playback clock
   instead of streaming frames as the simulation produces them.

4. On a fresh `docker compose up`, the api and worker raced the same ALTERs. What
   fixed it, what second bug did the fix introduce, and why did that second bug exit 0?

5. The test suite was green, yet the first real worker re-imported torch for every
   race. What was different between the two, and what is the general lesson?

---

### Answers

1. FastAPI runs every handler and every open WebSocket on one asyncio event loop; the
   loop only makes progress when the current coroutine awaits. A simulation is
   seconds of CPU with no await, so every connected stream and the health check
   freeze for its duration — that is F-26, and it is why simulation lives in the RQ
   worker process. The same logic at a smaller scale covers the manifest read: file
   IO blocks the loop too, so `run_in_threadpool` moves it onto a thread and the loop
   keeps serving. `test_health_p95_under_threshold_while_a_job_is_mid_flight` pins
   the consequence directly.

2. The key's last segment is the seed, so the seed must exist before the key can —
   with a `None` seed every anonymous request would share one key and one cached
   race, which is why `sim_cache_key` raises on it. Drawing first also makes the
   echoed seed the one that actually runs (5.9.2 reproducibility). The NX SET closes
   the window between the cache GET and the write: two identical requests can both
   see "no key", both insert a queued row, and both try to claim. NX makes the claim
   atomic, `get=True` returns the winner's run_id to the loser in the same round
   trip, and the loser deletes its orphan row and enqueues nothing.

3. Live streaming couples producer and consumer clocks: the worker finishes a race in
   seconds while a 1x viewer needs minutes, so you would need buffering either way —
   and a dropped socket would lose whatever had not been sent. E-16's answer is to
   make the store the only source of truth: the worker persists every frame and card
   immediately in one transaction, and the socket is a read-only view on a timer.
   Pause is "stop reading", seek is "read from a different offset", reconnect is "a
   fresh reader", and none of them can touch the physics. The cost — the race is not
   watchable during the seconds it takes to simulate — buys correctness under every
   disconnection and scrubbing pattern, and the early-arrival path (pub/sub wake on
   `events:{run_id}`, bounded by the staleness rule) covers the gap.

4. A Postgres advisory lock at the top of the migration runner: whoever arrives
   second blocks until the first migrator finishes, and a session-scoped lock
   releases even if its holder crashes. The introduced bug: executing the lock SELECT
   implicitly opened a transaction on the connection, and alembic, seeing an open
   transaction, treated it as caller-owned and never committed its own work — the
   upgrade ran, rolled back when the connection closed, and exited 0 because nothing
   raised. The fix is one `connection.commit()` after taking the lock, ending the
   incidental transaction so alembic begins and commits its own. The examinable
   sentence: transaction ownership is part of a library's interface, and violating it
   can fail silently in the successful direction.

5. Tests drain the queue with RQ's `SimpleWorker` running jobs in the test process,
   so process-level caches trivially survived between jobs. Production ran RQ's
   default worker, which forks a fresh work horse per job — the loader's `lru_cache`
   and the explainer cache died with every child, and every race paid the full torch
   import and triplet load. The fix runs `SimpleWorker` in production too (one
   process, loaded once, F-26), delegating crash isolation to the platform's restart
   policy. The general lesson: a test double that simplifies process topology cannot
   catch bugs that exist only because of process topology, which is why the compose
   smoke is part of the acceptance checklist and not a nicety.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| FastAPI and event-loop ownership (F-26) | F10 | Every handler and every WebSocket share one asyncio event loop, so nothing blocking may run in the API process — simulation goes to the worker, file IO to `run_in_threadpool`, and /health must answer mid-race. |
| Pydantic response models as the contract (5.9.2) | F10 | The API's shapes declared once as validated classes ("change the spec before changing a shape"); `extra="forbid"` on requests so a typo'd field is a 422, not a silently dry race. |
| RQ job queue and worker topology (5.9.3, F-26) | F10 | Jobs are a function path plus args in Redis, drained by a separate process from the same Docker image; production runs SimpleWorker because the default forking worker discarded the load-once model cache per job — invisible under tests' in-process SimpleWorker. |
| Redis as queue, cache and pub/sub at once | F10 | One Redis wearing three hats named in configs/serving.yaml: RQ's job lists, the E-15 result cache (SET NX as an atomic claim against duplicate enqueues), and events:{run_id} pub/sub waking early WebSockets — coordination only, results live in Postgres. |
| Versioned cache keys and stale-run recovery (E-15) | F10 | `sim:{model_version}:{env_hash}:{scenario_digest}:{seed}` with version and hash read from the served manifest so a retrain cold-starts its namespace; a hit is checked against the row behind it, and a run dead past two job budgets has its key deleted rather than answering for seven days. |
| WebSocket playback clock (E-16) | F10 | The socket replays persisted lap_frames rows on an injectable timer (delay = fitted lap time / speed; 1x = one wall second per simulated second), so pause, seek, speed and reconnect are all reads and producer speed never couples to playback. |
| The two-future select loop | F10 | `asyncio.wait({receive, tick}, FIRST_COMPLETED)` races the client's next message against the frame timer; a message that changes playback cancels the in-flight tick, because at 1x waiting it out is a whole lap of wall clock. |
| Postgres advisory locks and transaction ownership | F10 | An application-defined mutex serialising concurrent migrators (both entrypoints migrate on boot); the lock SELECT's implicit transaction must be committed before alembic gets the connection, or alembic assumes caller ownership and the upgrade rolls back silently with exit 0. |
| Baked artifacts on ephemeral filesystems (F-26) | F10 | The frozen triplet, surrogate set and ribbons are COPY'd into the one serving image (precise .gitignore negations), never mounted or fetched at boot; MODEL_VERSION selects among what is baked or fails loudly at startup. |
| Operational provenance origin | F10 | The fourth config origin (decision, 22 Jul 2026) for engineering defaults — timeouts, page sizes, poll cadences — each carrying its sizing rationale, so RQ's silent 180 s default becomes an explicit, reviewable 600 s. |
