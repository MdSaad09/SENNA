# F17 — Driver identity

Depends on: F02, F16 (both Done)
Spec anchors: 5.5.3, E-10, T5, M1, M2, M11

> **Extends master spec v3.0 rather than implementing a row of it**, like F16. The
> anchors are contracts F17 must not break: the lap-time model of 5.5.3, the joint
> regression of E-10, the degradation form of T5, and the three metrics whose meaning
> depends on where pace dispersion comes from (M1, M2, M11). The spec-auditor should read
> them as invariants and expect a new config file with per-driver provenance.

## Goal
Right now every car on the grid is the same driver with a different random number.
`driver_s` is drawn from `N(0, sigma_driver_s)` at reset (`race_env.py`), the archetypes
deliberately carry no pace offset (`rivals.py:8-9`), and `senna/eval/traces.py:13` states
the limitation out loud: *"Driver pace offsets are drawn, not fitted, because per-driver
skill is deliberately not modelled."* That module is handed `laps_by_driver` keyed by real
driver codes and still fills `driver_s` with `rng.normal` (`:94`) — it knows Verstappen is
in seat 0 and gives him a coin flip.

The numbers to fix that already exist and are already thrown away. `joint_pace.py:102`
estimates a per-driver fixed effect in seconds per lap; `:114` collapses the whole vector
to its mean and `:122` keeps only its standard deviation, which is the `sigma_driver_s`
the env then draws from. F17 persists the effects instead of summarising them, and gives
`CircuitScenario` a driver dimension so a race can be run as *this* grid rather than *a*
grid.

After F17, "Verstappen at Bahrain" is a thing SENNA can simulate, M2's counterfactuals
put the real driver's fitted pace in the real driver's seat, and drivers differ in how
they use a tyre rather than only in how fast they are.

## Deliverables
- `configs/drivers.yaml` — the per-driver table, one entry per driver code, every number carrying its provenance tag. The anti-black-box artifact for this feature.
- `senna/physics/fits/joint_pace.py` — stop discarding the driver effects: `JointPaceFit` gains `driver_effects_s: dict[str, float]` alongside the existing `sigma_driver_s`, which stays (the fallback still needs it).
- `senna/physics/fits/tyre_style.py` — new. Estimate a per-driver multiplier on the pooled degradation amplitude from the F02 partial residuals, with an identification gate in the style of `joint_pace`'s VIF check: report the multiplier only where the driver has enough stints to separate it from noise, and fall back to 1.0 with `identified=False` otherwise.
- `senna/physics/fits/run.py` — write `configs/drivers.yaml` from both fits.
- `senna/env/scenario.py` — `build_scenario(circuit, era, *, drivers=None)`; `CircuitScenario` gains `driver_pace_s` and `driver_deg_mult`, both `None` when no lineup is named.
- `senna/env/race_env.py` — `F1RaceEnv(..., drivers=None)`. With a lineup, `driver_s` is read from the table instead of drawn; without one, the existing draw is untouched.
- `senna/env/dynamics.py` — `lap_time_s` takes a per-car `deg_mult` array defaulting to ones. One multiplication against the fitted amplitude; no change to the form of T5.
- `senna/physics/fits/params_writer.py` — `validate_origins` beside `validate_complete`, so an untagged constant raises rather than relying on review to catch it.
- `senna/eval/traces.py` — fill `driver_s` from the table using the `laps_by_driver` keys, and rewrite the docstring paragraph that currently apologises for not doing so.
- `notebooks/fit_driver_identity.ipynb` — the residual plots and the identification table, per the repo's fitted-artifact convention.
- Tests per the list below.

## Out of scope
- **Aggressive overtaking.** There is no on-track pass event in the engine: classification is cumulative race time, and the T7 `P(pass | pace delta, override)` model lives in `senna/physics/synth/overtaking.py`, which generates data and is never imported by `senna/env`. Giving a driver a better chance of completing a pass means first giving the engine passes, which changes every race and is its own feature. F16 made it possible; it is not this.
- **Late braking.** No braking or cornering term exists in 5.5.3 to attach it to. Modelling it would mean inventing physics the data cannot check.
- **Per-driver degradation *curves*.** `degradation.py:61` refuses a fit below `min_drivers` for a real statistical reason — one driver's stints cannot identify a power law. F17 fits a per-driver *multiplier* on the pooled curve, which is estimable, and says so.
- **Wet skill.** Dropped on Saad's decision, 9 Aug 2026. There is not enough per-driver wet running in the calibration split to fit a multiplier, so it would have shipped `stylised` — an invented number about a named real person, in the file whose whole purpose is answering "how do you know that?". Two honest parameters beat three with one fabricated. It returns when data supports it, or not at all.
- **A default 2026 lineup.** Dropped on the same decision. Naming who drives for Cadillac next season is a claim the calibration data cannot support. `drivers=None` stays the random draw and remains what training and F14 use; lineups are opt-in and come from ingested data, which makes "Verstappen at Bahrain" a real 2024 race with the real grid rather than a guess.
- Team structure and teammate effects (F22), physics uncertainty (F18), any observation change (F20).

## Constants & configs
Every number lands in `configs/drivers.yaml`. The tags are not decoration — the viva
question is "where did Verstappen's number come from", and the file must answer it per
driver, per parameter.

| Name | Origin | Note |
|---|---|---|
| `drivers.<CODE>.pace_s.<circuit>` | **fitted** — `notebooks/fit_driver_identity.ipynb`, from `joint_pace` driver fixed effects | seconds per lap relative to the session mean; the quantity `sigma_driver_s` is currently the standard deviation of |
| `drivers.<CODE>.deg_mult` | **fitted** where identified, else **stylised** 1.0 with `identified: false` | multiplier on the pooled compound amplitude `a` |
| `drivers.fallback.pace_s` | **operational** — `null`, meaning "draw from `sigma_driver_s`" | an unnamed seat keeps today's behaviour rather than silently becoming average |
| `min_stints_for_deg_mult` | **operational**, sized in the notebook | the identification gate, mirroring `degradation.py`'s `min_drivers` |

`sigma_driver_s` stays in `physics_params.yaml` unchanged. It is still the right thing to
draw from for an unnamed grid, and removing it would break the default path.

## Tests first
- **`test_the_default_grid_is_byte_identical`** — the F16 golden fixtures still replay exactly with `drivers=None`. F17 inherits F16's identity harness wholesale, which is the cheapest possible guarantee that the frozen model and F14's numbers are untouched. This test is the gate, not a formality.
- **`test_driver_effects_are_centred`** — the persisted effects sum to zero across the fitted lineup and their standard deviation equals the same fit's `sigma_driver_s`. The regression uses drop-one coding and `t0_s` already absorbs the effects' mean, so persisting them raw would shift every lap time by a constant. Nothing else in the suite would notice.
- **`test_a_named_lineup_seeds_the_fitted_offsets`** — with a lineup, `state.driver_s` equals the table's values in seat order, and no `rng.normal` for driver pace is consumed.
- **`test_an_unnamed_seat_falls_back_to_the_draw`** — a lineup shorter than the grid, or carrying a code absent from the table, fills the remaining seats from `N(0, sigma_driver_s)` rather than zero. Zero would quietly make an unknown driver the best on the grid.
- **`test_a_faster_driver_finishes_ahead_on_equal_strategy`** — two seats, identical decisions every lap, differing only in `pace_s`; the faster one classifies ahead. The end-to-end statement that identity reaches the result.
- **`test_tyre_management_lengthens_the_useful_stint`** (property) — for `deg_mult` in a bounded range, lap-time delta at a given age is monotone in the multiplier. Pins direction, not magnitude.
- **`test_archetype_assignment_is_independent_of_driver_identity`** (property) — over many seeds, the distribution of archetypes assigned to a given driver code is uniform. This is the M1 guard (below) and the test that will be least obvious to a reader in six months.
- **`test_real_race_traces_carry_the_real_driver`** — `trace_from_real_race` with `laps_by_driver` keyed VER/HAM/LEC produces `driver_s` matching the table for those codes, in that seat order.
- **`test_the_driver_table_declares_provenance`** — every numeric leaf in `drivers.yaml` has a `fitted`/`stylised`/`sourced`/`operational` tag. The interpretability contract, enforced rather than trusted; the spec-auditor should not be the only thing standing between this file and an undocumented number.
- **`test_deg_multiplier_falls_back_when_unidentified`** — a driver below `min_stints_for_deg_mult` gets 1.0 and `identified: false`, not a noisy fitted value.

## Edge cases handled
- **E-10 identification** — the driver effects come out of the same regression whose fuel/evolution attribution is already gated on VIF. Persisting a coefficient the fit could not identify is the same error in a new place; the gate is reused, not reinvented.
- **T5 form unchanged** — `deg_mult` scales the fitted amplitude `a`; it does not add a term or change the power law. `grip_est` and `tyre_deg_s` keep their signatures.
- **E-14 frozen split** — driver effects are fitted on the calibration rounds only. `_refuse_validation_rounds` already guards this and must stay in the path.
- **A-05 twin** — `EventTrace` needs **no schema change**: it already carries `driver_s`, so a named lineup simply puts different values in an existing field. Saved traces under `models/*/stage_b_traces/` keep loading.
- **Solo mode** — a one-car grid with a named driver takes that driver's pace; with none, today's draw.

## Done means
- [ ] `configs/drivers.yaml` exists, every numeric leaf tagged, generated by `make fit`
- [ ] `joint_pace` persists per-driver effects; `sigma_driver_s` still produced for the fallback
- [ ] `F1RaceEnv(..., drivers=[...])` seeds `driver_s` from the table
- [ ] `drivers=None` replays the F16 golden fixtures byte-identical
- [ ] F14's M1/M3/M5/M10 payloads unchanged on the default path (the F16 worktree-diff method)
- [ ] `eval/traces.py` puts the real driver's fitted pace in the real driver's seat, and its docstring no longer says skill is not modelled
- [ ] A named driver's per-circuit pace is traceable from the config comment to the notebook cell that produced it
- [ ] The archetype-independence property test passes
- [ ] Cold-cache `ruff` over the whole repo

## Notes for the plan session

**The RNG hazard, again, and it is the same one.** `driver_s = self._rng.normal(0.0, sigma_driver_s, n)`
sits in `reset()` between the grid permutation and the rival field draw. Delete that call
and every seeded race in the repo changes — the frozen model's evaluation, the Stage B
traces, F14. The `drivers=None` default must consume the stream exactly as it does today;
a named lineup is a different mode and may legitimately shift it, in the same way
`weather="dry"` already skips the weather roll. F16's golden fixtures are the instrument
for proving the default path did not move, and they cost nothing to reuse.

**The M1 confound is a real design constraint, not a style note.** `rivals.py:8-9` records
a deliberate choice: archetypes carry no mean pace offset, because tying strategy style to
car pace would confound the paired-baseline metric. Driver identity threatens exactly that
if a fast driver is also systematically an undercutter. Keep the archetype draw
independent of the driver table, and let the property test say so. If a later feature
wants "Verstappen is aggressive *and* fast", it has to argue with M1 first.

**Fit the tyre multiplier honestly or label it.** The estimable quantity is a per-driver
multiplicative factor on the pooled amplitude, from an `age × driver` interaction in the
partial residuals. Where a driver has too few stints, report 1.0 and mark it
unidentified — do not let a noisy coefficient into `drivers.yaml` wearing a `fitted` tag.
The wet multiplier almost certainly cannot be fitted from the calibration split at all; if
so it ships `stylised` with the reasoning written down, which is a defensible answer and a
fabricated number is not.

**This feature's risk is provenance, not physics.** The code changes are small — two
multiplications in `lap_time_s`, one lookup in `reset`, one dict persisted instead of
averaged. What is large is a config file full of per-driver numbers that an examiner will
read as claims about real people. Every one of them needs to survive the question "how do
you know that?", and the honest answers include "I don't, so it is 1.0".
