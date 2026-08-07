# senna/env/ — the race, and the adapter that lets an agent drive it

Since F16 this directory has two halves, and the split is the point.

**The race** is `engine.py` (the per-lap tick), `dynamics.py` (the formulas), `state.py`
(twenty-two cars as a struct of arrays), `events_io.py` (where a lap's events come from),
`pitlane.py` and `events.py`. None of it imports Gymnasium or stable-baselines3, and
`tests/env/test_engine.py::test_engine_imports_no_gym` fails the build if that changes.

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

**No pandas anywhere reachable from the tick**, per `senna/CLAUDE.md`. The 5.6.2
throughput gate rests on it.

**Constants come from `configs/*.yaml`.** The per-lap event constants (hazard durations,
cliff margins, pit service floors) live on the event source; the reward and mask
constants stay on the env. Neither reads a literal.
