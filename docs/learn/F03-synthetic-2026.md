# F03 — Synthetic 2026 generator (T1–T8)

## What we built and why

We do not have a 2026 season to learn from. We have a handful of real 2026 races and a
whole 2024 season of clean telemetry. F02 already turned that 2024 data into fitted
constants — pace, tyre wear, pit loss, energy integrals — in `configs/physics_params.yaml`.
F03 is the machine that ages those 2024 numbers forward into 2026 race dynamics for
every circuit, including ones the 2026 calendar has not reached yet.

The rule we set ourselves is that no neural network invents a lap. Every 2026 number is
the output of one of eight named transformations (T1–T8), each a formula built from a
sourced physics delta and fitted from real behaviour. T1 reprofiles the powertrain with
the 350 kW taper. T2 scales corner speed for the downforce cut. T3 shifts mass. T4 does
the energy accounting. T5 borrows tyre wear for circuits with no 2026 data (that lives in
F02's cluster transfer). T6 handles fuel. T7 refits overtaking. T8 measures whatever the
first seven leave on the table and writes it down as one honest per-circuit offset. The
whole battery writes `configs/transforms.yaml` and fills three energy scalars into
`physics_2026.yaml`.

Then it grades its own homework. We froze a train/test split before touching any of this:
calibrate on 2026 rounds 1–6, validate on rounds 7+ (E-14). A tiny Monte Carlo turns the
transformed constants into simulated lap-time and stint distributions, and F03 compares
those against the real held-out races it was never allowed to see. The honest headline:
the held-out lap-time distance misses its target, and F03 reports the miss with its cause
rather than hiding it. More on that at the end, because it is the most examinable thing in
the feature.

## New ideas in this feature

**Point-mass longitudinal model (a grey-box "effective car").** Instead of modelling
downforce, drag coefficient, air density and engine torque separately, we collapse the
car into a mass being pushed by an effective power `P` against an effective drag `beta`:
`m·a = P/v − beta·v²`. Those two numbers are fitted from what the 2024 car observably did,
so they silently absorb every physical constant we would otherwise have to guess. SENNA
uses this for T1 (5.4) precisely because it keeps grade-C aero numbers out of the
transform — the only sourced quantities are the 2026 deltas applied on top. Mental model:
you do not need to know a runner's exact muscle physiology to predict their next race from
their last one; you need their effective power output and their effective drag, and the
stopwatch gives you both.

**RK4 integration of an ODE.** The point-mass equation has no closed-form solution once
the taper kicks in, so we integrate it numerically. Fourth-order Runge-Kutta samples the
acceleration four times per step and combines them so the error per step is tiny (order
`step⁵`). We integrate over *distance*, not time, because a straight has a fixed length,
not a fixed duration. This is a step up from F02's trapezoidal integration: there we summed
known samples, here we solve for the trajectory itself.

**The frozen split and data leakage (E-14).** Out-of-sample validation only means
something if the model never saw the test set. Data leakage is any path — direct or
sneaky — by which held-out information reaches a fit; the classic symptom is a model that
scores beautifully in validation and falls apart in the real world. We froze rounds 1–6 as
calibration and rounds 7+ as validation on a recorded date, and we enforce the wall in
three layers of code. The point of a frozen split is that the validation number is a
genuine prediction, not a restatement of the fit.

**Distribution distances: KS and EMD.** We are not checking whether one predicted lap
matches one real lap. We are checking whether the *distribution* of simulated laps matches
the distribution of real laps. The Kolmogorov-Smirnov statistic is the largest vertical
gap between two cumulative distribution functions — one number in [0, 1], where 0 is
identical. Earth-mover distance (Wasserstein) is the minimum "work" to reshape one
histogram into the other; for stint lengths it comes out in laps, which is readable. KS is
strict about shape, EMD is forgiving about small shifts — together they say different true
things.

**Logistic regression by Newton-Raphson.** T7 predicts a probability — will this follower
pass? — from a pace delta and an era flag. Linear regression cannot output a probability,
so we fit a logistic curve by maximum likelihood, iterating Newton-Raphson steps until the
coefficients stop moving. Same hand-rolled-not-statsmodels convention as F02's fits. The
fitted `beta_pace` says how much a pace advantage helps; the `shift_2026` term says how
much harder passing got when DRS became the weaker Manual Override.

**A derived quantity versus a noisy regression.** The lift-and-coast cost `c_lc` could be
regressed off real race laps, but real laps are noisy and confounded. Instead we *derive*
it from the already-calibrated point-mass profile: sweep a set of lift depths, compute the
exact time cost and the exact harvest for each on the model, and take the slope. It is a
clean geometric quantity of the fitted car, not a scatter plot with error bars.

**Seeded Monte Carlo with stream spawning.** The validation sampler is stochastic, but
every random draw hangs off the seed passed in — no module-level RNG (5.5.5, kept even
here). `np.random.SeedSequence(seed).spawn(n_races)` hands each race its own independent,
reproducible stream, so a `make synth-figures` rerun produces byte-identical figures.

## The code, guided

The battery runs its stages in dependency order (`run.py:33`, `MODULES`): aero feeds
pointmass, pointmass feeds energy, then mass/fuel, overtaking, residual. I will walk them
in that order, then the split machinery, the Monte Carlo, and validation.

### segments.py — cutting a lap into phases

Both T1 and T2 need the lap broken into throttle, brake and coast phases.
`lap_phases` (`segments.py:27`) groups the telemetry by `trace_id` first — the F01 upstream
split that marks every gap over 2 seconds — so no phase ever spans a data dropout (AR-16).
Inside a trace it labels each sample, finds the label changes with
`np.flatnonzero(kind[1:] != kind[:-1]) + 1` (`segments.py:36`), and emits one `Phase` per
run. The distance comes from `np.trapezoid(span_v, span_t)` (`segments.py:53`): integrate
speed over time to get metres, the same trapezoid discipline as F02. A phase under two
samples is dropped — it has no duration and no distance (`segments.py:42`).

### aero.py — T2, the corner-speed exponent

Corner apex speed scales with downforce to some power. The spec's prior is the fourth root
(exponent 0.25), but we fit it. `fit_corner_exponent` (`aero.py:25`) takes matched
2024-vs-2026 apex pairs and does the fit in log space:

```python
ratios = np.log(v_2026 / v_2024)
exponent = float(np.mean(ratios) / np.log(downforce_ratio))
```

Each corner gives `log(v26/v24) = exponent · log(downforce_ratio)`; the mean of the
left-hand side over `log(downforce_ratio)` is the least-squares slope through the origin.
If the sample is thin (`< min_corners`, 30) or the answer lands outside the plausibility
bounds `[0.1, 0.6]`, the code falls back to the 0.25 prior and flags `fallback=True`
(`aero.py:34`, `aero.py:45`), which surfaces in `transforms.yaml` as stylised. On the real
data the fit held: **exponent 0.2239 over the corner sample** (`transforms.yaml:585`), a
touch below the fourth-root prior and earned, not assumed.

The subtlety is `matched_apexes` (`aero.py:59`). Telemetry rarely resolves the same corner
count in both eras, so a strict corner-by-corner match throws most circuits away. Instead
we sort each era's apexes fastest-first and pair up to the shorter list (`aero.py:75-77`).
For a *global* exponent regressed over many corners, the aggregate slope is what matters,
not any single pairing — fast corners match fast corners, and that is enough.

### pointmass.py — T1, the powertrain reprofile

This is the physics core. First the taper, which is the one 2026 fact the viva will check
(`pointmass.py:21`):

```python
def taper_kw(speed_kmh, *, mgu_k_max_kw, full_power_to_kmh, zero_power_at_kmh):
    fraction = (zero_power_at_kmh - speed) / (zero_power_at_kmh - full_power_to_kmh)
    return mgu_k_max_kw * np.clip(fraction, 0.0, 1.0)
```

The MGU-K delivers its full 350 kW up to 290 km/h, then ramps linearly to zero at 355
(AR-02). The `clip(0, 1)` holds it flat below 290 and dead above 355. Never 400 kW — that
is the ICE. The test pins the shape exactly: full power at 290, zero at 355, strictly
decreasing between, and 175 kW at the midpoint (`test_pointmass.py:78-89`).

`run_straight` (`pointmass.py:47`) integrates a full-throttle run. Its state is
`[time, speed, deployed_energy]` and it steps over distance. The gradient (`pointmass.py:65`):

```python
def gradient(state):
    v_ms = state[1]
    accel = (total_power_w(v_ms) / v_ms - beta_drag * v_ms * v_ms) / mass_kg
    return np.array([1.0 / v_ms, accel / v_ms, harvest_side_w(v_ms) / v_ms])
```

Line by line: `total_power_w / v` is force from power (P = F·v), minus `beta·v²` drag, over
mass — that is `a = F/m`. The three returned derivatives are with respect to distance, so
each is the time-derivative divided by `v` (because `d/dx = (1/v)·d/dt`). The third channel
integrates only the *MGU-K* side of the power (`harvest_side_w`, `pointmass.py:61`), because
`e_dep` is deployable electrical energy, not total energy (F-02). The RK4 loop
(`pointmass.py:72-77`) is textbook: four gradient samples per step, combined
`k1 + 2k2 + 2k3 + k4` over 6. The closed-form test proves the integrator is honest: with
drag zero and power flat, `v(t) = sqrt(v0² + 2Pt/m)` has an exact solution, and the
integrator reproduces `t_true` and `e_dep = 0.350·t` to 1e-3 (`test_pointmass.py:50-75`).

`fit_effective_car` (`pointmass.py:85`) is where the grey-box constants come from. It
collects full-throttle finite differences (`m·a = P/v − beta·v²`, linear in `P` and `beta`)
and brake-phase differences, and solves each by least squares (`pointmass.py:133`,
`pointmass.py:142`). Two disciplines matter. The finite-difference span never crosses a
phase edge or a `trace_id` boundary (`pointmass.py:116-121`) — a pair straddling a dropout
reads a fraction of the true acceleration, and the gap test proves splitting leaves the fit
unmoved to 1e-3 (`test_pointmass.py:106-120`). And the self-check: `_phase_time_error`
(`pointmass.py:163`) re-simulates every observed full-throttle phase and takes the median
relative error; if one `(P, beta)` cannot reproduce the lap within tolerance (5%), the car
is flagged `ok=False` and drops out of the transform rather than distorting it
(`pointmass.py:159`, `test_pointmass.py:123-138`). A lap the model cannot explain excludes
itself.

`_profile_2026` in `run.py:530` is where T1 and T2 actually recompose a 2026 lap. Corner
entry speeds are scaled by `downforce_ratio ** exponent` (`run.py:533`), drag is scaled to
the low-drag X-mode value (`beta · 0.45`, `run.py:534`), and each throttle phase is
re-run with 2026 power. The corner phases contribute a time change scaled by
`1/corner_speed_scale − 1` (`run.py:558`): slower corners cost time. The straight phases
run faster. `delta_lap_s` is the sum. And here is the honest tension baked into the model:
across almost every circuit `delta_lap_s` is negative (the 2026 laps come out 1–4 s
*faster*), because the drag-reduction straight-line gain outweighs the downforce corner
loss in this model. Hold that thought for T8 and validation.

### energy_budget.py — T4, four numbers per circuit

`energy_budget` (`energy_budget.py:33`) is the accounting. Harvest from super-clipping is
`super_clipping_kw · full_throttle_s` (`energy_budget.py:46`); total supply is braking plus
clipping harvest, capped at the per-event `h_max_mj` (`energy_budget.py:47`); the
`deficit_mj` is whatever `e_dep` exceeds supply (`energy_budget.py:54`), and that shortfall
is the straight-line derate the agent will have to manage. If `h_max_mj` is null the code
raises `NullConstantError` (`energy_budget.py:41`) — the cap must be sourced in
`circuits.yaml` (E-02), never guessed.

`c_lc_s_per_mj` (`energy_budget.py:58`) is the derived-quantity idea in code. For each lift
depth in a sweep it computes the flat-out time to `v_end` versus the lift-and-coast time
over the same distance, and the harvest gained (`energy_budget.py:80-89`). The cost is the
through-origin slope of extra-time against harvested-MJ:

```python
return float(np.sum(deltas * harvests) / np.sum(harvests * harvests))
```

That is a least-squares slope forced through zero — zero harvest must cost zero time. Real
`c_lc` values sit around 0.4–0.7 s/MJ on most circuits (`transforms.yaml:21`, `:237`), with
a couple of noisy outliers; the cross-circuit **median 0.423 s/MJ** is what gets mirrored
into `physics_2026.yaml:52` as `conserve_pace_cost_s_per_mj`.

### mass_fuel.py — T3 and T6

Short module, because mass reaches lap time through one door only. `static_mass_delta_s`
(`mass_fuel.py:18`) is `k_m · (car_delta + fuel_delta)` — the jointly-fitted mass
sensitivity times the total kilograms shed. The 2026 car is 30 kg lighter (AR-09) and runs
the ~70 kg allowance (AR-10, verified 16 July). Critically, T1 already integrates at a
fixed reference fuel load, so per-lap fuel mass never touches pace a second time (E-10). In
`run.py:261` the fuel delta is *half* the allowance change, because both eras burn to the
flag and the race-average load is half the tank. The result is a flat **−0.5357 s** mass
gain per circuit (`transforms.yaml:19`).

### overtaking.py — T7

`extract_pass_events` (`overtaking.py:36`) mines every "opportunity": a follower within
1.0 s at the line on a green lap. The exclusions are the interesting part
(`overtaking.py:118`): lap 1, non-green laps, restart laps, cars in a pit cycle, and passes
on a car about to retire — each counted, not silently dropped. One line is easy to miss and
load-bearing (`overtaking.py:76-77`):

```python
field_pace_s = ordered.groupby("lap_number")["lap_time_s"].transform("median")
lap_s = ordered["lap_time_s"].fillna(field_pace_s).fillna(ordered["lap_time_s"].median())
```

In/out and NaT laps carry null lap times (E-09). A plain cumsum would drop them and
understate every later lap's running clock, corrupting the gap between cars. So each null is
filled with the field's median pace on that lap before the cumulative sum — the clock stays
monotonic and the gaps stay meaningful.

`fit_overtaking` (`overtaking.py:187`) refuses held-out rounds first (`overtaking.py:188`),
then fits the logistic model `passed ~ 1 + pace_delta + is_2026` by Newton-Raphson
(`_fit_logistic`, `overtaking.py:199`). The real fit: **beta_pace ≈ 0.3727, a 2026 shift of
+0.1231 logit over 21,159 events** (`transforms.yaml:586-589`). Note the design choice
recorded in `frames.py:33`: sprints *enter* T7's extraction, because it is a
per-opportunity model — a shorter session just contributes fewer opportunities without
biasing anything. That is the opposite of the per-race hazard counts in F02, which exclude
sprints because uneven race lengths would skew a per-race rate.

### residual.py — T8

After T1–T7, whatever error is left gets absorbed into one interpretable number per
circuit. `fit_residual_s` (`residual.py:17`):

```python
return float(np.median(clean["lap_time_s"])) - model_median_s
```

`c_circuit` = real 2026 median lap time minus the model's implied median, over green
accurate calibration laps. Circuits with no 2026 data take the pooled `c_global`, the
median of the per-circuit values (`residual.py:29`). Two guards live here: it refuses
validation rounds (`residual.py:21`, `test_residual.py:8-14`), and the held-out error is
computed in `validate.py`, never here — a residual tuned on the validation set would
validate itself. The pooled **c_global came out ≈ 0.88 s** (`transforms.yaml:583`).

### frames.py and heldout.py — the E-14 wall in three layers

This is the leakage defence, and it is worth seeing all three layers because a viva examiner
will push on it.

Layer one, at the SQL door: `_held_in` (`frames.py:62`) adds
`(season < 2026) OR round IN calibration_rounds` to every calibration query, so held-out
rounds never load. Layer two, the shared runtime guard: `refuse_validation_rounds`
(`frames.py:17`) raises if any 2026 lap outside rounds 1–6 slips into a fitter, naming every
offending round. Layer three, the import boundary: `heldout.py` is the only module that
reads rounds 7+, and `test_frames.py:36` parses every other synth module's AST and asserts
none of them import it. It uses the parsed tree, not a substring grep, so a comment
mentioning `heldout.py` stays legal (`test_frames.py:40-54`). Three independent walls, so
no single forgotten check leaks the test set.

### montecarlo.py — the generator-level sampler

This is explicitly *not* the F05 environment (`montecarlo.py:2`): no agent, no rivals, no
masks. It is the smallest thing that turns constants into distributions. `plan_stints`
(`montecarlo.py:18`) picks a min-time 1- or 2-stop plan, skipping any choice that violates
the two-compound rule (`montecarlo.py:35`, F-20). `sample_races` (`montecarlo.py:73`) spawns
one RNG stream per race off the seed and builds each car's laps. The lap-time equation
(`montecarlo.py:115`) is the whole physics model assembled:

```python
lap_s = (t0_s + driver_s + offset_s
         + a * age ** b                      # tyre wear
         + k_m_s_per_kg * fuel_kg[i]         # fuel mass
         + evolution_s_per_lap * lap         # track rubbering in
         + noise_s[i])
```

Then SC/VSC laps are multiplied by their status factor, and pit out-laps add a pit-loss
draw (`montecarlo.py:124-127`). Every term traces to a fitted or transformed constant.

### validate.py — the 5.4.1 metrics

`ks_distance` (`validate.py:33`) builds both empirical CDFs on a shared grid with
`searchsorted` and returns the max gap. `stint_emd_laps` (`validate.py:43`) is
`scipy.stats.wasserstein_distance`. `run_validation` (`validate.py:58`) loads the held-out
races through `heldout`, samples a matched Monte Carlo per circuit, and writes
`docs/synth/validation_summary.yaml`. The stint EMD (`validate.py:170`) counts lengths at
the per-driver, per-stint grain on both sides — never pooling drivers into one bucket. The
`_pit_check` carries an honest caveat in its comment (`validate.py:186`): the simulated pit
loss is F02's *net* loss and the real number is OpenF1's *stationary* duration, so a
near-miss there is a definition gap, not necessarily a model error.

### run.py — the orchestrator

`run_battery` (`run.py:47`) runs the stages, and a narrowed run (`--only` or `--circuit`)
never writes the yaml (`run.py:82`) — a partial battery must not masquerade as the full
artifact, the same rule as F02. The precedence for a circuit's 2026 base pace is
real-beats-transform-beats-donor (`_put_base`, `run.py:390`): a real 2026 fit wins, else the
T1+T2+T3 transform, else a cluster donor's average delta, else the circuit is skipped
entirely rather than emitted half-built (`run.py:377-381`, E-13 spirit). `transforms.yaml`
is written byte-deterministically through F02's `render_params`, and the three energy
scalars are patched into `physics_2026.yaml` by key so reruns stay idempotent
(`run.py:470-494`).

## How it connects

```
 configs/physics_params.yaml (F02 fits)      FastF1 cache (2024 + 2026 telemetry)
        │                                            │
        └──────────────┬─────────────────────────────┘
                       ▼
        run.py battery:  T2 aero ─► T1 pointmass ─► T4 energy
                                        │
                         T3 mass ─ T7 overtake ─ T8 residual
                       │                                     │
      configs/transforms.yaml        physics_2026.yaml (c_lc, c_atk, p_der filled)
                       │
     validate.py ◄── heldout.py (rounds 7+, the ONLY reader)
                       ▼
     docs/synth/validation_summary.yaml + ECDF figures (Chapter 6)
                       │
        F05 (env) reads transforms.yaml + physics_2026.yaml
```

F03 is the third box of the spec 5.1 pipeline: fitted constants and telemetry in, one
transforms artifact plus a validation report out, consumed by F05.

## The honest result — teach this clearly

The held-out lap-time KS misses its 0.15 target, badly: **0.87 at Silverstone, 0.92 in
Austria** (`docs/synth/validation_summary.yaml`). The cause is right there in the same
file: `sim_minus_real_median_s` is about **−4 seconds** on both held-out circuits. The
point-mass T1/T2 transform predicts 2026 laps roughly 2–4 s *faster* than reality, because
in this model the drag-reduction straight-line speedup outweighs the downforce corner
slowdown. T8's pooled `c_global` (~0.88 s) only partly corrects circuits with no calibration
data, so the held-out laps stay too fast and the distributions do not overlap — hence a KS
near 1.

This is not a bug to bury. The spec explicitly permits "met, or the miss documented with
cause" (F03 Done-means), and E-14 forbids tuning on the held-out rounds to close the gap —
doing so would be exactly the leakage the frozen split exists to prevent. So the generator
reports its own sim-to-real error faithfully and names the mechanism. The follow-up is
real physics work: improve T1/T2's corner model (the downforce-to-grip mapping is almost
certainly too weak), not a fudge factor fitted on rounds 7+. A generator that honestly says
"I am 4 seconds optimistic and here is why" is worth more than one that quietly tunes itself
to look right.

## Try it yourself

`make synth` reads the ingested database and F02's yaml; narrowed runs never overwrite
`transforms.yaml`, so they are safe.

1. Read the artifact. Open `configs/transforms.yaml`, pick `australian_grand_prix`, and
   explain every block: why `base.source` is "real 2026 fit" while `abu_dhabi` is
   "transform (T1+T2+T3)", why `t3_mass_fuel` is identical across all circuits, and why its
   `t8_residual` is a large positive number while Abu Dhabi's is the pooled 0.8809. You'll
   know it worked when you can say which circuits had real 2026 races and which were
   extrapolated.

2. Break the taper. In `pointmass.taper_kw`, change `mgu_k_max_kw` handling so it never
   clips (drop the `np.clip`), and run `pytest tests/physics/synth/test_pointmass.py -q`.
   You'll know it worked when `test_taper_shape` fails on the "zero at 355" assertion —
   the exact regression the viva table warns about. Revert.

3. Break the split guard. In `frames.refuse_validation_rounds`, change the `~` to nothing
   (accept held-out rounds), and run `pytest tests/physics/synth/test_frames.py
   tests/physics/synth/test_residual.py -q`. You'll know it worked when both the frames
   split-guard test and the T8 leakage test fail. Revert.

4. Break the import boundary. Add `from senna.physics.synth import heldout` to the top of
   `residual.py` and run `pytest tests/physics/synth/test_frames.py::test_no_calibration_module_imports_heldout -q`.
   You'll know it worked when it fails naming `residual.py`. Revert — this is the AST wall.

5. Predict, then check: raise `configs/physics_2026.yaml`'s `aero.downforce_vs_2024` from
   0.70 toward 0.85 (less downforce cut) and reason about `corner_speed_exponent` and the
   sign of `delta_lap_s`. Prediction first: with more downforce retained, corners slow
   less, `delta_lap_s` gets less negative, and the −4 s optimism shrinks. You do not have to
   rerun the full battery — trace the arithmetic through `_profile_2026`. You'll know it
   worked when you can say whether this would move the held-out KS, and why touching it to
   *fix* the KS would still be forbidden.

## Check yourself

1. Why does T1 fit an "effective" power and drag rather than using sourced aero constants,
   and what does that buy the transform when applied to a circuit with no 2026 data?

2. The held-out KS is ~0.9, far above the 0.15 target. What is the mechanism, and why is it
   correct *not* to fix it by adjusting a constant on the held-out rounds?

3. Defend this design choice: T7 includes sprint sessions in its overtaking extraction, but
   F02's hazard rates exclude sprints. Why is the same data right for one and wrong for the
   other?

4. There are three separate mechanisms stopping held-out data from reaching a calibration
   fit. Name them and say why one is not enough.

5. `c_lc` is derived from the calibrated point-mass profile with a sweep, not regressed off
   real race laps. Give one reason the derived quantity is more trustworthy here.

---

### Answers

1. Sourced 2026 aero numbers (CdA, downforce) are grade-C guesses; folding them in would
   inject that uncertainty into every lap. The effective `P` and `beta` are fitted from the
   2024 car's own telemetry, so they absorb engine, density, drag and rolling resistance
   into two numbers we actually measured, and the only sourced inputs are the 2026 deltas
   applied on top. For a dataless circuit, an effective car fitted on its 2024 telemetry
   plus the same global deltas gives a defensible 2026 profile without any circuit-specific
   aero claim.

2. The point-mass model's drag-reduction straight-line gain outweighs its downforce corner
   loss, so it predicts 2026 laps ~4 s too fast; the simulated and real lap-time
   distributions barely overlap, driving KS toward 1. Fixing it by tuning a constant on
   rounds 7+ is train-test contamination (E-14) — the validation number would stop being an
   out-of-sample prediction and become a restatement of the fit. The honest fix is better
   T1/T2 corner physics, validated the same frozen way.

3. T7 is a per-opportunity model: it counts follower-within-1.0 s situations, so a shorter
   sprint simply contributes fewer opportunities and biases nothing. A per-race hazard rate
   divides events by races of unequal length, so mixing in short sprints would inflate or
   deflate the rate through exposure, not through any change in the underlying hazard. Same
   raw sessions, different denominator, different correctness.

4. (a) The SQL `_held_in` filter, so held-out rounds never load into a calibration query.
   (b) The runtime `refuse_validation_rounds` guard, which raises if one slips through, as a
   fitter's own defensive check. (c) The AST import-boundary test, which forbids any
   calibration module from even importing the held-out loaders. One is not enough because a
   single forgotten `.where` or a careless import would silently leak the test set; the
   layers are independent so no one omission defeats all three.

5. Real race laps are noisy and confounded — lift-and-coast happens tangled up with traffic,
   tyre state and fuel, so a regression would attribute other effects to `c_lc`. The sweep
   computes the exact time cost and exact harvest of lifting on the *already-calibrated*
   model, holding everything else fixed, so the slope is a clean geometric property of the
   car rather than a fit through scattered, contaminated points.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| Point-mass longitudinal model (effective car) | F03 | Car as mass under effective power and drag `m·a = P/v − beta·v²`, both fitted from telemetry so they absorb every unsourced physical constant (T1, 5.4). |
| RK4 ODE integration | F03 | Fourth-order Runge-Kutta solving the point-mass trajectory over distance; four gradient samples per step, error ~step⁵, validated against the flat-out closed form. |
| Frozen train/validation split and data leakage | F03 | Calibrate on 2026 rounds 1–6, validate on 7+ (E-14); leakage is any path by which held-out data reaches a fit, blocked here in three independent layers. |
| Distribution distances (KS, EMD) | F03 | KS is the max gap between two CDFs, EMD the work to reshape one histogram into another (laps for stints); the 5.4.1 sim-to-real metrics. |
| Logistic regression by Newton-Raphson | F03 | Maximum-likelihood fit of a probability model `P(pass) = sigmoid(design·beta)`, iterated to convergence by hand — T7's overtaking model. |
| Derived quantity vs noisy regression | F03 | Computing `c_lc` as an exact slope off the calibrated model (sweep lift depths) instead of regressing confounded race laps. |
| Seeded Monte Carlo with stream spawning | F03 | `SeedSequence(seed).spawn(n)` gives each simulated race an independent reproducible RNG, so validation figures regenerate byte-identically (5.5.5). |
</content>
</invoke>
