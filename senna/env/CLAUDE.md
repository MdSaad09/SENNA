# senna/env/ — the race, and the adapter that lets an agent drive it

Since F16 this directory has two halves, and the split is the point.

**The race** is `engine.py` (the per-lap tick), `dynamics.py` (the formulas), `state.py`
(twenty-two cars as a struct of arrays), `events_io.py` (where a lap's events come from),
`pitlane.py` and `events.py`. None of it imports Gymnasium, stable-baselines3, pandas or
the adapter, and `test_engine_imports_no_gym` is parametrised over all six so the build
fails if that changes.

**The adapter** is `race_env.py`, plus `observation.py`, `masks.py`, `reward.py` and
`reward_v2.py`. It fills twenty-one seats from `rivals.py`, one from the learner, and
turns a `LapOutcome` into the reward-observation-mask shape SB3 expects.

## Rules that bite here

**The lap runs in two phases, and decisions go between them.**

    context = begin_lap(state, scenario, rng, source=..., lap_index=...)
    decisions = <every seat commits>
    outcome = advance_lap(state, context, decisions, scenario, rng, source=..., sink=...)

Rivals need the neutralisation onset before they can choose (E-06), so the track has to
resolve first. Do not add a decision that reads the track before `begin_lap`, and do not
fold the phases back into one call — the ego's action mask is the one thing still built
from the previous lap's weather (`race_env.py`, end of `step`), and closing that gap is a
scoped follow-up that depends on this seam staying open.

**Draw order is the seed (5.5.5).** The tick consumes rng at six sites, in this order:

    track status -> weather -> rival pit choices -> tyre failure (per car) -> pace noise
    -> pit service

Move one, or replace the per-car failure loop with a single array draw, and every seeded
race changes silently while every test that does not compare against a recorded race
still passes. `tests/env/test_engine_identity.py` holds both ends: the draw-order
recorder localises which site moved, the golden `.npz` fixtures prove no race did. The
fixtures were recorded before the extraction and regenerating them proves nothing.

**`state.ego` is an indexing convenience, not a privilege.** No engine function may
branch on it. The asymmetry lives in `rivals.draw_field`, which fills the ego's slot with
unit pace sigma and an infinite pit age — field construction, where it belongs.
`test_seat_symmetry` is the property test that keeps it there.

The two exceptions are deliberate and both belong to the twin: `TraceSource` recomputes
the ego's tyre failure from its own age, and `TraceSink` blanks the ego's pit and mode
out of the recording. That is what A-05 is for — freeze the field, vary the ego — so
the symmetry property is asserted on the live path only.

**Decisions reaching `advance_lap` must already be legal.** The engine does not mask,
snap or validate: hand it a slick in the wet and it will run the race faithfully. F-16's
"compliant by construction" is the *adapter's* guarantee — the learner goes through
`_coerce`/`_snap_pit`, rivals through `rivals.pit_choices`, both of which shop only
compounds the wetness allows. Any new caller of the engine owes the same guarantee before
it calls, and owes a test that says so. This is the one contract the seam cannot enforce
for you.

**A lineup rides the scenario, not the state.** `F1RaceEnv(..., drivers=[...])` resolves
`configs/drivers.yaml` into `scenario.lineup` at construction (`senna/env/lineup.py`), and
that is the only place driver identity lives. `RaceState` gained nothing and `EventTrace`
gained nothing — seat pace goes into the `driver_s` field both already had, and the
tyre-style multiplier is read off the scenario inside `lap_time_s`, which already takes it.
Three consequences worth knowing before you touch it:

- **`drivers=None` reads no table at all.** Same rule as `ablations.yaml`. The F16 golden
  replay builds from `tests/env/fixtures/pinned_configs/`, which has no `drivers.yaml` and
  never will, so a config loaded unconditionally in `build_scenario` takes the identity
  gate down with it.
- **`reset` draws every seat's offset and then overwrites the named ones.** Do not
  "optimise" the draw away for a named lineup. It is what keeps the variate stream
  identical to an unnamed race at the same seed, which is what makes the golden fixtures
  evidence for anything, and it is why an unnamed seat falls back for free.
- **A twin still owns `driver_s`.** In a replay the trace's offsets win, as they always
  have; only `deg_mult` comes from the lineup. `senna/eval/traces.py` fills the trace from
  the same table, so the two agree without either knowing about the other.

**No pandas anywhere reachable from the tick**, per `senna/CLAUDE.md`. The 5.6.2
throughput gate rests on it.

**Constants come from `configs/*.yaml`.** The event constants (hazard durations, weather
targets, cliff margins) are cached on the event source at construction. The pit-timing
constants — `pit.min_service_s`, `pit.lane_gap_s`, `pit_loss_mult`,
`forced_pit.tyre_failure_penalty_s` — are read off `scenario.env` inside
`engine._pit_times`, on stop laps only; that is measurably inside noise, but it is the
one place the extraction traded a cached attribute for a lookup. The reward and mask
constants stay on the adapter.
