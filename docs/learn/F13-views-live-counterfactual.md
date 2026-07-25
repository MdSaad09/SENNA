# F13 — The live view and the counterfactual

## What we built and why

These are the two persuasion views. View 5 answers "show me the agent racing, now": a
run streams in lap by lap over a WebSocket, cars move on the track, and each lap's
decision card — the SHAP drivers, the flip line, the honesty footer — arrives beside
it. The header says, in words, that this is the trained agent in the simulator and
never live timing (R-05). View 6 answers the dissertation's headline question: what
would the agent have done in a real race? It splits the screen — agent strategy on the
left, the driver's actual strategy on the right, replayed in the same simulator on the
same random events — with an honesty header stating exactly what is being compared
(F-24).

View 5 needed no new backend: F10 already built and tested the WebSocket playback
clock. View 6 had a real gap. `POST /counterfactuals` used to enqueue one agent run
and nothing else; a split screen needs two frame streams. So F13 ships a minimal
backend pair slice: the route extracts the driver's real pit stops from the ingested
laps at POST time, inserts two linked run rows, and one worker job produces both frame
sets — by recording the real-strategy episode once and then replaying both strategies
against that recording's exact event sequence. That pairing choice is the most
examinable thing in the feature, and the rejected alternative matters as much: we do
not render real telemetry in the right pane, because comparing a simulation to reality
would conflate model error with strategy difference — the confusion F-24 exists to
prevent (plan decision 1).

The frontend discipline from F11 and F12 carries through. One canvas per route, even
for a split screen. Nothing re-renders at frame rate. Every number on screen came from
the API. And when something cannot be honest — no stored explanations for this model,
a baseline race that ends early, a pending era-matched model — the view says so in
words instead of hiding it.

## New ideas in this feature

**A WebSocket client, versus REST.** Everything the frontend fetched so far was
request-response: ask once, get an answer, done. A WebSocket is a single long-lived
connection where either side can send at any time, so it has a *lifecycle* — open,
messages, close — and each stage needs handling that a fetch never does. Open means
resync (where was I?). Message means route by type. Close means decide: is this
terminal, or do I retry? Our client retries with capped exponential backoff (500 ms
doubling to 8 s) unless the close code says retrying cannot help (4404 no such run,
4500 broken summary) or the race already finished. Mental model: REST is sending
letters; a WebSocket is a phone call, and a phone call can drop mid-sentence, so you
need a plan for calling back and asking "where were we?". The server side of this —
the playback clock, the two-future select loop — was F10; F13 is the browser end.

**The E-16 buffer and the idempotent insert.** E-16's rule is that stored frames are
the single source of truth. Client-side that becomes: every frame the socket delivers
lands in one sorted buffer, and scrubbing back replays *that buffer*, never a refetch
and never a re-simulation. The subtlety is reconnect: the resync seek races the frame
the server already had in flight, so one duplicate frame per reconnect is guaranteed,
by protocol, not by bad luck. `insertFrame` absorbs it by returning the same array
reference when the lap already exists — and because zustand compares by reference,
a duplicate costs zero re-renders too.

**StrictMode double effects and ref guards.** React 18's dev-mode `<StrictMode>`
deliberately runs every effect twice on mount — setup, cleanup, setup — to flush out
effects that are not safe to re-run. An effect that POSTs a simulation would enqueue
two races. The fix has two halves: a `useRef` flag (`posted.current`) that survives
the double invocation and blocks the second POST, and a `dispose()` on the socket that
is a true inverse of construction, so the mount-unmount-mount dance leaves exactly one
live socket and zero stray timers. The tests render inside an explicit `<StrictMode>`
so this is pinned, not hoped.

**Structural typing: the injectable store prop.** TypeScript checks whether two types
are compatible by their *shape*, not by their declared names — no inheritance needed.
`ReplayScene` declares a `PlaybackStore` interface (a callable selector hook plus
`getState()`, over a `PlaybackSlice` of the fields it reads), and any store matching
that shape plugs in: View 2 passes the replay store, View 5 the live store, View 6's
panes share the replay store with the clock turned off. One scene component, three
views, no base class. Mental model: the socket on the wall does not care what brand
the plug is, only that the pins fit.

**Scissored viewports and GL clear semantics.** View 6 wants two 3D panes, but F-28
allows one canvas. drei's `<View>` solves it by *tunnelling*: each pane is a plain
layout `<div>` in the DOM, and its scene is teleported into the one shared canvas,
where `<View.Port>` renders each scene clipped to its pane's screen rectangle — that
clipping is GL's *scissor test*. One canvas, one context, two scenes. The catch is
clearing. A full canvas normally erases itself between frames (`autoClear`); the
scissored path turns that off and only clears a view whose scene sets an explicit
background. Skip the `<color attach="background">` and each frame draws over the last
— cars smear ghost trails across the pane. That was a confirmed red-team finding, so
the background is a named constant (`PANE_BACKGROUND`) with its provenance comment.

**Trace-donor pairing, applied to serving.** The deterministic twin and EventTrace
are F06 ideas — one line of recap: same seed is not same race, because the RNG stream
consumes a policy-dependent number of variates (a tyre only rolls for failure past its
cliff, a stop only draws service time when it happens), so two policies on one seed
diverge in weather and safety cars after their first different stop
(`senna/env/twin.py`'s docstring says exactly this). What is new in F13 is using it in
the serving path: the pair job records the real-replay episode once, then twin-rolls
*both* legs on that recording's trace. The donor is the replay side — "what would the
agent have done in *that* race" — matching the recorded-baseline convention evals.py
already uses. The viva answer: **seed pairing alone fails because RNG variates are
consumed policy-dependently, so the legs would race different weather after the first
different stop; the pair job records the real strategy's episode and replays both
strategies on its EventTrace, so any difference between the panes is strategy, never
luck (F-24, A-05).**

**Purpose-namespaced cache keys.** F10's E-15 key was
`sim:{model_version}:{env_hash}:{scenario_digest}:{seed}`. A counterfactual agent leg
now runs the same scenario and seed as a plain simulation could — but twin-rolled on
recorded events, so its frames are a different race. Without a discriminator the two
would share a key: a stored pair could answer a plain `POST /simulations`, or a plain
run could dedupe a pair request down to one leg. The fix is a `purpose` field folded
into the scenario digest, so each purpose gets its own namespace by construction.

Name-checked from earlier lessons, not re-taught: zustand's three doors and transient
subscriptions (F11), the WebSocket playback clock and two-future select loop (F10),
versioned E-15 keys and stale-run recovery (F10), the deterministic twin (F06), the
A-07 strategy-policy interface (F06), react-query polling (F11), the jsdom WebGL
boundary and pure `lib/` logic (F11), the provenance ring (F11), the browser boundary
F-27 (F00), and the hot-loop rule (F05).

## The code, guided

Reading order: the backend pair slice first, then the live view, then the split view.

### senna/strategy/extract.py — the real strategy, as a pure function

The winner-extraction script existed; F13 pulls its heart out into `plan_from_rows`,
a pure function over bare tuples — no pandas, no database — so the API route and the
worker share it without either touching a frame (the hot-loop rule holds in serving
too). This is the function that turns a real race into something the simulator can
replay, so it gets the line-by-line read.

```python
    stints: dict[int, list] = {}
    for lap_number, stint, compound, pit_in_time_s in rows:
        if stint is None:
            continue
        stints.setdefault(int(stint), []).append((int(lap_number), compound, pit_in_time_s))
```

Group the driver's laps by stint number, skipping laps where FastF1 had no stint data
— a null stint is a data gap, not a strategy fact. The caller upstream 404s if *every*
lap is stint-less, because then there is no strategy to replay at all.

```python
    ordered = [sorted(stints[number]) for number in sorted(stints)]
    stops = []
    for current, following in zip(ordered[:-1], ordered[1:], strict=False):
        if not any(pit_in is not None for _, _, pit_in in current):
            continue
        out_lap_real, compound, _ = following[0]
```

Walk consecutive stint pairs. A stint that never records a pit-in time ended without a
pit stop — a red-flag tyre change, say — and the sim has no such move, so it yields no
stop. Otherwise the stop happens at the *next* stint's first lap (the out-lap), on the
next stint's compound: that is when and what the car actually changed to.

```python
        stops.append((
            round(out_lap_real * sim_total_laps / real_total_laps),
            None if compound is None else str(compound),
        ))
```

The lap is rescaled from the real race distance to the sim's (identity when they
match). A null compound passes through as `None` deliberately — the route turns it
into a 404 that *names* the missing compound data, instead of a `"None"` tyre dying
opaquely in the worker.

```python
    laps: list[int] = []
    for lap, _ in stops:
        laps.append(max(lap, 1, laps[-1] + 1 if laps else 1))
    for i in range(len(laps) - 1, -1, -1):
        laps[i] = min(laps[i], sim_total_laps - (len(laps) - 1 - i))
```

The repair passes. A shortened sim can rescale two out-laps onto the same lap; the
forward pass nudges each stop to be at least one lap after the previous (dropping a
stop would understate the real strategy). The nudge can push the tail past the race
distance, so the backward pass caps each lap so every later stop still fits before the
flag. A hypothesis property test pins the invariants: strictly increasing, inside
`[1, sim_total_laps]`, one stop per pit-ended stint.

### api/routes/simulations.py — the E-15 scaffolding, shared not forked

Block-level: `enqueue_run`'s key-check, staleness and SET NX claim logic is extracted
into `draw_seed`, `fresh_cache_hit` and `claim_key_or_yield` so the counterfactual
route imports them instead of copying them — a fork of that logic is exactly where a
stale-cache bug would hide. `claim_key_or_yield` earns one note: on losing the SET NX
race it deletes every row this request just inserted (the pair passes both ids), so a
lost race leaves no orphan legs.

### api/routes/counterfactuals.py — one POST, two linked rows

Block-level with the linking excerpt. The route resolves the race and the driver's
grid slot from the ingested results (404 with a plain sentence when missing), builds
the 2024 scenario, extracts the real stops via `plan_from_rows` *at POST time* and
freezes them into the run config — so the worker never reads laps and a retry replays
the identical plan. Then the pairing:

```python
        baseline_id = (await conn.execute(
            insert(SimulationRun).values(
                ..., model_version=None, purpose="counterfactual_baseline",
                config={**sim.model_dump(), **identity, "policy": "real_replay"},
            ).returning(SimulationRun.id)
        )).scalar_one()
        agent_id = (await conn.execute(
            insert(SimulationRun).values(
                ..., purpose="counterfactual",
                config={..., "era_matched_model": "pending-F14",
                        "baseline_run_id": baseline_id, "real_stops": real_stops,
                        "pairing": "event_trace"},
            ).returning(SimulationRun.id)
        )).scalar_one()
```

Both rows in one transaction, each config naming the other's id, so a cache hit or a
page reload can recover the whole pair from either row. The baseline's
`model_version` is null on purpose: no policy network runs a replay, and that null is
what E-15 reads as "nothing to explain". The agent leg's config carries the
`pending-F14` clause the frontend header will render until the real era-matched
fine-tune exists. The cache key is built with `purpose="counterfactual"` and lives on
the agent run only; a seeded second POST dedupes to the same pair.

### worker/jobs.py — run_counterfactual, the pairing made real

`_run_pair` is the core of the feature, so the middle of it gets the line-by-line
read. Setup (block-level): mark both rows running, with `.one()` on each select as a
loud existence check — a pair job pointed at a missing leg must die here, not
half-run. Then:

```python
        recording_env = build_env(req, record=True)
        replay = RealStrategyReplay(plan, recording_env.scenario,
                                    config.load("baselines")["replay"])
        _episode(recording_env, replay, seed=req.seed,
                 reset_options={"grid_position": req.grid_position})
        trace = recording_env.recorded_trace()  # raises loudly on a DNF'd recording
```

The recording roll. The env is built with `record=True` (a one-argument pass-through
in `serve/mapping.py`), the replay policy is the A-07 baseline with balanced modes,
and the episode runs at the request's seed. `recorded_trace()` is the harvest: every
event the race applied. A DNF'd recording raises rather than donating a broken trace
— no silent fallback to seed-only pairing (plan decision 2).

```python
        baseline_frames, baseline_summary = _episode(
            build_env(req), replay, seed=req.seed, reset_options={"twin": trace})
        baseline_summary["snapped_stops"] = int(replay.snapped)  # A-07 honesty counter
```

The baseline leg is *not* the recording's own frames — it is a fresh env twin-rolled
on the trace. That keeps both legs on the exact same footing: same env mode, same
frame-assembly path, noise zeroed by the twin, so nothing about how the recording was
captured can leak into the comparison. `snapped_stops` counts real stops the replay
had to nudge onto legal laps — an honesty number the summary carries.

```python
        agent_env = build_env(req)
        policy = Sb3Policy(serving.model, serving.venv.normalize_obs)
        logger = DecisionLogger(policy, circuit=req.circuit_id, seed=req.seed)
        agent_frames, agent_summary = _episode(agent_env, logger, seed=req.seed,
                                               reset_options={"twin": trace})
        cards = _cards_for(logger.records, agent_env, policy, serving)
```

The agent leg: same trace, but the frozen policy decides and the `DecisionLogger`
records every decision for TreeSHAP cards. The baseline leg gets no logger —
`RealStrategyReplay` has no `.model`, so `DecisionLogger` would break, and a replay
has no policy network to explain anyway. That asymmetry *is* the E-15 honesty: the
baseline's card stream is empty by construction.

Both legs run through the one `_episode` helper the single-run path also uses, so a
summary field cannot exist on one leg and silently miss on another —
`era_matched_model` is echoed into the agent summary exactly as the single-run path
does, because summaries are what screenshots quote. Persistence (block-level) is one
transaction for both legs: delete-then-insert frames and decisions (a retried job
lands on the same rows), mark both complete, insert cards on the agent only. Failure
anywhere marks *both* rows failed, deletes the E-15 key and publishes `failed` on both
channels — a one-legged comparison must never look complete.

### senna/serve/cache.py — the purpose discriminator

```python
    scenario["purpose"] = purpose
```

One line, folded into the scenario dict before it is hashed into the key's digest.
`run_simulation` passes `purpose="serve"` (or the row's own purpose), the pair job
`"counterfactual"`, so the namespaces can never collide. `tests/serve/test_cache_key.py`
pins that identical requests under different purposes produce different keys.

### frontend/src/api/liveSocket.ts — the phone call

The class wraps one run's socket. Construction connects; `dispose()` is the exact
inverse. The two lifecycle handlers carry the protocol knowledge, so they get the
close read. Open:

```ts
    const { frames, speed, playing } = useLiveStore.getState();
    const head = frames.length === 0 ? 0 : frames[frames.length - 1].lap;
    if (head === 0) return; // a fresh session: the server's defaults are ours too
    this.send({ type: "client:seek", lap: head + 1 });
    this.send({ type: "client:speed", speed });
    if (!playing) this.send({ type: "client:pause" });
```

On a first connect the buffer is empty and nothing is sent — the server starts at lap
1 at 1x, which is also our state. On a reconnect the client resyncs in one path: seek
just past the buffered head (a replayed connection always restarts at lap 1, and we
already have those frames), restore the tempo, re-pause if the viewer had paused. The
seek races the frame the server already sent before processing it, so one duplicate
frame arrives — guaranteed, and absorbed downstream. Close:

```ts
    const { complete, failed } = useLiveStore.getState();
    if (TERMINAL_CLOSES.has(event.code) || complete || failed) return;
    this.retryTimer = setTimeout(() => { ...this.connect(); }, nextBackoffMs(this.attempt++));
```

Retry only when retrying can help: 4404 and 4500 are the server saying it cannot, and
a finished race has nothing left to stream. `nextBackoffMs` is
`min(500 · 2^attempt, 8000)` — the first retry no more eager than the server's own
0.5 s store poll, the cap sized for a demo audience's patience (both provenanced in
`constants.ts`). One provenance entry per lifecycle event, never per frame: 57 frames
at 30x would flush the 50-entry ring and evict the REST entries carrying
model_version. `sim:event` messages are dropped on purpose — the same event dicts ride
inside every frame, and a second copy would double-count and de-sync from scrubbing.

### frontend/src/stores/liveStore.ts — the buffer is the truth

The store is View 5's E-16 surface, so its three moving parts get the line-level read.

```ts
export function insertFrame(frames: LapFrame[], frame: LapFrame): LapFrame[] {
  const at = frames.findIndex((held) => held.lap >= frame.lap);
  if (at === -1) return [...frames, frame];
  if (frames[at].lap === frame.lap) return frames;
  return [...frames.slice(0, at), frame, ...frames.slice(at)];
}
```

Sorted insert in four lines: append past the end, return the *same reference* on a
duplicate lap (the reconnect's guaranteed double — and an unchanged reference means no
subscriber fires), splice into place otherwise. Exported and pure, so the seeded
property test can hammer it with random-order duplicates and assert the buffer is
always `1..N` sorted.

```ts
    receiveLap: (frame, card) => {
      ...
      set({
        frames, cards,
        ...(state.following && state.playing ? { playheadLap: head } : {}),
      });
    },
```

While following, the stream *is* the clock: frames arrive on the server's playback
cadence (E-16), so the playhead simply rides the newest lap. Scrubbed back, the
buffer keeps filling and the playhead stays put.

```ts
    tick: (deltaS, nominalLapS) => {
      ...
      if (complete) { set(advanced); return; }
      set({
        playheadLap: advanced.playheadLap,
        following: following || advanced.playheadLap >= head,
      });
    },
```

`tick` reuses F11's `advancePlayhead` with the buffer head as the ceiling, and the
distinction it draws is the one the tests pin: after `sim:complete` the clamp is the
chequered flag and playback stops, but mid-stream the same clamp is only a buffer
underrun — keep playing, and touching the head rejoins live. Pausing, scrubbing and
speed are transient-subscription discipline exactly as in the replay store (F11); the
view reads the playhead through `subscribe`, never a render.

### frontend/src/views/live/ — the view and the card panel

`LiveSimulationView` is mostly wiring (block-level): the deep link resolves
`?run=` first, else `?circuit=&seed=` POSTs once behind the StrictMode ref guard and
writes `?run=` back with `history.replaceState` so the link stays shareable; the
socket effect creates and disposes symmetrically; the scene mounts once frames exist
and the 1 s status poll has delivered `nominal_lap_s`. The R-05 header is a string on
screen, pinned by test. Two moments earn excerpts. Resume:

```ts
    if (next) {
      // resume is a seek: only the server's seek branch clears its paused flag
      // (api/ws.py:125, plan divergence 4) — a speed message would not restart it
      socketRef.current?.sendSeek(headLap + 1);
    }
```

The 5.9.3 protocol has no `client:play`. Reading `api/ws.py`, only the `client:seek`
branch sets `paused = False`; a `client:speed` while paused changes tempo and leaves
the clock stopped. So resume is a seek to just past the head — a protocol quirk that
would cost an hour of confusion undocumented, which is why the comment cites the line
and a test pins the message. And the E-15 empty state:

```tsx
              <p className="text-xs text-neutral-500">
                no stored explanations for model version {run.data?.model_version ?? "unknown"}
                — this run streams without cards (a retrained model explains only its own runs, E-15)
              </p>
```

When every card in the stream is null, the panel explains *why* instead of erroring —
never explain a ghost, and never pretend an absence is a bug. `DecisionCardPanel`
itself renders the A-03 card verbatim: the server composed the decision line, the
plain-language sentence, the flips and the honesty footer, and the panel adds only
layout. The SHAP bars are plain divs from a centre line — sign as direction, pushes
toward the action go right — because five served numbers do not earn a chart library.
The one thing the client adds is names: the card's probability arrays arrive
unlabelled, so `PIT_ACTION_LABELS` / `MODE_ACTION_LABELS` mirror `cards.py`'s call
strings, pinned verbatim by `constants.test.ts`.

### frontend/src/views/counterfactual/SplitCanvas.tsx — two panes, one canvas

The scissoring described under "new ideas", in code. The canvas sits absolutely
positioned behind the two pane divs and contains only the shared machinery:

```tsx
      <Canvas ... eventSource={eventSource as MutableRefObject<HTMLElement>}>
        <View.Port />
        <PerfProbe />
        <OrbitControls makeDefault />
      </Canvas>
```

`View.Port` is where both tunnelled scenes render. `eventSource` points at the
wrapper element that contains both panes, so pointer events from either half reach the
one `OrbitControls` — and because both panes inherit the one root camera, dragging
anywhere orbits both in lockstep. That is an honesty choice as much as a technical
one: any visual difference between the halves is strategy, never viewpoint (F-24).
Each pane:

```tsx
    <View className="h-full w-full">
      <color attach="background" args={[PANE_BACKGROUND]} />
      <SceneFrame>
        ...
        <ReplayScene ... store={store} driveClock={false} labelPolicy="ego" ... />
```

The explicit background is the load-bearing line — drei's scissored path disables
autoClear and never clears a view whose scene has none, so without it cars smear
trails. `SceneFrame` is the light rig extracted from `CanvasHost` so panes and
full-canvas routes share one rig definition. Bloom is deliberately absent on this
route (it composits the root scene through an effect pass, which fights the scissored
renders) and the transport caption says so. The budget arithmetic: about 8 draw calls
per pane, roughly 16 of the 150; labels are `egoOnlyLabels` — each pane labels only
the ego, 2 of the 4-label budget. `routeMount.test.tsx` keeps counting one canvas
across every hop, so F-28 survives the split by measurement, not assertion.

### CounterfactualClock, divergence.ts and the delta chart

`CounterfactualClock` is the split view's only clock: a DOM-side `requestAnimationFrame`
loop ticking the replay store with the *shared* max lap, while both panes mount with
`driveClock={false}`. One writer, two readers, so "synced lap clocks across speed
changes" is true by construction — there is no second clock to drift. It lives outside
the canvas because jsdom mocks away `useFrame`, and a clock the tests cannot crank is
a clock the tests cannot pin. The view `reset()`s the store keyed on the run pair,
because arriving from View 2 with a stale playhead was a confirmed red-team finding.

`findDivergenceLap` compares the ego's *strategy signature* per lap — `in_pit`,
`compound`, `tyre_age` — and deliberately never position: the panes can swap fortunes
on lap one without the strategies differing, and the divergence flash must not fire on
luck. `deltaSeries` is `baseline position − agent position` (positive = the agent runs
ahead), truncated to the shared lap range because beyond the shorter race the
comparison is undefined. Both are pure functions in `lib/`, property-tested against a
naive first-difference reference. `DeltaChartPanel` draws the series in recharts under
the F12 energy-view discipline — animations off, a lap-quantised playhead cursor fed
by a transient subscription, and every row mirrored into an `sr-only` list because
jsdom sees no SVG: the mirror is what the tests and screen readers read. The delta
line reuses `EGO_ACCENT` — white already means "the ego car", and the series is
exactly the ego's gain. The header above it renders every F-24 claim from data: era
and grid size from the run, the model line with the `pending-F14` clause while the
config carries it, the verbatim "in-simulator comparison under stated assumptions",
and the driver's real-world result from `GET /races` — appearing whole or not at all,
so no screenshot ever catches a half-stated assumption.

### The tests that came first

Backend: `tests/strategy/test_extract.py` pins `plan_from_rows` on fixed layouts and
a hypothesis property (stops strictly increasing, in range, one per pit-ended stint).
`tests/serve/test_counterfactual_pairing.py` is the pairing spec with no database in
sight — the env is stubbed at `worker.jobs`' import seams and the assertion is
behavioural: one recording roll donates a trace, both twin rolls receive the identical
object. `tests/api/test_counterfactuals.py` covers the pair POST shape, the seeded
dedupe answering with the whole pair, the two 404s that *name* the missing stint or
compound data, and (slow) the end-to-end run: agent decisions non-empty, baseline
decisions empty, the `era_matched_model` echo intact, and a baseline failure marking
both rows failed with the key deleted. `test_ws_stream.py` adds a socket on the
baseline run receiving `card: null` every lap. Frontend: `liveStore.test.ts` draws the
underrun-versus-complete distinction and hammers `insertFrame` with a mulberry32
property; `liveSocket.test.ts` runs the whole lifecycle on fake timers — no seek on
first connect, seek-then-speed on reconnect, backoff 500→8000, terminal closes,
`dispose()` leaving zero timers; `LiveSimulationView.test.tsx` is the E-16 spec test
(stream laps 1..10, scrub to 3, the rendered lap deep-equals the delivered payload,
no `client:seek` sent) plus the E-15 empty state and the StrictMode single POST;
`CounterfactualView.test.tsx` pins the honesty header, the store reset, the divergence
caption and delta mirror, and that the baseline pane's ego label never reads "agent".

## How it connects

```
 browser
 ┌─ /live ──────────────────────────────┐  ┌─ /counterfactual ────────────────────┐
 │ LiveSocket ⇄ WS /ws/simulations/{id} │  │ POST /counterfactuals → run pair     │
 │ liveStore buffer (E-16, dedupe)      │  │ GET /frames ×2 · GET /races          │
 │ ReplayScene + DecisionCardPanel(A-03)│  │ SplitCanvas: 2 drei Views, 1 canvas  │
 └───────────────┬──────────────────────┘  │ one clock · divergence · F-24 header │
                 │                          └───────────────┬──────────────────────┘
                 ▼                                          ▼
 F10 API ── playback clock over lap_frames ── two linked SimulationRun rows
                 ▲                                          │ one RQ job
 worker ── run_simulation ──────────────── run_counterfactual:
           (single leg)                     record replay leg → EventTrace
                                            twin-roll baseline + agent on it
                                            persist both legs in one transaction
```

Both views read the same stored frames — the socket streams them on a clock, REST
pages them after completion — which is why View 6 needs no WebSocket at all. The
recorder built here is not throwaway: F14's paired evaluation harness needs exactly
this record-then-twin-roll machinery for the ten-race M2 numbers.

## Try it yourself

Frontend commands from `frontend/`; Python from the repo root.

1. **Watch a reconnect heal.** `docker compose up --build`, open
   `/live?circuit=bahrain_grand_prix&seed=7`, let a few laps stream, then in DevTools
   set the network to offline for ~3 seconds and back. Press backtick. You'll know it
   worked when the cars catch up seamlessly and the provenance ring shows a close
   entry, an open (101) entry, and not one entry per frame.

2. **Break the duplicate absorber.** In `stores/liveStore.ts`, delete the line
   `if (frames[at].lap === frame.lap) return frames;`. Run `npm test -- liveStore`.
   You'll know it worked when the seeded property test fails with its seed printed —
   the buffer now holds duplicate laps — and you can say which real protocol moment
   (the reconnect seek racing the in-flight frame) that line exists to absorb. Revert.

3. **Resume with the wrong message.** In `LiveSimulationView.tsx`, change the resume
   branch to `socketRef.current?.sendSpeed(speed)`. Run
   `npm test -- LiveSimulationView`. You'll know it worked when the resume test fails
   on the expected `client:seek` message, and you can point at `api/ws.py:125` to say
   why the green-looking alternative would leave the server paused forever. Revert.

4. **Collide the cache namespaces.** In `api/routes/counterfactuals.py`, change
   `purpose="counterfactual"` in the `sim_cache_key` call to `purpose="serve"`. Run
   `python -m pytest tests/serve/test_cache_key.py tests/api/test_counterfactuals.py -q -m "not slow"`.
   You'll know it worked when the key tests fail, and you can name the two bugs the
   discriminator prevents (a pair answering a plain POST; a plain run swallowing a
   pair). Revert.

5. **Smear the panes.** Comment out `<color attach="background" ...>` in
   `SplitCanvas.tsx`'s `ScenePane` and open a counterfactual in the browser. You'll
   know it worked when the cars leave ghost trails in both panes — the scissored path
   never cleared them — and no test caught it, because jsdom cannot see GL clears:
   this one lives on the runtime checklist, which is exactly why the constant carries
   its warning comment. Revert.

## Check yourself

1. Defend the pairing design: why does running both legs on the same seed not give a
   fair comparison, and what does the pair job do instead? Why is the trace donor the
   replay side and not the agent side?

2. View 6 shows two 3D scenes. How does it stay inside F-28's one-canvas rule, what
   is drei's `<View>` actually doing, and why does each pane need an explicit
   background colour?

3. View 5 uses a WebSocket and View 6 uses plain REST fetches. Why is that split
   right, and why is it consistent with E-16 rather than a contradiction of it?

4. Every reconnect delivers exactly one duplicate frame. Why is that guaranteed by
   the protocol rather than a race you could fix, and where is it absorbed?

5. The right pane replays the driver's strategy in the simulator instead of drawing
   the real telemetry, which we ingested and could render. Defend that choice.

---

### Answers

1. The RNG stream consumes a policy-dependent number of variates — a tyre only rolls
   for failure past its cliff, a stop only draws service time when it happens — so two
   policies on one seed diverge in weather and safety cars after their first different
   stop, and the comparison would mix strategy with luck. The pair job records the
   real-strategy episode once, takes its EventTrace, and twin-rolls both legs on that
   trace, so both races see identical events by construction (A-05, F-24). The donor
   is the replay side because the question is "what would the agent have done in *that*
   race" — the real race's events are the reference world — matching the
   recorded-baseline convention evals.py already established.

2. There is one `<Canvas>`, absolutely positioned behind two plain layout divs; each
   div is a drei `<View>` that tunnels its scene into the shared canvas, where
   `<View.Port>` renders each scene scissor-clipped to its pane's rectangle. One
   canvas, one GL context, two scenes — and `routeMount.test.tsx` keeps counting the
   peak at 1 (F-28). The scissored path disables autoClear and only clears a view
   whose scene sets a background, so a pane without `<color attach="background">`
   draws each frame over the last and cars smear trails — the explicit
   `PANE_BACKGROUND` is the clear.

3. View 5's race is still being produced, so the client needs a stream with a
   server-owned playback clock; View 6's runs are both complete, so `GET /frames`
   reads the very same `lap_frames` rows the socket would have streamed, and a socket
   would add reconnect complexity for nothing. That is E-16 working as designed:
   stored frames are the single source of truth, and stream, scrub and REST are just
   different reads over them — the client never re-simulates and never invents a
   second source.

4. On reconnect the server has already started replaying from lap 1 and typically has
   a frame in flight before it processes the client's resync seek, so one
   already-buffered lap arrives again — that is the protocol's ordering, not a fixable
   race. `insertFrame` absorbs it: a lap already in the buffer returns the same array
   reference, so the duplicate changes nothing and, because zustand compares by
   reference, triggers no subscriber either.

5. Real telemetry would put a simulation next to reality, so every gap between the
   panes would be model error plus strategy difference, inseparably — exactly the
   confusion F-24 exists to prevent. Replaying the real strategy in the same simulator
   on the same recorded events isolates the one variable the view claims to show: the
   strategy. The header then states the frame honestly — "in-simulator comparison
   under stated assumptions" — and the driver's actual result is shown alongside as a
   labelled fact from `GET /races`, not as a pane.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| WebSocket client lifecycle vs REST | F13 | A long-lived connection with open/message/close stages, unlike one-shot fetches: resync on open (seek past the buffer, restore tempo — resume itself is a seek, since only ws.py's seek branch clears paused), retry on close with capped backoff (500 ms doubling to 8 s), and treat 4404/4500 as terminal. |
| The E-16 client buffer and idempotent insertFrame | F13 | Every streamed frame lands in one sorted buffer that scrub replays verbatim — never a refetch — and a duplicate lap returns the same array reference, absorbing the one frame every reconnect seek is guaranteed to double-deliver at zero re-renders. |
| StrictMode double effects and ref guards | F13 | React 18's dev StrictMode runs each effect setup-cleanup-setup on mount to expose unsafe side effects; a useRef flag makes the deep-link POST fire once, and the socket's dispose() is a true inverse so the double mount leaves one socket and no timers. |
| Structural typing (the injectable PlaybackStore) | F13 | TypeScript matches types by shape, not name: ReplayScene accepts any store exposing selector-call plus getState over the PlaybackSlice fields, so the replay store, the live store and View 6's shared-clock panes all plug into one scene component. |
| Scissored viewports and GL clear semantics (drei View) | F13 | Two Views tunnel two scenes into one canvas, each rendered scissor-clipped to its pane's rectangle (F-28 keeps one context, one root camera keeps orbits in lockstep); the scissored path disables autoClear, so each pane must set an explicit background or frames smear. |
| Trace-donor pairing for served pairs | F13 | The pair job records the real-replay episode once and twin-rolls both legs on its EventTrace (donor = the replay side, evals.py's convention), because seed pairing diverges after the first different stop — F06's twin, now serving the F-24 comparison. |
| Purpose-namespaced cache keys (E-15 extended) | F13 | A purpose discriminator folded into the E-15 key's scenario digest, so a twin-rolled counterfactual leg never answers a plain /simulations POST for the same scenario and seed, and a plain run never dedupes a pair down to one leg. |
