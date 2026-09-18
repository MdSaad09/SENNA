# F16 — Race engine extraction

Depends on: F05, F06 (both Done)
Spec anchors: 5.5 (all of it), 5.5.3, 5.5.4, 5.5.5, 5.6.2, F-16, A-05, M3

> **This feature extends master spec v3.0 rather than implementing a row of it.** The
> spec anchors above are the contracts F16 must *not* break, not the rows it delivers.
> The spec-auditor should read them as invariants: no physics constant moves, no reward
> term is added or removed, no legality becomes a penalty, no throughput gate slips.
> F16 is the first feature past the frozen build, and every later one (F17+) sits on it.

## Goal
Advancing one lap of a Formula 1 race stops being something only a reinforcement
learning agent can do. Today `F1RaceEnv.step()` *is* the race — 75 lines of inline tick
plus eight private resolvers, one hard-coded ego seat, and a reward computed on every
call whether the caller wants a scalar or not. After F16 there is a `senna/env/engine.py`
that advances a `RaceState` given twenty-two decisions and knows nothing about
Gymnasium, stable-baselines3, rewards or observations. `F1RaceEnv` becomes a thin
adapter that fills twenty-one seats from `rivals.py`, one from the learner, and converts
the outcome into the reward-observation-mask shape SB3 expects. The race becomes the
object; the agent becomes one of its customers.

Nothing about the simulation changes. A recorded race must replay byte-identical
through the new seam — that identity is the deliverable, not a side condition.

## Deliverables
- `senna/env/engine.py`: `begin_lap(state, scenario, rng, *, twin, lap_index) -> LapContext` resolving track status, neutralisation onset and weather before anyone decides
- `senna/env/engine.py`: `advance_lap(state, context, decisions, scenario, rng, *, twin, lap_index) -> LapOutcome` — the whole physical tick, no reward, no observation, no mask
- `senna/env/engine.py`: `LapDecisions` (pit: n_cars int array, mode: n_cars int array) — a value object, not a car-zero-plus-others shape
- `senna/env/dynamics.py`: finish the abandoned `LapOutcome` dataclass at :40 — it already carries five of the fields the engine returns and nothing imports it
- `senna/env/race_env.py`: `step()` reduced to coerce action, collect rival decisions, call the engine, then reward/mask/observe/info. The eight private resolvers move out; the ego bookkeeping stays
- `senna/env/state.py`: `ego` documented as an indexing convenience the engine ignores; no engine function may branch on it
- `tests/env/test_engine_identity.py`: the golden-trace equivalence suite (below)
- A short note at the engine seam recording the two-phase tick order, so later features do not reintroduce a decision that reads stale track status

## Out of scope
Any behaviour change at all. Specifically **not** in F16, each already scoped elsewhere:
- The mask-lag defect (the ego's mask is built from last lap's weather at `race_env.py:319` while rivals read this lap's at `:265`) — F16 exposes the seam that makes it fixable, and fixing it moves F14's numbers. Deferred.
- The pit-lane occupancy defect (`race_env.py:491` feeds the full ~22.8 s net pit loss into `pitlane.resolve_pit_lane`, whose own docstring calls that argument a stationary service draw, so two teammates 0.5 s apart pay ~+23 s) — deferred to the team feature.
- Driver identity (F17), physics uncertainty (F18), explanation language (F19), observation changes (F20), look-ahead (F21), multi-agent and teams (F22).
- Any second learning seat. F16 makes the engine seat-symmetric; it trains nothing new.

## Constants & configs
None. F16 introduces no numbers — it moves existing code across a module boundary. If
the implementation reaches for a new constant, that is a signal the extraction has
picked up scope it should not have, and the plan is wrong.

## Tests first
- **`test_golden_trace_identical`** — the headline. Record an `EventTrace` on the current
  code for a full race at two circuits, then replay through the extracted engine and
  assert exact equality across all twenty-two cars on `cumulative_time_s`, `positions()`,
  `soc_mj`, `compound`, `tyre_age`, `fuel_kg` and `retired`, every lap. Not `allclose` —
  equality. Any drift means the RNG draw order moved.
- **`test_rng_draw_order_preserved`** — a counting/recording RNG wrapper asserting the
  same sequence of draws, in the same order, with the same shapes, before and after.
  This is the test that will actually fail during the build.
- **`test_engine_imports_no_gym`** — grep-level guarantee, in the style of F01's
  ergast ban: `senna/env/engine.py` imports neither `gymnasium` nor anything under
  `stable_baselines3`/`sb3_contrib`, and defines no class inheriting `Env`.
- **`test_advance_without_reward`** — drive a full race through `advance_lap` alone, never
  constructing `F1RaceEnv`, and reach the flag with a classified field. Proves the engine
  has no reward dependency.
- **`test_seat_symmetry`** (property) — for a fixed seed and a fixed 22-wide decision
  array, permuting which index is called "ego" leaves every car's race identical. The
  engine must not privilege seat zero. This is the test that proves the inversion
  happened rather than being claimed.
- **`test_decisions_are_field_wide`** — a decision array differing only at seat 5 changes
  seat 5's race and, through traffic, the field's — but is accepted without the caller
  naming an ego at all.
- **`test_two_phase_ordering`** — decisions collected between `begin_lap` and
  `advance_lap` see this lap's track status and weather, not last lap's. Pins the seam
  that makes the deferred mask-lag fix a one-line change later.
- **`test_throughput_no_regression`** (marked slow) — the 5.6.2 gate re-measured; the
  extraction may not cost more than 5% of aggregate env steps/s. Current headroom is
  large (18,477 measured against a 300 floor), so this is a smoke alarm, not a squeeze.

## Done means
- [x] `senna/env/engine.py` exists and advances a race with no gym, SB3, reward or observation import — enforced over all six race modules by `test_engine_imports_no_gym`
- [x] `advance_lap` takes twenty-two decisions and branches on no ego index — on the live path; the twin is the documented exception (decision 2)
- [x] `F1RaceEnv.step()` is under 30 lines and contains no physics — **29 lines**, down from 75. It was 31 until the review fix dropped an unused argument from `begin_lap` and folded a three-line call onto one
- [x] The golden-trace suite passes byte-identical at two circuits, full race, all 22 cars
- [x] The seat-symmetry property test passes
- [x] `senna/eval` and `senna/serve` still pass unchanged — `frames.py` keeps its `env._state` reach
- [x] F14's evaluation suite reproduces its recorded numbers exactly — M1/M3/M5/M10 payloads diffed identical against a pre-extraction worktree with the frozen headline triplet
- [x] Throughput within 5% of the recorded 5.6.2 figure — 0.9% slower (8817 vs 8898 steps/s), measured by hand on both commits; no committed test asserts this
- [x] The unused `LapOutcome` in `dynamics.py` is either used or deleted, not left abandoned a second time

## Notes for the plan session
**The one real hazard is RNG draw order.** `self._rng` is consumed in eight methods
across the tick — track status, weather, failures, rival pit choices, pit time draws,
lap noise — and the number and order of draws is what makes a seed reproducible. Moving
a call earlier or later, or drawing a full-field array where the old code drew per car,
silently changes every race. Write `test_rng_draw_order_preserved` before touching a
line, and treat the golden trace as a bisect tool during the build rather than a gate at
the end.

**Two phases, not one.** Rivals need the track status and neutralisation onset before
they can decide (`_field_pit_choices` takes `onset` today), so status and weather must
resolve before decisions are collected. That is why the interface is `begin_lap` then
`advance_lap` rather than a single call. It also happens to be how a real race works:
observe the track, everyone commits, the lap runs.

**Watch the couplings that are not physics.** `_lap_noise()` reads
`self._rivals.sigma_mult`, so per-lap noise currently depends on which archetypes were
drawn — that is a rivals dependency living inside the tick and it needs an explicit home
in the new signature. `_capture()` writes the record trace mid-tick. Both must survive
the move without changing draw order.

**Do not fix what you find.** The extraction will surface the mask lag and the pit-lane
occupancy bug. Both are real, both are scoped elsewhere, and both change F14's numbers.
Record them in the ship report and move on.

**Reward stays exactly three terms.** F16 makes reward *optional to compute*, not
different. `reward_mode` already carries v3/terminal_only/v2 for F08's ablations; the
engine simply stops being the thing that decides.
