# F17 plan — Driver identity

Approved by Saad, 13 August 2026, with both proposed defaults taken.
Spec: `docs/spec/features/F17-driver-identity.md`.

> Supersedes the plan approved on 9 August, which was aborted on 11 August when the
> data-integrity defect surfaced. F18 has since rewritten three of the four files that
> plan targeted. The list of what changed is at the end.

> F17 extends master spec v3.0 rather than implementing a row of it. Its spec anchors are
> contracts it must not break, not rows it delivers.

## Objective & spec anchors

Every car on the grid is currently the same driver with a different random number.
`race_env.py:162` draws `driver_s ~ N(0, sigma_driver_s)` at reset. `rivals.py:8-9`
deliberately gives archetypes no pace offset. `eval/traces.py:13` states the limitation
out loud and then calls `rng.normal` at `:94` while holding `laps_by_driver` keyed by real
driver codes, so M2's counterfactual harness knows which seat is Verstappen's and gives it
a coin flip.

The numbers that would fix that are already computed and already discarded.
`joint_pace.py:116` estimates a per-driver fixed effect in seconds per lap, `:128` folds
its mean into `t0_s`, and `:136` keeps only its standard deviation, which becomes the
`sigma_driver_s` the env draws from. F17 persists the effects instead of summarising them.

**Why this is shippable now and was not on 11 August.** The blocker was that driver
effects have to come from the same regression that produces the simulator's own constants.
Post-F18 they do, and the sample behind them is much larger. Era 2024 pools 2022–2025,
giving 31 drivers across 652 driver-by-circuit cells, median 93 clean slick laps per cell,
628 of the 652 above 30 laps. Era 2026 has 22 drivers over 235 cells on the calibration
rounds. That is enough to fit per-circuit effects rather than one number per driver.

Anchors, as invariants:

- **E-10** — the effects come out of the gated joint regression, so its identification
  discipline applies unchanged. F17 adds a sample-size gate at the driver level, which is
  the same idea one layer down.
- **E-14** — `_refuse_validation_rounds` stays in the path. Nothing is fitted on held-out
  2026 rounds.
- **T5** — `deg_mult` scales the fitted amplitude `a`. `tyre_deg_s` and `grip_est` keep
  their signatures and the power law keeps its form.
- **5.5.3** — one multiplication enters `lap_time_s`. The `eps ~ N(0, sigma_driver)` line
  of the spec pseudocode stays exactly as written on the default path.
- **M1** — `rivals.py:8-9` records that archetypes carry no pace offset because tying
  strategy style to car pace confounds the paired-position metric. Driver identity
  threatens precisely that, so the archetype draw stays independent of the driver table
  and a property test holds it there.
- **M2** — the feature's point.
- **M11** — luck share (0.786, CI [0.70, 0.86]) is measured against pace dispersion, so its
  reading shifts once dispersion is named rather than drawn. Flagged in the ship report,
  not renegotiated here.

**What the fitted number actually is, and the plan turns on this.** Era 2024 pools four
seasons in which a driver may have changed teams and every car changed. Session fixed
effects absorb per-session mean pace, so what survives in the driver coefficient is that
driver's offset within their own sessions: driver plus car, lap-weighted across the seasons
they raced. It is a seat effect, not a skill measurement. The config has to say so per
driver, with the seasons and the lap count sitting next to the value. That is the question
an examiner will ask about Verstappen's number, and "I measured the seat, and here is which
seat over which seasons" is the answer that survives it. The leaf is therefore named
`seat_pace_s` (decision 2 below).

## Deliverables

**Fitting side**

- **`senna/physics/fits/joint_pace.py`** — `JointPaceFit` gains `driver_effects_s:
  dict[str, float]` (centred), `driver_laps: dict[str, int]` and `driver_seasons:
  dict[str, tuple[int, ...]]`. `_effects` returns a bare array today and discards the
  level names; it must return them paired. `sigma_driver_s` stays untouched, because the
  fallback still needs it.
- **`senna/physics/fits/tyre_style.py`** — new. Per-driver multiplier on the pooled
  degradation amplitude, fitted per era across all circuits and compounds, with an
  identification gate. Returns the value, its standard error and `identified`.
- **`senna/physics/fits/run.py`** — a `tyre_style` stage after `degradation`; a `drivers()`
  tree builder beside `params()`; a `--drivers-out` CLI argument; the write goes through
  the existing `render_params` / `validate_complete` / `validate_origins` rather than a
  second emitter.
- **`configs/drivers.yaml`** — new generated artifact. The anti-black-box file for this
  feature.
- **`configs/fits.yaml`** — a `driver_identity:` block holding the three gates. Inputs live
  here, never outputs.
- **`notebooks/fit_driver_identity.ipynb`** — residual plots, the identification table, and
  the cells that size the gates.

**Simulator side**

- **`senna/env/lineup.py`** — new and small. Resolves a list of driver codes plus circuit
  and era into `pace_s` and `deg_mult` arrays, applying the fallback ladder and recording
  which level each seat used. One loader, so `traces.py` and `scenario.py` cannot disagree.
- **`senna/env/scenario.py`** — `build_scenario(circuit, era, *, drivers=None,
  configs_dir=None)`. `CircuitScenario` gains `driver_pace_s` and `driver_deg_mult`, both
  `None` when no lineup is named. `drivers.yaml` is read only when `drivers` is not None,
  for the pinned-configs reason below.
- **`senna/env/race_env.py`** — `F1RaceEnv(..., drivers=None)`, passed through to
  `build_scenario`. In `reset`, the normal draw runs exactly as today and named seats are
  then overwritten.
- **`senna/env/dynamics.py`** — `lap_time_s` multiplies `a` by `scenario.driver_deg_mult`
  when it is not None. No signature change, because `scenario` is already a parameter.
- **`senna/eval/traces.py`** — fill `driver_s` from the table via the `laps_by_driver` keys,
  and rewrite the docstring paragraph that currently apologises for not doing so.
- **`senna/eval/harness.py`** — pass `drivers=list(ordered)` to `F1RaceEnv` so the
  counterfactual gets `deg_mult` as well as pace.
- **Engine seam notes** — one paragraph: the lineup is scenario-borne, not state-borne,
  and why.

**Bookkeeping**

- **`tests/physics/fits/test_refit_reproduces_committed.py`** — extend the A-09 round-trip
  to `drivers.yaml`, and point it at a tmp path. Today it calls `run.main(["--params-out",
  tmp])`; without `--drivers-out` the same call would write over the committed
  `configs/drivers.yaml` during a test run.
- **`configs/eval.yaml`** — the `seeds_per_race: 5` comment says the seeds "vary only pit
  service and driver offsets". After F17 the driver offsets are fixed, so the comment
  becomes false and has to be corrected.
- **`docs/results/F14-evaluation.md`** and the INDEX decisions log — the re-measured M2,
  reported beside the old reading (decision 1 below).
- **`docs/freeze.md`** step 1 — name both files in the round-trip command.

## Constants & configs

`configs/drivers.yaml`, generated by `make fit`, never hand-edited. One entry per driver
per era. Era keys render unquoted and load back as ints, matching `physics_params.yaml` and
`scenario.py`'s `era_int`.

```yaml
drivers:
  VER:
    2024:
      seat_pace_s:
        bahrain_grand_prix: -0.412   # fitted: notebooks/fit_driver_identity.ipynb — 213 laps, 2022-2025
      seat_pace_mean_s: -0.388       # fitted — lap-weighted mean over fitted circuits (fallback level 2)
      deg_mult: 0.94                 # fitted — 41 stints, relative SE 0.08
      deg_mult_identified: true      # fitted
      deg_mult_se: 0.075             # fitted — the precision behind the claim
      n_laps: 2871                   # fitted
      seasons: [2022, 2023, 2024, 2025]  # fitted — which seasons produced this seat
```

| Name | Value | Origin | Home |
|---|---|---|---|
| `drivers.<CODE>.<era>.seat_pace_s.<circuit>` | fitted, centred | **fitted** — `notebooks/fit_driver_identity.ipynb` | `drivers.yaml` |
| `drivers.<CODE>.<era>.seat_pace_mean_s` | fitted | **fitted** | `drivers.yaml` |
| `drivers.<CODE>.<era>.deg_mult` | fitted where identified, else `1.0` | **fitted**, or **stylised** with `deg_mult_identified: false` | `drivers.yaml` |
| `drivers.<CODE>.<era>.deg_mult_se`, `.n_laps`, `.seasons` | fitted | **fitted** — the sample behind each claim | `drivers.yaml` |
| `driver_identity.min_laps_for_seat_pace` | **30** — mirrors `degradation.min_laps`; clears 628 of 652 era-2024 cells and 91 of 127 era-2026 ones, so it bites the thin cells without gutting coverage. Sized in the notebook. (The era-2026 figure read "190 of 235" when this plan was written, from a query that counted every 2026 session rather than the six calibration rounds the fit may see — corrected 13 Aug against the executed notebook.) | **stylised** | `configs/fits.yaml` |
| `driver_identity.min_stints_for_deg_mult` | **12** — the observed era-2024 minimum, a floor rather than a filter | **stylised** | `configs/fits.yaml` |
| `driver_identity.max_rel_se_for_deg_mult` | **0.25** proposed, sized in the notebook — the gate that actually bites | **stylised** | `configs/fits.yaml` |

`sigma_driver_s` stays in `physics_params.yaml` unchanged. It is still what an unnamed grid
draws from, and removing it would break the default path.

**No `fallback` entry with a null value.** The old spec proposed `drivers.fallback.pace_s:
null`. `validate_complete` refuses null leaves, so that entry would fail the writer's own
gate. The fallback is code behaviour, documented in the file header, not a constant.

**`drivers.yaml` is added to no fingerprint that does not read it.** `train/run.py:52`
carries the precedent: the ablation harness appends `ablations` for its own runs only, so
the headline's fingerprint cannot be broken by a later edit there. `drivers.yaml` gets the
same treatment — out of `CONFIG_FILES`, which would change `env_config_hash` for runs that
never read a lineup, and into `M2_CONFIG_FILES` and the M2 envelope, because M2 names a
lineup for every race and the hash has to identify what produced the number.

**Corrected 13 Aug 2026, during the build.** This section originally said "nothing is added
to any existing config fingerprint", and that was wrong the moment the three gates went into
`configs/fits.yaml` — which is itself the seventh entry of `CONFIG_FILES` and of
`bench/throughput.py`'s list. Measured across the diff, `train.CONFIG_FILES` moves
`5e3ddb15d584` to `b9eae725babd` and the bench list `2a1ee1f3a859` to `8507264a38b8`. The
first of those is the frozen headline's own version string, so it no longer recomputes from
the live configs. Nothing breaks and no test fails: `tests/eval/test_freeze.py` already
documents that recomputing the eleven-file fingerprint "would fail by design and prove
nothing", because the configs were legitimately comment-edited after training. But the claim
as written was false and a reader checking it would have found that out before I did.

### The two fits, stated precisely

**Seat pace.** The design matrix uses drop-one coding (`joint_pace.py:242`), so the effects
are relative to the alphabetically first driver, and `t0_s` at `:128` already absorbs
`driver_effects.mean()`. Persisting raw effects and assigning them to `driver_s` would
shift every lap time by that mean. The effects must be centred, `effect[d] -
mean(effects)`, so `t0_s` keeps its current meaning. The happy consequence: centred effects
have standard deviation equal to `sigma_driver_s` by construction, so a named lineup and
the random draw are distributionally matched. That is what keeps M1 from moving.

**Tyre style.** The partial residual for a lap is the joint fit's age contribution plus
noise, with the driver's mean pace already removed — `age_partial_residuals` subtracts the
full design, driver dummies included, then adds the age block back. So the multiplier
measures purely how a driver's lap time grows with tyre life relative to the pooled curve.
For each lap the predicted degradation is `a·t0·age^b` from that circuit-era-compound's
fit, which is exactly what `tyre_deg_s` computes. The multiplier is the least-squares slope
of residual on prediction, per driver, pooled across circuits and compounds:

    m_d = Σ(r·d̂) / Σ(d̂²),   se(m_d) = σ̂ / √Σ(d̂²)

Closed form, one parameter per driver, and it handles circuits having different `a` and `b`,
which an `age × driver` interaction on raw age would not.

The multipliers are then **normalised so their lap-weighted mean is exactly 1.0**, for the
same reason the pace effects are centred: the pooled `a` was fitted on all drivers, so
without normalisation naming a lineup would systematically shift tyre life for the whole
field.

The gate is precision, not count. Counts do not bite here — every driver has at least 12
stints in era 2024 and 21 in era 2026, median 132 and 29 — so a count-only gate would be
theatre. The relative standard error is the honest analogue of E-10's VIF: it asks whether
the design pinned the number down, not whether there were rows.

The same seat caveat applies to `deg_mult`. Tyre usage is dominated by the car's
aerodynamics and suspension, so this is a seat effect too, and the yaml header says so.

## Tests first

*Identity — the gate, not a formality*

- **`tests/env/test_engine_identity.py`** (existing, re-run) — the F16 golden fixtures
  replay byte-identical with `drivers=None`. Inherited wholesale. Because F18 pinned the
  fixture's world to `tests/env/fixtures/pinned_configs/`, this now proves the default path
  did not move without being sensitive to the new config file, provided `build_scenario`
  does not try to load `drivers.yaml` from that directory. Which is the next test.
- **`test_a_default_scenario_never_reads_the_driver_table`** — build a scenario from a
  configs dir with no `drivers.yaml` and assert it succeeds. The pinned-configs README
  warns about exactly this failure mode for `ablations.yaml`; this makes the warning
  executable.
- **`test_a_named_lineup_consumes_the_same_variates`** — the draw count and every non-pace
  variate are identical between `drivers=None` and `drivers=[...]` at the same seed.

*The two centring guards — the silently-wrong failures*

- **`test_driver_effects_are_centred`** — the persisted effects sum to zero across the
  fitted lineup and their standard deviation equals the same fit's `sigma_driver_s`.
  Nothing else in the suite would notice a constant pace shift.
- **`test_deg_multipliers_are_normalised`** — the lap-weighted mean of the multipliers is
  1.0, so a named grid cannot change the field's overall tyre life.

*Behaviour*

- **`test_a_named_lineup_seeds_the_fitted_offsets`** — `state.driver_s` equals the table's
  values in seat order.
- **`test_an_unnamed_seat_falls_back_to_the_draw`** — a short lineup, or a code absent from
  the table, leaves those seats at their drawn `N(0, sigma_driver_s)` value. Not zero: zero
  would quietly make an unknown driver the best on the grid.
- **`test_a_thin_circuit_falls_back_to_the_driver_mean`** — a driver below
  `min_laps_for_seat_pace` at one circuit takes their mean over fitted circuits, and the
  resolved level is reported.
- **`test_a_faster_driver_finishes_ahead_on_equal_strategy`** — two seats, identical
  decisions every lap, differing only in seat pace; the faster one classifies ahead. The
  end-to-end statement that identity reaches the result.
- **`test_tyre_management_lengthens_the_useful_stint`** — *property test.* Lap-time delta at
  a given age is monotone in `deg_mult` over a bounded range. Direction, not magnitude.
- **`test_archetype_assignment_is_independent_of_driver_identity`** — *property test.* Over
  many seeds, the distribution of archetypes assigned to a given driver code is uniform.
  The M1 guard, and the test least obvious to a reader in six months.
- **`test_deg_multiplier_falls_back_when_unidentified`** — above the relative-SE gate, `1.0`
  and `deg_mult_identified: false`, never a noisy fitted value wearing a `fitted` tag.
- **`tests/eval/test_traces.py::test_real_race_traces_carry_the_real_driver`** —
  `trace_from_real_race` with VER/HAM/LEC keys produces `driver_s` matching the table for
  those codes, in that seat order.

*Provenance*

- **`test_every_driver_constant_declares_its_origin`** — `validate_origins` over the built
  driver tree. Structural rather than a comment parser, because the tree is
  `(value, origin)` pairs before it is text.
- **`test_drivers_yaml_renders_byte_deterministically`** — a rerun leaves `git diff` empty,
  matching `params_writer`'s existing guarantee.
- **`test_refit_reproduces_the_committed_drivers`** — *slow*, needs the ingested store. The
  A-09 claim extended to the new file.

## Edge cases handled

- **E-10** — effects come from the gated regression; no new attribution is invented, and
  the driver-level gate is the same discipline one layer down.
- **E-14** — `_refuse_validation_rounds` stays in the path; the era-2026 table is fitted on
  calibration rounds 1–6 only.
- **T5** — multiplier on `a`, applied at `tyre_deg_s`'s call site. Form unchanged,
  signatures unchanged.
- **A-05** — `EventTrace` needs no schema change. Pace rides the existing `driver_s` field
  and `deg_mult` lives on the scenario, so saved traces under `models/*/stage_b_traces/`
  keep loading. In a twin replay the trace's `driver_s` wins, as it does today, and
  `deg_mult` comes from the lineup if one is named.
- **E-06** — the archetype draw stays independent of the driver table, by construction and
  by property test.
- **E-09** — a driver whose laps were all dropped for missing tyre age simply has no entry
  and falls back to the draw.
- **Solo mode (F07 Stage A)** — a one-car grid takes its named driver's seat, or today's
  draw.
- **Three-level fallback ladder** — per-circuit fitted where the cell clears the lap gate;
  that driver's lap-weighted mean across fitted circuits where it does not; the random draw
  where the driver is unknown to the era. Each seat's resolved level is recorded so a
  reader can tell which applied.

**The observation does not change.** Observation feature #10 (`tyre_grip_est`,
`observation.py:43`) keeps reading the pooled `scenario.deg_a`, as do `heuristic.py:92` and
`oracle.py`. That is deliberate. F20 owns observation changes, and batching them is what
makes F20 a retrain. It also reads correctly as physics: the agent's model of the tyre is
the engineer's model, and a driver's realised wear differing from it is what `deg_mult`
represents. Documented in the module note rather than left for a reader to notice.

## Acceptance checklist

- [ ] `configs/drivers.yaml` generated by `make fit`, every leaf origin-tagged, renders byte-deterministically
- [ ] `joint_pace` persists centred per-driver effects with their lap counts and seasons; `sigma_driver_s` still produced
- [ ] `tyre_style` multipliers normalised to a lap-weighted mean of 1.0, gated on relative standard error
- [ ] `F1RaceEnv(..., drivers=[...])` seeds `driver_s` from the table and applies `deg_mult`
- [ ] `drivers=None` replays F16's golden fixtures byte-identical, and a configs dir without `drivers.yaml` still builds a scenario
- [ ] F14's M1/M3/M5/M10 payloads unchanged on the default path (F16's worktree-diff method)
- [ ] `eval/traces.py` puts the real driver's fitted seat pace in the real driver's seat; its docstring no longer says skill is not modelled
- [ ] The archetype-independence property test passes
- [ ] `--drivers-out` exists and the slow round-trip test writes to tmp, not over the committed file
- [ ] A named driver's per-circuit number is traceable from the config comment to the notebook cell, and its `seasons` list says which seat it measures
- [ ] M2 re-measured, old and new readings reported side by side
- [ ] Cold-cache `ruff` over the whole repo; `make test` with both `DATABASE_URL` and `REDIS_URL` exported

## Out of scope

- **Aggressive overtaking.** There is no on-track pass event in the engine: classification
  is cumulative race time, and T7's `P(pass)` lives in `senna/physics/synth/overtaking.py`,
  which `senna/env` never imports. Giving a driver better overtaking means first giving the
  engine overtaking, which changes every race and is its own feature.
- **Late braking.** No braking term in 5.5.3 to attach it to.
- **Per-driver degradation curves.** `degradation.py` refuses a fit below `min_drivers` for
  a real statistical reason. F17 fits a multiplier on the pooled curve, which is estimable.
- **Wet skill.** Dropped on 9 August and still dropped. There is not enough per-driver wet
  running in the calibration split, so it would ship `stylised`: an invented number about a
  named real person, in the file whose whole purpose is answering "how do you know that?".
- **A default 2026 lineup.** Lineups stay opt-in. Era-2026 seat effects are fitted from real
  ingested 2026 rounds, so this is no longer about fabricating data; it is about not
  asserting a grid.
- **Any observation change, and any retrain** (F20). Training and F14's default path use
  `drivers=None`.
- **A CLI or UI entry point for named lineups.** The live users are the M2 harness and the
  notebook.
- **Teams and teammate effects** (F22), **physics uncertainty** (F19).

## Decisions (Saad, 13 August 2026)

**1. M2 switches to fitted seat pace, and the chapter is re-measured.** `eval/traces.py`
fills `driver_s` from the table, the M2 leg is re-run, and the report carries the old
reading (1W/8L/1T, p=0.039, mean −3.66) beside the new one. The pre-registered alpha stays
at 0.05, and the write-up states that the direction of the move was unknown before the
roll — that is the honest framing, and it is a claim the repo can support because the plan
saying so is committed before the number exists.

The mechanism, for the write-up: the seat offset largely cancels inside the pair, because
both legs share the trace's `driver_s` and the counterfactualled driver is car 0 in both.
What moves is field context. Giving the real grid its real pace changes where car 0 sits
among the rivals, and therefore changes the strategic problem the agent is solving.

**2. The leaf is `seat_pace_s`, not `pace_s`.** `drivers.VER.pace_s` invites "so you
measured Verstappen's skill?", and the answer is no: era 2024 pools four seasons of
whatever car he was in. `seat_pace_s` makes the file state its own limitation in the key,
before anyone reads the comment.

## Notes for the build

**The RNG hazard is the one F16 taught.** `driver_s = self._rng.normal(0.0,
sigma_driver_s, n)` sits in `reset()` between the grid permutation and the rival field
draw. Delete that call and every seeded race in the repo changes: the frozen model's
evaluation, the Stage B traces, F14. Keep the draw unconditional and overwrite named seats
afterwards. That makes the default path byte-identical by construction, makes the
unnamed-seat fallback free, and lets a named race share every other variate with the
same-seed unnamed race.

**Centre the effects and normalise the multipliers before persisting them.** These are the
two changes that are silently wrong rather than loudly wrong, and each has a test above
whose only job is to catch it.

**Reuse `params_writer`, do not write a second emitter.** Every leaf of
`physics_params.yaml` is a `(value, origin)` pair rendered with its origin as a trailing
comment, sorted and byte-deterministic. `drivers.yaml` is the same shape with a different
header, and `render_params` already takes `header=`.

**Watch the two files F18 left loaded.** `tests/env/fixtures/pinned_configs/` will raise
`FileNotFoundError` if `build_scenario` loads `drivers.yaml` unconditionally, and
`test_refit_reproduces_committed.py` will overwrite the committed `drivers.yaml` if the
battery has no `--drivers-out`. Both are cheap to get right up front and expensive to
debug later.

**This feature's risk is provenance, not physics.** The code is small: one multiplication
in `lap_time_s`, one overwrite in `reset`, one dict persisted instead of averaged. What is
large is a config file of per-driver numbers an examiner will read as claims about real
people. Every one needs to survive "how do you know that?", and the honest answers include
"I don't, so it is 1.0".

## Sizing corrections during the build (13 August 2026)

The plan deferred both gate values to the notebook. Doing that sizing first changed one
line of code as well as one constant, so it is recorded here rather than only in the
notebook.

**The standard error is clustered by stint.** Degradation residuals are correlated within a
stint — a set that runs hot is slow for its whole life — so a lap-level error bar counts a
stint's laps as that many independent observations. On the era-2024 fit it runs 2.3x small
at the median, which is enough to walk a thin driver through any precision gate. The cluster
key is `(session_id, stint)`; stint numbers restart every session, so either field alone
under-clusters.

**`max_rel_se_for_deg_mult` is 0.10, not the 0.25 the plan proposed.** Sized against the
committed `(a, b)` distribution rather than an invented curve: a driver with the era-2024
median 132 stints lands at relative standard error p90 0.019–0.051, an era-2026 median
29-stint driver at 0.053–0.109, and a 12-stint driver at 0.084–0.220. 0.25 admitted every
row including the thinnest. On the real fit 0.10 identifies 31 of 31 era-2024 drivers and
15 of 22 in era 2026, which is the gate doing its job where the data is thin rather than
manufacturing refusals where it is not.

**A denominator guard the plan did not anticipate.** 26% of the 145 committed degradation
curves sit at exactly `a = 0`, where the fitter hit its lower bound on a flat residual
cloud, and 41% are below 1e-4. A driver whose whole sample came from those has no
degradation to be relatively fast or slow at, so the estimator's denominator is zero. That
reads as unidentified rather than as a division returning an infinity.

## What changed since the 9 August plan

1. **`validate_origins` already exists.** F18 added it at `params_writer.py:53` and
   `run.py` already calls it. That deliverable is done; F17 reuses it.
2. **The pinned-configs hazard is new.** F18 created `tests/env/fixtures/pinned_configs/`,
   whose README warns that a config `build_scenario` loads unconditionally but which is
   absent there will raise `FileNotFoundError`. `drivers.yaml` must follow the
   `ablations.yaml` precedent. The old plan would have broken the F16 golden fixture.
3. **The A-09 round-trip test would have overwritten the committed file.**
   `test_refit_reproduces_committed.py` is new in F18 and calls `run.main(["--params-out",
   tmp])`. Hence `--drivers-out`.
4. **`deg_mult` moved from `RaceState` to `CircuitScenario`.** No state field, no trace
   field, no `lap_time_s` signature change, because `scenario` is already a parameter.
   Smaller diff and a stronger identity story.
5. **The tyre-style fit is specified differently.** The old plan said "an `age × driver`
   interaction", which ignores that `a` and `b` vary by circuit and compound. Regressing
   the partial residual on the predicted degradation gives one estimable parameter per
   driver that pools correctly across circuits.
6. **The gate is precision, not count.** The old plan's `min_stints_for_deg_mult: 6` would
   pass every driver in the store: the observed minimum is 12 and the median 132.
7. **Normalisation of the multipliers is new**, and it is the same class of silent bug as
   the pace centring the old plan caught.
8. **The draw is now always consumed.** The old plan's
   `test_a_named_lineup_seeds_the_fitted_offsets` asserted that no `rng.normal` for driver
   pace is consumed. Drawing anyway and overwriting is better on three counts, so that
   test's assertion changes and a variate-count test joins it.
9. **`seat_pace_s` and the seat-not-skill framing** are new, and they follow directly from
   F18 pooling 2022–2025.
10. **The `fallback: null` entry is dropped**, because it would fail `validate_complete`.
