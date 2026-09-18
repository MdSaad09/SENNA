# F16 plan — Race engine extraction

Approved by Saad, 7 August 2026. Spec: `docs/spec/features/F16-engine-extraction.md`.

> F16 is the first feature past master spec v3.0. Its spec anchors are contracts it must
> not break, not rows it implements — the spec-auditor should read them as invariants.

## Objective & spec anchors

Make advancing one lap of a race something that does not require a reinforcement
learning agent. Today `F1RaceEnv.step()` (`race_env.py:248-322`) *is* the race: 75
inline lines plus eight private resolvers, `ego=0` hard-set at `:192`, and
`self._reward(...)` called unconditionally at `:318`. After F16 a `senna/env/engine.py`
advances a `RaceState` given twenty-two decisions and imports nothing from Gymnasium or
stable-baselines3; `F1RaceEnv` becomes the adapter that fills 21 seats from `rivals.py`,
one from the learner, and converts the outcome into reward, observation, mask and info.

Nothing about the simulation changes. Byte-identical replay is the deliverable, not a
side condition.

Anchors, as invariants:

- **5.5.3** — transition dynamics stay character-for-character. Call sites move, formulas do not.
- **5.5.4 / F-15** — exactly three reward terms. F16 makes reward optional to compute, never different.
- **F-16** — legality stays masks plus physics clipping. `_coerce`, `_snap_pit` and the penalty arm stay in the env: they are policy-facing, not race-facing.
- **5.5.5** — `reset(seed=...)` seeds every stream; SubprocVecEnv workers stay stateless. The engine takes an `rng` argument and owns no module-level randomness.
- **5.6.2** — the throughput gate; 18,477 steps/s measured against a 300 floor.
- **A-05 / M3** — the deterministic twin survives intact and gets a better home.
- **Hot-loop discipline** — nothing pandas-shaped reachable from the tick; the engine inherits this verbatim.

**The design insight from exploration.** `self._twin` is tested in seven separate places
inside the tick — `_resolve_track_status:343`, `_resolve_weather:384`, `_field_modes:399`,
`_lap_noise:410`, `_resolve_failures:433`, `_field_pit_choices:467`, `_pit_times:488`.
F16 collapses those into one seam: the twin becomes an **event source**, `record=True`
becomes an **event sink**, and the physics stops knowing either exists. This is worth
more than tidiness — a real-race twin built from FastF1 data is exactly an event source,
so this is also the plumbing any later digital-twin work needs.

## Deliverables

- **`senna/env/engine.py`** — new:
  - `begin_lap(state, scenario, rng, *, source, lap_index) -> LapContext` — resolves track status, neutralisation onset, weather. Mutates `track_status`, `status_laps_left`, `red_flags_seen`, `weather`, `wetness`; returns `red_flag` and `onset`. Runs before anyone decides, because rivals already need `onset` (`_field_pit_choices:461`).
  - `advance_lap(state, context, decisions, scenario, rng, *, source, sink) -> LapOutcome` — failures, gaps, energy, lap time, pit times, pit application, fuel burn, lap increment. No reward, no observation, no mask, no ego.
  - `LapDecisions(pit, mode)` — both n_cars wide. Not an ego-plus-others shape; that is the point.
- **`senna/env/dynamics.py`** — finish the `LapOutcome` dataclass abandoned at `:40-46`; it already declares five of the fields the engine returns and nothing imports it. Add `racing_time_s`, `pit_time_s`, `failed`, `red_flag`.
- **`senna/env/events_io.py`** — new, small. `TraceSource` / `LiveSource` / `TraceSink`. Where the seven twin branches go to live.
- **`senna/env/race_env.py`** — `step()` becomes: coerce action, collect the 21 rival decisions, `begin_lap`, `advance_lap`, ego bookkeeping, reward, mask, observe, info. The eight resolvers leave. Everything ego-shaped stays: `_coerce`, `_snap_pit`, `_ego_mask`, `_observe`, `_info`, `_terminal_info`, the `_ego_*` counters, the v2 reward block.
- **`senna/env/state.py`** — `ego` documented as an indexing convenience for the adapter; no engine function branches on it.
- **Engine seam notes** — new, short: the two-phase tick order and the draw-order rule, so a later feature does not reintroduce a decision reading stale track status, or vectorise a loop that must stay a loop.
- **`tests/env/test_engine.py`**, **`tests/env/test_engine_identity.py`** — per the `tests/<module>/test_<file>.py` convention.

## Constants & configs

F16 introduces no physics constants, and that is a checkable property of this plan. The
feature moves code across a module boundary; if the build reaches for a physics number,
the extraction has picked up scope it should not have.

One number appears, and it is a test threshold rather than a model constant:

| Name | Value | Origin | Home |
|---|---|---|---|
| `THROUGHPUT_TOLERANCE` | 0.05 | **operational** — three dataclass allocations per lap over ~60 laps is under a tenth of a percent of 18,477 steps/s; 5% is a smoke alarm with two orders of headroom, not a squeeze | `tests/env/test_engine_identity.py`, named module constant, rationale in a comment |

Declared explicitly because the interpretability contract treats an inline constant as a
defect, and a declared test threshold should be ruled on rather than discovered.

## Tests first

Written and shown failing before any engine code exists. The first two are the build's
instruments, not its gate.

1. **`test_rng_draw_order_preserved`** — a recording RNG wrapper capturing (method, shape) for every draw across a full race, asserted equal before and after. This is the test that will actually fail during the build and the one that localises the failure. The six draw sites, in the order they must stay: `advance_track_status` → `advance_weather` → `rivals.pit_choices` → `tyre_failure` (**per car, in a Python loop**, `:445-456`) → `_lap_noise` → pit-loss normals.
2. **`test_golden_trace_identical`** — the headline. Record a full race at two circuits on current `main`, replay through the engine, assert **exact** equality (not `allclose`) across all 22 cars, every lap, on `cumulative_time_s`, `positions()`, `soc_mj`, `compound`, `tyre_age`, `fuel_kg`, `retired`. Fixtures committed so the comparison survives the refactor.
3. **`test_engine_imports_no_gym`** — grep-level guarantee in the style of F01's ergast ban (R-04): no `gymnasium`, no `stable_baselines3`/`sb3_contrib`, no `Env` subclass, no pandas.
4. **`test_advance_without_reward`** — a full race through `begin_lap`/`advance_lap` alone, never constructing `F1RaceEnv`, reaching the flag with a classified field. The literal statement of the inversion.
5. **`test_seat_symmetry`** — *property test.* For a fixed seed and fixed per-car parameter arrays, live-path engine output is invariant to the value of `state.ego`. Live path only — see the decision below.
6. **`test_decisions_are_field_wide`** — a decision array differing only at seat 5 changes seat 5's race and, through traffic, the field's, with the caller never naming an ego.
7. **`test_two_phase_ordering`** — decisions collected between `begin_lap` and `advance_lap` observe this lap's track status and weather. Pins the seam that makes the deferred mask-lag fix a one-line change later.
8. **`test_event_source_round_trip`** — a race run under `TraceSink` and replayed under `TraceSource` reproduces itself; a shape-mismatched source raises at construction rather than misreplaying mid-race (the `_check_twin:135` guarantee, kept).
9. **`test_throughput_no_regression`** — marked `slow`.

Existing suites are part of the gate and must pass untouched: `test_determinism.py`,
`test_properties.py`, `test_twin.py`, `test_variants.py`, `test_stage_toggles.py`,
`test_race_smoke.py`, plus all of `tests/eval`, `tests/serve`, `tests/train`.

## Edge cases handled

- **E-04 red flag** — `_resolve_track_status` returns the event; `_apply_pits`/`_pit_times` grant free tyre choice and zero pit loss. Moves wholesale, including the `red_flags_seen < _max_red` cap and the `hazards="sc_vsc"` zeroing at `:93`.
- **E-05 pit-lane FIFO** — `resolve_pit_lane` keeps its call shape exactly. The known defect (full net loss passed where the docstring wants a stationary service draw, `:491-496`) is preserved as-is; fixing it moves F14's numbers and belongs to the team feature.
- **E-06 rival response** — `rivals.pit_choices` is called by the adapter now, not the engine: rivals become one strategy module filling 21 seats. Its RNG position is unchanged.
- **E-08 wet crossover** — untouched. `advance_weather` moves into `LiveSource` with no change to the integrator, including its one-lap 0.0 → 0.352 jump.
- **E-01 derate clipping** — `resolve_energy` is already pure in `dynamics.py`; call site moves only.
- **E-03 VSC vs SC** — `_status_pit_multiplier:502` and the `sc_burn_factor` branch in `_burn_fuel:527` move intact.
- **Incomplete-trace refusal** — the guard in `recorded_trace:239` stays: a race that retired before the flag raises rather than handing out a green-tailed twin.
- **Solo mode (`n_cars=1`, F07 Stage A)** — `draw_field` returns an empty non-ego set at `:131`; the engine must not assume `n_cars > 1`. Property tests parameterise over solo.

## Acceptance checklist

- [x] `senna/env/engine.py` exists; advances a race with no gym, SB3, reward, observation or pandas import
- [x] `advance_lap` takes 22 decisions and branches on no ego index on the live path
- [x] `F1RaceEnv.step()` is under 30 lines and contains no physics — **29 lines** (from 75). It was 31 until the review fix dropped `begin_lap`'s unused `scenario` argument
- [x] Golden-trace equality at two circuits, full race, all 22 cars, exact
- [x] Seat-symmetry property test passes on the live path
- [x] The seven `self._twin` branches inside the tick are gone, replaced by one event-source seam — one branch remains in `_field_decisions`, which is rival *strategy* replay and therefore adapter work, not engine work
- [x] `senna/eval` and `senna/serve` pass unchanged — including `frames.py`, which reaches into `env._state` at `:34` and keeps working
- [x] F14's evaluation suite reproduces its recorded numbers exactly — M1/M3/M5/M10 payloads diffed identical against a pre-extraction worktree, frozen headline triplet
- [x] Throughput within 5% of the 5.6.2 figure — 0.9% slower, measured by hand on both commits; the committed test asserts a ratio, not this
- [x] `dynamics.LapOutcome` is used, not abandoned a second time
- [x] Cold-cache `ruff` over the whole repo before the final gate

## Out of scope

Each of these is real, was found during exploration, and is fenced deliberately:

- **The mask-lag defect.** The ego's mask is built at `:319` from last lap's weather; the 21 rivals read this lap's at `:265`. The agent is structurally one lap behind its opponents on rain. F16 builds the seam that makes this a one-line fix and does not take it, because it moves F14's numbers.
- **The pit-lane occupancy defect** (`:491` against `pitlane.py:12-15`) — two teammates 0.5 s apart pay roughly +23 s.
- **Vectorising the per-car tyre-failure loop** (`:445`). The obvious optimisation; it would change draw order. Explicitly forbidden in F16.
- **Promoting `frames.py` off `env._state`.**
- Driver identity (F17), physics uncertainty (F18), explanation language (F19), observation changes (F20), look-ahead (F21), multi-agent and teams (F22). No second learning seat: F16 makes the engine seat-symmetric, it trains nothing.

## Decisions (Saad, 7 August 2026)

**1. The engine lives at `senna/env/engine.py`, not `senna/race/`.** A new top-level
package would say the inversion out loud, but it churns imports across roughly eight
modules and adds a way for the byte-identity proof to fail for reasons unrelated to the
physics. Get the seam right first; the address is a later mechanical move, once identity
has already passed once.

**2. Seat symmetry is asserted on the live path only, and the twin adapter is documented
as deliberately ego-aware.** The live path can be fully symmetric: `draw_field` already
writes per-car arrays with the ego's slot filled at `:141-148` (`sigma_mult[ego] = 1.0`),
so the asymmetry lives in field *construction*, which is its correct home. The twin path
cannot: `_resolve_failures:437-439` recomputes the ego's failure from its own tyre age and
`_capture:422-425` blanks the ego's row, and both are load-bearing for A-05, whose whole
purpose is to freeze the field while the ego varies. Weakening the test to cover both
paths would prove less than testing the live path honestly and writing the twin's
asymmetry down.

## Notes for the build

**The one real hazard is RNG draw order.** `self._rng` is consumed at six sites across
the tick, and the number and order of draws is what makes a seed reproducible. Moving a
call, or drawing a full-field array where the old code drew per car, silently changes
every race. Write the draw-order recorder first and use the golden trace as a bisect
tool during the build rather than a gate at the end.

**Two phases, not one.** Rivals need track status and neutralisation onset before they
can decide, so status and weather resolve before decisions are collected. That is why
the interface is `begin_lap` then `advance_lap`. It is also how a real race works:
observe the track, everyone commits, the lap runs.

**Watch the couplings that are not physics.** `_lap_noise():406` reads
`self._rivals.sigma_mult`, so per-lap noise depends on which archetypes were drawn — a
rivals dependency inside the tick that needs an explicit home in the new signature.
`_capture():414` writes the record trace mid-tick. Both must survive the move without
changing draw order.

**Do not fix what you find.** The extraction will surface the mask lag and the pit-lane
occupancy bug. Both are real, both are scoped elsewhere, both change F14's numbers.
Record them in the ship report and move on.
