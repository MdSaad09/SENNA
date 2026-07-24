# F13 — Live Simulation view + Counterfactual view

Approved by Saad, 24 Jul 2026. Q1 (the backend pair slice) answered yes: build the
minimal pair — real-strategy extraction, two linked runs, EventTrace pairing — which
also builds the recorder F14's paired harness needs. Reconnect and scrub robustness
come before any visual polish, per the feature spec's own warning.

## Context

F13 builds the two persuasion views. View 5 shows the agent racing live — explicitly
in the simulator (R-05) — with decision cards streaming in per lap. View 6 is the
split-screen era-matched counterfactual: agent strategy beside the team's actual
strategy, honestly framed (F-24). The 5.13 demo opens cold into View 5 through a
deep link, so seed + circuit in the query string is a deliverable, not polish.

Planning verified the backend state. F10 already shipped and tested the whole View 5
serving side: `/ws/simulations/{run_id}` with the playback clock, `client:speed`
`client:pause` `client:seek`, `sim:lap` carrying the DecisionCard, reconnect
replaying stored frames (E-16). View 5 is frontend-only. View 6 had a real gap:
`POST /counterfactuals` enqueued a single frozen-agent run on 2024 physics tagged
`era_matched_model: "pending-F14"` — no second run, no pairing, and
`RealStrategyReplay` (senna/strategy/replay.py) imported by nothing in api/ or
worker/. A split screen needs two frame streams, so this plan includes the minimal
backend slice. Three design candidates were drafted against the real code and each
was adversarially reviewed before this plan; the reviewers' confirmed findings are
folded in.

## Objective & spec anchors

- 5.10.2 rows 5–6 — the view definitions and their stated brittleness
- E-16 — playback clock decoupled from sim speed; stored frames are the single
  source of truth for stream, scrub and reconnect
- E-15 — never explain a ghost: the card panel shows an honest empty state when the
  run's model_version has no stored explanations
- E-18 — WebGL context-loss overlay (CanvasHost from F11 already wires it; both new
  canvas paths inherit it — stated because the spec names it as an F13 deliverable)
- F-24 — era-matched counterfactual; header states the era config and "in-simulator
  comparison under stated assumptions"
- A-03 — the decision card: top-5 SHAP drivers, flip line, plain-language sentence,
  honesty footer carrying the fidelity badge (rendered verbatim from the server)
- R-05 — the live view states it is the agent in the simulator, never live timing
- F-28 — one canvas mounted at a time, ≤ 4 Html labels, ≤ 150 draw calls (5.10.3)
- 5.9.3 — the WS contract and playback speeds; 5.13 — the 0–15 s cold-open beat

## Flagged spec divergences

1. **JobAccepted gains `baseline_run_id: int | None = None`** (additive 5.9.2
   change, the F12 precedent). Set only by POST /counterfactuals; the pairing is
   also persisted in both runs' config JSONB so reloads and cache hits recover it.
2. **CounterfactualCreate gains `seed: int | None = None`** (additive). Today every
   POST draws a fresh seed before the E-15 key is built (simulations.py:64–66), so
   the endpoint can never dedupe. A seeded POST is idempotent, reproducible for the
   demo, and lets the pairing test actually discriminate.
3. **`simulation_runs.purpose` vocabulary gains `counterfactual_baseline`** —
   comment-only update in schema.py; free string column, no migration.
4. **Resume-from-pause is `client:seek`, not `client:speed`** — 5.9.3 lists no
   `client:play`, and in api/ws.py only the seek branch clears `paused` (ws.py:125);
   a speed message while paused changes tempo without resuming. The client
   implements seek-resume with a comment citing that line.
5. **Bloom is not mounted on /counterfactual** — the quality toggle has no effect
   there and the view says so. Bloom renders the root scene through a composer,
   which fights the two scissored View renders; 5.10.3 keeps bloom toggleable on
   every other canvas route.

## Deliverables

Backend pair slice:
- `senna/strategy/extract.py` — pure `plan_from_rows(rows, *, sim_total_laps,
  real_total_laps) -> PitPlan`; `compile_plan` becomes a thin pandas adapter over
  it (winner script and its tests unchanged). New async helper reading the driver's
  ingested laps. Rationale for DB extraction over configs/real_strategies.yaml: the
  yaml covers one circuit, winner only; the route accepts arbitrary {year, round,
  driver}.
- `api/routes/counterfactuals.py` — extract the driver's real stops at POST time
  (404 naming missing stint data when the laps carry none), accept the optional
  seed, insert two linked rows in one transaction (agent config: `baseline_run_id`,
  `real_stops`, `pairing: "event_trace"`, `era_matched_model: "pending-F14"`;
  baseline config: `agent_run_id`, `policy: "real_replay"`), keep the E-15 cache
  key on the agent run only, enqueue one `run_counterfactual` job. The cache-hit
  path recovers both ids from the stored agent config.
- `api/routes/simulations.py` — extract enqueue_run's key/dedupe/staleness
  scaffolding into a shared helper rather than duplicating it (an E-15 bug would
  hide in a fork of that logic).
- `worker/jobs.py` — `run_counterfactual(agent_run_id, baseline_run_id)`: run the
  real-strategy episode with `record=True` (RealStrategyReplay, balanced modes per
  A-07, grid pinned), take `recorded_trace()`, then twin-roll both sides — baseline
  without cards (RealStrategyReplay has no `.model`; DecisionLogger would break),
  agent with DecisionLogger — by parameterising the existing `_simulate` so there
  is exactly one frame/summary assembly path (this keeps the `era_matched_model`
  summary echo, jobs.py:66–69, alive for pairs too). Persist both frame sets and
  the agent cards in one transaction; mark and publish `events:{run_id}` for both
  ids on success and failure. Baseline row: `model_version` null, purpose
  `counterfactual_baseline`, summary carries `nominal_lap_s` and `snapped_stops`.
  EventTrace pairing, not seed-only: same-seed episodes diverge in events after the
  first different stop (INDEX decision 19 Jul); the trace donor is the real-replay
  side, matching evals.py's recorded-baseline convention. F14's paired harness
  needs this same recorder, so nothing is throwaway.
- `senna/serve/mapping.py` — `build_env(req, *, record=False)` passes through.

View 5 Live Simulation (frontend only; the backend is done and tested):
- `frontend/src/api/liveSocket.ts` — `LiveSocket`: URL from
  `import.meta.env.VITE_WS_BASE` + `/simulations/{run_id}` (nothing reads that var
  today), 5.9.3 message types, capped exponential backoff reconnect, terminal close
  codes 4404/4500, StrictMode-symmetric `dispose()`. On reconnect it syncs in one
  path: `client:seek {lap: head + 1}` then `client:speed` (the seek is skipped on
  first connect when the buffer is empty — sending it would only earn a duplicate
  frame). Provenance: one `recordProvenance` entry per socket lifecycle event
  (open / complete / failed / close), never per frame — 57 frames at 30x would
  flush the 50-entry ring and evict the REST entries carrying model_version.
- `frontend/src/stores/liveStore.ts` — frames buffer + cards map + connection
  state + playhead. Pure `insertFrame` (sorted, dedupes, same-reference on
  duplicate). `tick` reuses the exported `advancePlayhead` with maxLap = newest
  buffered lap, but keeps playing on a buffer-underrun clamp while streaming
  (end-of-race stop only once `sim:complete` arrived). Transient-subscription
  discipline as in replayStore.
- Scrub (the E-16 deliverable): back-scrub replays locally from the buffer — those
  are the stored frames, delivered once; `following` flips false, the stream keeps
  filling the buffer, playing forward onto the head rejoins live. After
  `sim:complete` the socket is closed by the server and scrub degenerates to View 2
  semantics over the full buffer. Pause = `client:pause` + local freeze; resume =
  `client:seek {lap: head + 1}` (divergence 4).
- `frontend/src/views/live/LiveSimulationView.tsx` — R-05 header ("the trained
  agent racing in the simulator — not live timing"), CanvasHost (E-18 inherited)
  mounted unconditionally with the scene gated on a non-empty buffer, reused
  ReplayScene/CarInstances/CarLabels, waiting state until the run summary delivers
  `nominal_lap_s` (the WS can outrun the 1 s status poll; refetch on first
  `sim:lap`), failed/not-found states.
- `frontend/src/views/live/DecisionCardPanel.tsx` — A-03 renderer addressed by the
  playhead (scrubbing shows that lap's card): decision headline, plain_language,
  probs labelled via constants mirroring cards.py's call strings, top-5 SHAP
  drivers as plain-div bars in served order (no chart lib — the server already
  trims to five), flip lines when present, honesty footer verbatim (fidelity
  per-head, model_version, statement). E-15 empty state when every card is null.
- Deep link: `?run=` wins; else `?circuit=&seed=[&grid=]` POSTs /simulations once
  (ref-guarded; the seeded body is idempotent through E-15 dedupe) and writes
  `?run=` back via history.replaceState; else RunPicker. RunPicker on this view
  gains the era / weather / rival-band selects — the comment at RunPicker.tsx:4–5
  promised the full matrix to F13, and the component was already made prop-driven.
- `frontend/src/views/replay/TransportControls.tsx` — moved to components/ and made
  presentational (props + subscribePlayhead), wired back to replayStore in View 2
  (behaviour unchanged, existing tests as the regression net) and to liveStore +
  client messages in View 5, plus a "go live" affordance and live chip.
- `frontend/src/views/replay/ReplayScene.tsx` — optional `store` prop defaulting to
  useReplayStore; optional `driveClock` and `labelPolicy` props (View 6). Zero-diff
  defaults for View 2.
- `frontend/src/api/types.ts` — DecisionCard, CounterfactualCreate, RaceDetail
  mirrors; JobAccepted gains baseline_run_id. (ModelVersion stays unmirrored — the
  badge arrives inside card.honesty; nothing calls GET /agents.)
- `sim:event` messages are received and dropped: the same RaceEvent dicts already
  ride inside each frame, and no F13 spec line asks for an event ticker
  (decision 3).

View 6 Counterfactual:
- `frontend/src/views/counterfactual/SplitCanvas.tsx` — ONE Canvas (F-28; the
  routeMount assertion keeps counting) with drei `View.Port`, two `<View>` panes as
  layout divs tunnelling scissored renders, PerfProbe, context-loss wiring, one
  root OrbitControls with `eventSource` on the wrapper so both panes orbit in
  lockstep — the shared root camera is the honest choice: any visual difference
  between panes is strategy, never viewpoint. Each pane sets
  `<color attach="background">` (PANE_BACKGROUND) — drei's scissored path disables
  autoClear and never clears otherwise, so an unset background smears frames (the
  red-team's confirmed renderer bug). Draw calls ≈ 8 per pane (ribbon 5 +
  CarInstances 3), ~16 of the 150 budget.
- `frontend/src/components/SceneFrame.tsx` — the light rig + Z-up group extracted
  from CanvasHost (which now uses it; no behaviour change) so pane scenes and root
  scenes share one stylised rig definition; per-pane children wrapped in Suspense
  (useGLTF suspends).
- `frontend/src/views/counterfactual/CounterfactualClock.tsx` — the one clock: a
  DOM-side rAF driver ticking useReplayStore with the agent run's nominal_lap_s
  and sharedMaxLap = max(both last laps); both panes mount ReplayScene with
  `driveClock={false}` and read the same playheadLap, so "synced lap clocks across
  speed changes" is true by construction and testable at store level.
  TransportControls reused as-is. The store is `reset()` on mount keyed on the run
  pair — without it, playback state leaks in from View 2 (red-team finding).
- Labels: `egoOnlyLabels()` in lib/labels.ts; each pane DOM-labels only the ego —
  2 of the ≤ 4 budget — and the label suffix becomes pane-aware: the baseline
  pane's car must not read "agent" (CarLabels hardcodes that suffix today).
- `frontend/src/lib/divergence.ts` — pure `findDivergenceLap` (first lap the ego
  stop signatures differ: in_pit, compound change, tyre_age reset) and
  `deltaSeries` (per-lap `baseline position − agent position`, positive = agent
  ahead, truncated to the shared lap range). DivergenceFlash: DOM border pulse on
  both panes when the playhead crosses the divergence lap forward (re-fires on
  scrub-back and replay), plus the persistent, jsdom-visible surfaces: "strategies
  diverge on lap N" caption and a chart ReferenceLine.
- `frontend/src/views/counterfactual/DeltaChartPanel.tsx` — recharts LineChart per
  the energy-view discipline (isAnimationActive false, reference-line array
  mirrored into an accessible list, lap-quantised playhead cursor). The delta line
  reuses EGO_ACCENT — white already means "the ego car", and the series is exactly
  the ego's gain; no new tint (the drafted lime collided with TEAM_COLOURS[8]).
- `frontend/src/views/counterfactual/CounterfactualHeader.tsx` — F-24 header, all
  claims from data: event identity from run config + GET /races; the era line with
  the pending clause rendered while `config.era_matched_model == "pending-F14"`
  (jobs.py also echoes it into summary — the test pins the field the header reads);
  the verbatim "in-simulator comparison under stated assumptions"; the driver's
  real result from RaceDetail. Pane captions "SENNA agent strategy" / "actual
  {year} strategy (replayed in-simulator)".
- Data flow: `?year=&round=&driver=[&seed=]` POSTs /counterfactuals once
  (ref-guarded; seeded links idempotent per divergence 2), writes `run=` back,
  polls both runs with useSimulation, fetches both frame sets with useRunFrames on
  completion, `useRace` hook (selects results; the laps payload is not needed). No
  WebSocket, and that is E-16-consistent: both runs are complete replays and GET
  /frames reads the same lap_frames rows the socket would stream. Partial states
  (one running, one failed, missing params, POST 404 detail verbatim) render as
  status rows with the canvas still mounted. Race-length mismatch: the clock spans
  the longer run, the shorter pane's cars park at their final frame (existing
  clamps), deltaSeries stops at the shared range, caption states "baseline ends on
  lap N". 20-car 2024 grids flow through untouched (verified: everything sizes
  from frames, carLivery is total).
- Test seams: `test/fakeSocket.ts` (FakeWebSocket + installer mirroring
  installFetchStub — jsdom has no WebSocket), installFetchStub made method-aware
  with POST routes for /simulations and /counterfactuals (today it ignores `init`,
  so the deep-link tests are unwritable without this), mockR3F's dreiMock gains a
  View stub, fixtures for cards, the counterfactual pair and races.
- `routes.tsx` swaps both stubs; `routeMount.test.tsx` extends the hops. Ship
  order: backend slice, then View 5, then View 6 (reconnect and scrub first, per
  the feature spec's note).

## Constants & configs

Frontend (frontend/src/config/constants.ts unless noted; each pinned by
constants.test.ts):

| Name | Value | Origin |
|---|---|---|
| PLAYBACK_SPEEDS | [1, 5, 10, 30] | already present from F11 — sourced 5.9.3, mirrors configs/serving.yaml playback.speeds; reused, not added |
| WS_RECONNECT_BASE_MS | 500 | operational — first retry no more eager than the server's own store poll (serving.yaml ws.status_poll_s 0.5 s) |
| WS_RECONNECT_FACTOR | 2 | operational — plain doubling, reaches the cap in four retries |
| WS_RECONNECT_MAX_MS | 8000 | operational — worst-case retry gap stays under what a demo audience tolerates; the feature spec stakes the demo on reconnect |
| WS_STATUS_OPEN | 101 | sourced — HTTP 101 Switching Protocols, the status a WS open represents in the provenance log |
| DEFAULT_GRID_POSITION | 8 | operational — hoisted from RunPicker's inline default so the deep link and the picker cannot drift |
| PIT_ACTION_LABELS / MODE_ACTION_LABELS | mirror of cards.py _PIT_CALLS / _MODE_CALLS | sourced — labels the card's unlabelled probability arrays; pinned verbatim against the Python strings |
| DIVERGENCE_FLASH_MS | 900 | stylised — long enough to register at 30x, where a lap lasts ~3 s of wall clock |
| DIVERGENCE_FLASH_TINT | #f43f5e | stylised — rose, distinct from braking amber, X-mode violet, harvest teal, SOC sky and every TEAM_COLOURS entry |
| PANE_BACKGROUND | #0a0a0a | stylised — the app's neutral-950 backdrop; scissored panes must clear to it explicitly because the transparent-canvas trick cannot work there |
| WS base fallback | "ws://localhost:8000/ws" | operational — in liveSocket.ts, mirrors docker-compose / spec 5.11.2 dev value; client.ts precedent |

Delta line colour: EGO_ACCENT reused from liveries.ts, not a new constant — one
colour keeps one meaning. Backend: no new numeric constants; the slice reuses
provenanced entries (queue.job_timeout_s 600 has order-of-magnitude margin — the
two extra card-free episodes take seconds; replay mode balanced per
configs/baselines.yaml A-07 note; cache.ttl_days 7 unchanged).

## Tests first

Backend (pytest; DB/Redis-gated tests slow-marked, conftest create_and_drain):
1. tests/strategy/test_extract.py — plan_from_rows unit: three-stint layout yields
   two stops at the next stint's out-lap on its compound; final stint yields none;
   stint-less rows yield the empty plan; identity rescale when distances match.
2. tests/strategy/test_extract.py — hypothesis property test, @pytest.mark.property
   (the backend convention — pinned dependency and marker; the frontend's
   seeded-loop style is frontend-only): random stint layouts over random distances
   → stop laps strictly increasing, within [1, sim_total_laps], count = pit-ended
   stints.
3. tests/api/test_counterfactuals.py — POST returns run_id and a distinct
   baseline_run_id; both rows queued; configs carry the pairing fields both ways;
   baseline model_version is null; a seeded second POST dedupes to the same pair.
4. tests/api/test_counterfactuals.py — the pairing mechanism directly: the pair job
   hands the same recorded EventTrace to both twin rolls (stubbed recorder unit),
   and the seeded slow run asserts identical per-lap sc events across the pair —
   with the seed field, the test can pick a seed that produces one.
5. tests/api/test_counterfactuals.py (slow) — end to end: both complete; agent
   /decisions non-empty, baseline /decisions == []; baseline summary carries
   nominal_lap_s and snapped_stops; both frame sets show 20 cars; the agent
   summary still echoes era_matched_model == "pending-F14" (the screenshot field —
   re-pinned so the pair path cannot silently drop it).
6. tests/api/test_counterfactuals.py — driver with stint-less laps → 404 naming the
   missing stint data; (slow) a baseline episode failure marks both rows failed,
   deletes the E-15 key, publishes "failed" on both channels.
7. tests/api/test_ws_stream.py — a socket on the baseline run receives sim:lap with
   card: null every lap and a normal sim:complete.

Frontend (vitest; FakeWebSocket + method-aware fetch stub):
8. stores/liveStore.test.ts — tick clamps at the buffer head and keeps playing
   while streaming (underrun ≠ end-of-race); stops at the final lap after
   complete; scrub-back flips following and moves only the playhead; playing onto
   the head rejoins live. Property (seeded mulberry32 loop): random-order inserts
   with duplicates through insertFrame always yield 1..N sorted, duplicates
   returning the same reference.
9. api/liveSocket.test.ts (fake timers) — URL from VITE_WS_BASE + fallback;
   first connect sends no seek; reconnect syncs seek-then-speed; backoff
   500→8000 capped; buffered laps deduped; 4404/4500 and post-complete closes
   terminal; dispose() leaves zero timers and sockets (StrictMode symmetry);
   provenance gets exactly lifecycle entries, never per-frame.
10. views/live/LiveSimulationView.test.tsx — the E-16 spec test: stream laps 1..10
    through the fake socket, scrub to lap 3, the rendered lap and card deep-equal
    the exact delivered payload and no client:seek was sent. The E-15 spec test:
    all-null cards → the "no stored explanations for model version X" line, no
    error. Pause sends client:pause (freeze pinned at store level — the R3F mock
    stubs useFrame, so a view-level freeze assertion would pass vacuously); resume
    sends client:seek {lap: head+1}; a speed button sends client:speed. R-05
    header text. Deep link ?circuit=&seed= POSTs once inside an explicit
    <StrictMode> render and writes ?run= back.
11. views/live/DecisionCardPanel.test.tsx — decision + plain_language; exactly the
    served driver pairs, served order; flip lines only on the pit-lap fixture;
    honesty statement verbatim + per-head fidelity + model_version.
12. lib/divergence.test.ts — fixed cases (differing pit lap; same lap different
    compound; identical → null) and a seeded-loop property test: random ego stop
    schedules → result equals a naive first-difference reference, null iff equal
    on the shared range. deltaSeries sign convention (baseline P5, agent P3 → +2)
    and truncation.
13. stores/replayStore.test.ts extension — property: advancePlayhead composed over
    random delta/speed sequences stays monotone, matches the summed formula, and
    clamps — one store means both panes read one value, so this IS the
    synced-clocks spec test at its root; CounterfactualClock.test.tsx (rAF
    stubbed) pins the driver: rate follows speed changes, paused store does not
    advance, unmount cancels.
14. views/counterfactual/CounterfactualView.test.tsx — deep link POSTs once under
    <StrictMode> and writes run= back; run= present → no POST; store reset on
    mount (arriving with playing=true / stale playhead starts clean); partial
    states each keep exactly one canvas; honesty header pins the era line, the
    pending-F14 clause (present and absent), the verbatim in-simulator sentence
    and the real-result line; divergence caption + delta mirror rows with sign
    convention; "baseline ends on lap N" on the mismatched-length fixture;
    baseline pane's ego label does not read "agent".
15. lib/labels.test.ts extension — egoOnlyLabels returns exactly the ego; two
    panes ≤ MAX_HTML_LABELS. routeMount.test.tsx — /live and /counterfactual each
    mount exactly one canvas; peak across all hops stays ≤ 1 (F-28).
16. config/constants.test.ts — new constants pinned exactly; action labels equal
    the cards.py strings verbatim.

## Edge cases handled

- E-15 — WS card is null on unexplained laps; REST /decisions returns [] — the
  panel renders the honest empty state, never an error. The baseline run has no
  cards by construction (no policy network ran), which is the same honesty.
- E-16 — the client never re-simulates and never invents a second source: live
  scrub replays the delivered stored frames, reconnect replays from Postgres,
  View 6 reads the same lap_frames rows over REST.
- E-18 — both canvas paths run through the CanvasHost context-loss wiring
  (SplitCanvas mounts the same hooks); the overlay and its tests exist from F11.
- Protocol quirks pinned by tests: resume-is-seek (divergence 4), the guaranteed
  duplicate frame racing a reconnect seek (absorbed by insertFrame), a
  socket-before-completion waiting state gated on nominal_lap_s.
- Failure honesty: sim:failed and close 4404/4500 render terminal states; a
  half-failed pair marks both runs failed rather than showing a one-legged
  comparison.

## Acceptance checklist

- [ ] A cold deep link opens mid-race with cars moving and cards arriving — the
      5.13 opening beat
- [ ] The counterfactual view runs an era-matched pair end to end with the honesty
      header
- [ ] The perf budget holds with the split viewport: 1 canvas, ~16 draw calls of
      the 150 budget asserted by PerfProbe, ≤ 4 Html labels, 45 fps floor on a
      Chrome trace of the split route
- [ ] Scrub, pause, resume, speed change and reconnect all work against the live
      compose stack, not just the fake socket
- [ ] npm test, tsc -b, npm run lint, pytest -m "not slow" all green;
      `rm -rf .ruff_cache` before the final lint (a warm cache can hide I001 on
      tests-first features); CI checked after /land

## Out of scope

- Recruiter-script polish (F15); mobile 3D and broadcast cameras stay cut (R-08)
- The ten-race M2 counterfactual numbers, bootstrap CIs, and the 2024 Stage-C
  fine-tune (F14) — the pending-F14 clause stays on screen until then
- An event ticker for sim:event messages (no spec line asks for one; the events
  already ride inside each frame if F15 wants it)
- GET /agents consumption (the fidelity badge arrives inside every card's honesty
  block)
- Full ribbon library commit before the video — separate INDEX.md decision

## Decisions (Saad, 24 Jul 2026)

1. **Q1 answered yes**: build the minimal backend pair slice — real-strategy
   extraction, two linked runs, EventTrace pairing. It doubles as the recorder
   F14's paired harness needs. The rejected alternative (right pane rendering real
   telemetry from GET /races) would compare a simulation to reality, conflating
   model error with strategy difference — the exact confusion F-24 exists to
   prevent.
2. The pair runs as one RQ job, trace donor = the real-replay side, matching the
   evals.py recorded-baseline convention — "what the agent would have done in that
   race". A replay-side DNF fails the pair loudly; no silent seed-only fallback.
3. Real stops come from ingested laps at POST time, frozen into the run config;
   the worker never touches pandas (hot-loop discipline holds).
4. sim:event is dropped client-side; the frame's own events list is the single
   source (a ticker would double-count and de-sync from scrub).
5. The live view's RunPicker gains the era/weather/rival-band selects, honouring
   the "full matrix is F13's live view" comment recorded in F12.
6. Seedless deep links are not idempotent (the server draws the seed); F15's demo
   links must always carry seed= — one line for the F15 plan.
7. Reconnect and scrub land before any visual flourish; ship order is backend
   slice → View 5 → View 6.

## Ship-process notes

- `rm -rf .ruff_cache` before the final lint gate; verify CI green on GitHub
  Actions after /land (private repo — F03–F06 once merged red unnoticed).
- The perf checklist item needs a manual Chrome trace of the split route; jsdom
  cannot measure draw calls.
- drei View pointer events and the eventSource + root OrbitControls wiring are
  read-from-source, not shipped precedent: verify both early in /ship; the
  fallback is passing domElement to OrbitControls explicitly, and pane-level car
  selection is droppable (not a spec deliverable).
