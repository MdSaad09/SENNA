# F02 — Physics model fits

## What we built and why

The simulator that F05 builds will claim things like "a Monaco pit stop costs 23
seconds" and "a hard tyre loses grip as `1 - a*age^b`". F02 is where every one of
those numbers is earned: a fitting battery reads the F01 database, estimates each
constant from real races, and writes them all to `configs/physics_params.yaml` with a
comment on every line naming the notebook that produced it. This file is the
interpretability contract for the physics layer — when an examiner points at any
number in the simulator, the answer is one `grep` away.

Five fits run in dependency order. A joint pace regression separates fuel burn from
track evolution (E-10) and hands its leftovers to the tyre degradation fit (E-09, T5
groundwork). Track-status digits become safety-car, virtual-safety-car and red-flag
rates per circuit, with honest uncertainty bands. OpenF1 pit durations become the
mean and spread the E-05 pit-queue model needs. Telemetry integrals estimate braking
energy and full-throttle time per lap (F-13, AR-16). Finally, circuits the 2026
season has not visited yet borrow tyre coefficients from statistically similar
circuits, flagged as borrowed forever (T5).

The story of this feature is mostly the story of things refusing to work quietly. A
clean race turned out to be mathematically incapable of telling fuel apart from track
evolution, so the code had to learn to say "I don't know" out loud. Pooling the weak
estimates anyway produced a car that got *faster* as it got heavier — a diagnostic,
not a bug, and it set the pooling rule. A circuit with one race and one safety car
briefly claimed a safety car every single lap. And `repr(7e-06)` has no decimal
point, which YAML 1.1 reads as a string, which crashed a mean over degradation
coefficients two modules later. Each of these is now a pinned test.

## New ideas in this feature

**OLS with fixed effects (dummy variables).** Ordinary least squares finds the
coefficient vector that makes `design_matrix @ coef` closest to the observed lap
times. A fixed effect is a 0/1 column per category level — one per driver, session
and compound — so each driver gets their own baseline and the interesting
coefficients (fuel, evolution) are estimated *within* driver, not confused by Max
being faster than everyone. One level per category is dropped (the baseline),
otherwise the dummy columns sum to the intercept column and the matrix is singular.
SENNA needs this because E-10 demands one joint fit; the fixed effects are what let
races, drivers and compounds share it without contaminating the slopes. Smallest
example: with two drivers, the column `[0,0,1,1]` says rows 3 and 4 belong to driver
B, and its coefficient is "how much slower B is than A".

**Collinearity, VIF and condition number.** Two regressors are collinear when one is
nearly a linear function of the other; OLS then has no way to split credit between
them and the coefficients swing wildly. The variance inflation factor of a column is
`1/(1-R²)` from regressing that column on all the others — VIF 1 means independent,
VIF 30 means 97% of the column is explained by its neighbours. The condition number
is the same worry for the whole matrix at once. F02 computes both by hand and writes
them into the yaml, because E-10's fit lives or dies on exactly this diagnosis.

**Identifiability versus noise.** A noisy estimate gets better with more data. An
unidentifiable one never does: the data mathematically cannot distinguish the two
explanations, and the only honest outputs are the combination it *can* pin down plus
a flag. Constructed fuel in a clean race is the textbook case — it is exactly a
straight line in lap number, so "0.03 s/kg fuel" and "0.02 s/lap evolution plus a
different fuel slope" fit identically. The honest move, and the one the code makes,
is `identified: false`.

**Partial residuals.** After fitting a model, the partial residual for one term is
the raw residual plus that term's fitted contribution added back — "the data with
everything *except* tyre age removed". The degradation power law is fitted on these,
so it never re-explains fuel or evolution that the joint fit already took (the E-10
double-count, avoided a second time).

**Inverse-variance pooling.** To combine estimates of the same quantity from several
circuits, weight each by `1/SE²`: precise estimates count more, noisy ones barely
register. It is the minimum-variance way to pool independent unbiased estimates —
but the word *unbiased* is load-bearing, which is what the negative-pool story below
is about.

**Wilson score interval.** A confidence interval for a proportion that behaves at
small n and at the boundaries. The naive `p ± z·sqrt(p(1-p)/n)` collapses to width
zero at 0-of-4 races; Wilson gives 0-of-4 an upper bound near 0.49, which is the
honest statement that four races prove very little. Every hazard rate in the yaml
carries its Wilson band.

**Per-race probability to per-lap hazard.** The env needs "chance of an SC starting
*this lap*", the data gives "fraction of races with an SC". If a constant per-lap
hazard λ runs for L laps, the chance of at least one event is `1 - exp(-λL)`; invert
it and `λ = -ln(1-p)/L`. Survival analysis in one line (5.5.3).

**scipy curve_fit with bounds.** Nonlinear least squares for models like
`amplitude * age^exponent` that no linear design matrix can express. Bounds keep the
answer physical (grip loss cannot be negative; the exponent stays in a plausible
wear-to-cliff range), and the starting point `p0` matters because the optimiser is
local.

**KMeans and silhouette.** KMeans groups points into k clusters by nearest centroid;
the silhouette score measures how much better each point fits its own cluster than
the next one, giving a data-driven way to pick k. F02 clusters circuits on 2024
behaviour so 2026-dataless circuits can borrow tyre coefficients from cluster mates
(T5). Features are standardised first — KMeans is distance-based, and unscaled pit
seconds would drown fractional grip losses.

**Trapezoidal integration on irregular timestamps.** Telemetry arrives at roughly
4–5 Hz but never evenly (AR-16). Multiplying a sample count by an assumed 0.2 s
would invent time; instead each adjacent pair contributes
`dt * (value_left + value_right) / 2`, using the actual timestamp delta. Any
integral that crosses a data dropout would invent energy, so integration stops at
every trace break.

**The YAML 1.1 float trap.** Python's `repr(7e-06)` is `'7e-06'` — no dot. YAML 1.1
(what pyyaml speaks) only recognises scientific notation with a dot, so `safe_load`
returns the *string* `'7e-06'`, silently. The writer inserts the dot; a regression
test pins it.

**Byte-deterministic artifacts.** Running `make fit` twice on the same data must
produce a byte-identical file, so `git diff` is the change detector. Three habits buy
it: every SQL query has a total `ORDER BY` (float summation order changes the last
digit otherwise), the writer sorts keys at every level, and `generated_at` is a data
watermark ("seasons 2022-2026, round 6"), never a clock read.

## The code, guided

### senna/physics/fits/gate.py and frames.py

The gate is F-14 verbatim: `assert_quality_reports` checks that
`quality.report_path()` (F01) exists for every season and raises naming the missing
ones, before any database engine is even built. Fitting from unaudited data is the
failure mode; ten lines close it.

`frames.py` is the only fits module allowed to touch Postgres. Each function builds
one Core select, joins Lap → Session → Event, and returns a DataFrame. Two lines do
real work. Every statement passes through:

```python
def _held_in(stmt: Select, calibration_rounds: list[int]) -> Select:
    # E-14: 2026 rounds outside the frozen calibration list never reach a fitter
    return stmt.where(
        (Event.season < FIRST_2026_SEASON) | Event.round.in_(calibration_rounds)
    )
```

The frozen split is enforced at the SQL door, so held-out validation rounds cannot
leak into a fit even if a fitter forgets to check (they check too — defence in
depth). And every query carries a total ordering like
`.order_by(Lap.session_id, Lap.driver, Lap.lap_number)`, with a comment saying why:
stable row order keeps float sums identical run to run, which is half of
byte-determinism. Note also `pace_laps` filters `Session.is_dry.is_(True)` — a
session whose weather never landed (null) stays out of dry fits rather than sneaking
in (5.3.4).

### senna/physics/fits/fuel.py

Fuel mass is never observed — teams do not publish it — so it is constructed: total
burn equals the race allowance (F-06/T6), spread over the laps. Core logic, line by
line:

```python
ordered = laps.sort_values("lap_number")
```

One driver's race in lap order, because the cumulative sum below is meaningless
otherwise.

```python
slowed = ordered["track_status"].map(
    lambda status: bool(INTERVENTION_DIGITS & set(str(status)))
)
```

The F01 digit-string trick again (`set(str(status))`, from `flag_green_laps`): a lap
is "slowed" if any of digits 4/5/6/7 (SC, red, VSC, VSC-ending) appears anywhere in
its status. This is the line the whole E-10 story hangs on — slowed laps burn less.

```python
burn_weights = slowed.map({True: sc_burn_factor, False: 1.0})
kg_per_weight = race_fuel_kg / burn_weights.sum()
```

Green laps weigh 1.0, slowed laps weigh `sc_burn_factor` (0.6, stylised, in
fits.yaml). Dividing the allowance by the total weight normalises the profile so the
tank empties exactly at the flag whatever happened mid-race.

```python
burned_before_kg = kg_per_weight * burn_weights.cumsum().shift(1, fill_value=0.0)
return (race_fuel_kg - burned_before_kg).reindex(laps.index).rename("fuel_kg")
```

`cumsum().shift(1)` is "fuel burned before this lap started" — the shift because lap
1 starts with a full tank. The `reindex` puts the series back on the caller's row
order so it aligns with the laps frame by index, not by position.

`session_fuel` extends this to a multi-session circuit frame: each session's
allowance scales with its lap count against the circuit's longest race, so
kg-per-lap comes out the same for sprints (T6) and for red-flag shortened races. The
docstring admits the deliberate approximation: a shortened race's fuel *level* is
wrong, but level errors are absorbed by the joint fit's session fixed effects — only
the slope reaches the estimate.

### senna/physics/fits/joint_pace.py — the E-10 fit

The model:
`lap_time ~ session FE + driver FE + compound FE + per-compound (age + age²) + k_m·fuel + b·lap_number`.
Fitting fuel and evolution separately double-counts their shared downward trend
(E-10); fitting jointly is only honest if the design can tell them apart. That is
the whole drama of this module.

The clean mask first:

```python
clean = (
    laps["is_green"]
    & laps["is_accurate"]
    & laps["lap_time_s"].notna()
    & laps["pit_in_time_s"].isna()
    & laps["pit_out_time_s"].isna()
)
```

SC laps are 30+ seconds slow for reasons that are not fuel; in/out laps carry pit
deltas; inaccurate laps are FastF1's own distrust flag; NaT stays null per 5.3.4.
Any of these in the fit would sink every coefficient (the synthetic-race test proves
this by making them ruinously slow on purpose).

`_design_matrix` builds the matrix column by column: an intercept of ones; drop-one
dummies for session, driver and compound (`levels[1:]` — the first level is the
baseline, and keeping it would make the dummies sum to the intercept, a singular
matrix); then per-compound `age` and `age²` columns via multiplication with the
compound indicator, so each compound wears at its own rate; finally the constructed
fuel and the lap number — the two columns fighting over the same trend.

Then the fit and its diagnosis:

```python
coef, rank = _lstsq(columns, lap_time_s)
vif_fuel = _vif(columns, names.index("fuel_kg"))
condition_number = _condition_number(columns, names)
identified = bool(np.isfinite(vif_fuel) and vif_fuel <= vif_max and rank == len(names))
```

`np.linalg.lstsq` solves the least squares problem and reports the matrix rank —
rank below the column count means some column is an exact combination of others and
its coefficient is arbitrary. `_vif` regresses the fuel column on all other columns
and returns `1/(1-R²)`, with an explicit `inf` when R² is 1 to machine precision:
the clean-race case, where fuel *is* a line in lap number and the dummies. A fit is
`identified` only if the VIF is finite, under the threshold (30, fits.yaml), and the
matrix is full rank.

The identified branch is plain: `k_m` is the fuel coefficient, `evolution` is the
lap coefficient, and `trend = evolution + k_m * fuel_slope` reconstructs the
observable combined slope (fuel slope in kg/lap comes from `_within_session_slope`,
a pooled within-session regression so multi-session frames do not mix levels). The
honest branch is the interesting one:

```python
else:
    # refit without the fuel column: the lap coefficient is the combined
    # trend, which stays well identified when the attribution is not
    no_fuel = [i for i, name in enumerate(names) if name != "fuel_kg"]
    trend_coef, _ = _lstsq(columns[:, no_fuel], lap_time_s)
    trend = float(trend_coef[...index of lap_number...])
    ...
    if k_m_pooled_s_per_kg is None:
        k_m, evolution = None, None
    else:
        k_m = k_m_pooled_s_per_kg
        evolution = trend - k_m * fuel_slope_kg_per_lap
```

Drop fuel, refit, and the lap coefficient becomes the *combined* trend — which the
data always pins down, because the trend is what you can see. If a pooled `k_m` from
circuits that did identify is available, decompose: borrowed attribution, own trend.
Either way `k_m·fuel_slope + evolution` reproduces what was observed; only the
attribution is borrowed, and the yaml says so on the line
(`— decomposed via pooled k_m`). This is the flagged E-10 divergence from the plan,
implemented.

`pool_k_m` is four lines of inverse-variance weighting (`1/SE²`) over
`fit.identified` circuits only. Its docstring carries the war story: pooling *all*
the weak OLS estimates gave `k_m = -0.005` s/kg — a heavier car cannot be faster, so
the weak estimates were not noisy, they were confounded. The post-SC laps that bend
the fuel line also carry cold tyres, a bunched field and fresh rubber, and the fit
booked those pace effects to fuel. The sign flip was the diagnostic that set the
rule: identified circuits only. In the real data exactly one circuit cleared the
bar — Canada 2026, VIF 23.6, a sprint weekend with an interruption to bend the
fuel line — so the
2026 "pool" is Canada, `k_m = 0.011905` s/kg, and 2024 (no circuit identified)
borrows it via the cross-era fallback in `run.py`, flagged in the yaml as exactly
that, grade C all the way down because the fuel construction rests on AR-10's
unverified 70 kg.

The dataclass keeps `k_m_ols_s_per_kg` even when too weak to report — not for
pooling, but so the notebook can *show* the confounding diagnostic. And
`_refuse_validation_rounds` raises on any 2026 round outside the frozen calibration
list, naming the offender (E-14, the second layer behind `_held_in`).

`age_partial_residuals` re-runs the same design, then:

```python
age_contribution_s = design[:, age_columns] @ coef[age_columns]
raw_residual_s = lap_time_s - design @ coef
return fit_laps.assign(pace_residual_s=raw_residual_s + age_contribution_s, ...)
```

Residual plus the age terms added back: lap times with driver, session, compound,
fuel and evolution removed and only tyre age left in. That frame is the degradation
fitter's input.

### senna/physics/fits/degradation.py

The guard runs before anything else, and it raises rather than filters:

```python
def _refuse_poisoned(laps):
    in_or_out = laps["pit_in_time_s"].notna() | laps["pit_out_time_s"].notna()
    if in_or_out.any():
        raise InOutLapError(...)
```

frames.py already filters, and the joint fit's clean mask filters again — so if an
in/out lap reaches this fitter, some upstream contract broke, and fitting through it
would turn a cleaning bug into fake thermal runaway: in-laps sit at stint end, so
their +20 s would read as a tyre cliff (E-09). The error message says how many and
where to fix it. Same for `is_accurate`.

The fit itself is `curve_fit` on `amplitude * age^exponent` per compound, with
bounds from fits.yaml keeping it physical (a ≥ 0, b in [0.3, 3]) and `maxfev` raised
because flat-residual circuits push the optimiser to the a = 0 boundary slowly. Two
lines carry meaning:

```python
a=float(amplitude_s) / t0_s,  # seconds of delta over t0 = fractional grip loss
```

The curve is fitted in seconds (the residuals' units) but the spec's grip model is
fractional: `grip(age) = 1 - a·age^b`. Dividing the amplitude by the circuit's t0
converts one to the other. And the `thin` check — under `min_laps`, `min_stints`,
`min_drivers`, or never seen past `min_max_age` — sets `low_confidence` instead of
refusing: the fit is kept, flagged, and eligible for cluster transfer rather than
silently trusted.

### senna/physics/fits/hazards.py

`classify_track_status` maps digits to events (`4`→sc, `5`→red, `6`/`7`→vsc) and its
docstring pins the classic trap: `"12"` is the digits 1 and 2 — green then yellow,
never SC. `per_race_events` reduces laps to one boolean row per race per event kind.

`wilson_band` is the Wilson formula transcribed, tested against hand-computed
values, including the 0-of-n case that motivates it. The hazard conversion is where
the war story lives:

```python
p_per_race = n_with / n_races
if n_with == n_races:
    p_per_race = n_with / (n_races + 1)
return -math.log(1.0 - p_per_race) / race_laps + 0.0
```

The first version had no shrink, and a circuit with one race and one SC produced
`p = 1.0`, `log(0)` — a per-lap hazard of infinity, a safety car every lap of every
simulated race there. The boundary shrink `n/(n+1)` is the mildest statement that
the next race might stay green: 1-of-1 becomes p = 0.5. Interior counts pass through
untouched. The `+ 0.0` folds `-0.0` (from `-log(1.0)`) into a clean zero so the yaml
never prints a negative zero; a test checks the sign bit.

`status_multipliers` computes the SC and VSC lap-time multipliers (5.5.3
`status_mult`) as a median of per-session ratios, not a ratio of pooled medians —
pooling raw lap times across circuits would let short-lap circuits dominate the
green median while SC laps cluster wherever SCs happened to occur. Ratio first,
median second.

### senna/physics/fits/pit_loss.py

Twenty-five lines: mean, sample std (`ddof=1` — this sigma is the FIFO service-time
spread E-05 consumes), and n over OpenF1 durations, with nulls and stops over 60 s
(penalties, red-flag stops) excluded and *counted* in `n_excluded`. Excluded and
counted, never silent — the F01 reporting habit carried forward.

### senna/physics/fits/energy.py

No real per-lap ERS telemetry exists (F-13), so these integrals estimate what a 2026
powertrain could harvest and deploy from what the car observably did. The integrals
are core logic:

```python
for _, trace in car_data.groupby("trace_id"):
    time_s = trace["Time"].dt.total_seconds().to_numpy()
    dt_s = np.diff(time_s)
```

Grouping by `trace_id` — assigned upstream by F01's `split_telemetry_gaps` wherever
the sample gap exceeds 2 s — is the AR-16/F-13 discipline: no `dt` ever spans a
dropout, so a 30-second data hole cannot donate 30 seconds of full throttle.

```python
    flat_out = (trace["Throttle"].to_numpy(dtype=float) >= throttle_full_pct).astype(float)
    full_throttle_s += float(np.sum(dt_s * (flat_out[:-1] + flat_out[1:]) / 2.0))
```

The trapezoid rule on a 0/1 indicator: a sample at 97% next to one at 100%
contributes half its interval. The threshold is 98%, not 100, because throttle
sensors jitter (stylised, fits.yaml).

`_braking_phases_j` finds contiguous brake applications by edge detection on the
boolean channel (`np.diff` on the int cast; flatnonzero gives the flip indices, with
the two boundary cases for a trace that starts or ends braking), then per phase:

```python
shed_j = 0.5 * mass_kg * (speed_ms[start] ** 2 - speed_ms[end] ** 2)
total_j += max(0.0, shed_j)  # uphill or noisy phases must not pay energy back
```

ΔKE = ½m(v₁² − v₂²) across the whole phase — entry speed to exit speed, not
sample-by-sample, so intra-phase noise cancels. The `max(0, ·)` stops a phase where
the car somehow exits faster (crest of a hill, GPS noise) from *refunding* energy.
Mass is the car plus constructed fuel at that lap (`fuel_profile` again), which is
why 2026 energy rows are grade C too. `session_energy_frame` around it is selection
plumbing: only green, accurate, non-in/out laps with a start time; a driver missing
a channel is skipped and logged, never fatal (channel gaps are a fact of the source,
F-14).

### senna/physics/fits/clusters.py

`assign_clusters` standardises the features, runs KMeans for each k in the clipped
range (silhouette needs 2 ≤ k ≤ n−1; the range is clipped, never padded), and keeps
the k with the best silhouette. The seed comes from fits.yaml because a rerun that
reshuffled transfer donors would break byte-determinism. `transfer_degradation` is
the T5 ratio transfer in five lines: scale the donor's 2026 amplitude by the two
circuits' known era-2024 abrasiveness ratio, keep the donor's shape exponent, and
stamp the result `low_confidence: true` with `source_circuit` naming the donors —
a borrowed coefficient confesses forever.

### senna/physics/fits/params_writer.py

Hand-rolled YAML emission, because pyyaml's dumper does not do per-line comments and
comments are the whole point. Every leaf is a `(value, origin)` pair; `_render_mapping`
sorts keys at every level and prints `key: value  # origin`. The float branch is the
bug fix:

```python
text = repr(value)  # shortest round-trip repr; safe_load returns the same float
if "e" in text and "." not in text:
    # YAML 1.1 only reads scientific notation with a dot: "7e-06"
    # loads as a string, "7.0e-06" as the float
    text = text.replace("e", ".0e")
```

The first render of the real battery wrote a soft-compound `a: 7e-06`. The clusters
notebook then crashed on `np.mean` over degradation coefficients — one of them was a
string. `safe_load` had done exactly what YAML 1.1 says: no dot, not a float. The
notebook caught it, the writer fixed it, and
`test_scientific_notation_floats_load_back_as_floats` pins it. Strings go through
`json.dumps` (double-quoted, so a slug can never be reparsed as a date), and
`validate_complete` walks the tree and raises listing every null by dotted path —
F05's debugging starts from that message.

### senna/physics/fits/run.py

The orchestrator: gate first, then the six modules in declaration order, which is
dependency order (joint pace feeds degradation its residuals and t0; degradation,
energy and pit loss feed the cluster features; clusters feed the T5 transfer). A
`_Battery` object holds shared results in memory. Worth pausing on three choices.
A narrowed run (`--only` or `--circuit`) never writes the yaml — a partial battery
must not masquerade as the full artifact. The joint-pace stage runs twice over
unidentified circuits: first pass fits everyone, `_pool_k_m` pools the identified
ones per era (with the cross-era fallback when an era has none — and if *both* eras
somehow pooled empty, the gap is left for `validate_complete` to fail loudly rather
than guessed), second pass refits the unidentified circuits with the pooled value so
their yaml rows carry the decomposition. And `params()` is where grade C propagates:
every 2026 value touched by the AR-10 fuel construction carries
`(grade C via AR-10 fuel)` in its origin string, including the subtle case — a 2024
circuit whose attribution came *through* the 2026 pool inherits the flag even though
its own era's fuel is verified. Nothing silently promoted, exactly as the acceptance
checklist demands. Meanwhile `trend_s_per_lap`, `t_ref_s`, `s_ref_s` and
`sigma_driver_s` are computed from raw lap times alone, fuel-free, so they carry no
flag even in 2026.

The energy stage's broad `except` around `load_car_data` mirrors `run_ingest`
(F01): fastf1 raises a zoo of cache and parse errors, and one broken weekend must
not kill an hour-long battery. The warning is the record.

### tests/physics/fits/ and the notebooks

`conftest.py` builds the synthetic race: 57 laps, 20 drivers (a regression sample
size, not a grid — the comment heads off the 22-car reflex), an SC window at laps
20–24, staggered pit laps, two compounds, and known coefficients baked into the lap
times, with fuel built by the real `fuel_profile`. SC and in/out laps are made
ruinously slow on purpose, so a fitter that fails to exclude them cannot pass the
recovery tolerances — the filter is tested by consequence, not by inspection.

The two tests that matter most are a pair.
`test_recovers_injected_coefficients` proves the estimator works *when
identification exists*: the SC bends the fuel line, and k_m comes back within 20%.
`test_flags_unidentifiable_clean_race` is the honesty pin: the same race with
`sc_laps=()` must produce `identified is False` and still recover the combined
trend. Note the two VIF thresholds at the top of the test file: even with an SC, a
single race's fuel VIF sits in the low thousands (the bend is weak), so the recovery
test sets the bar at 10,000 to pin the estimator, while the production threshold of
30 governs pooled multi-session fits. That comment is the difference between a test
that documents reality and one that quietly lies.

The five notebooks are thin by construction (senna/CLAUDE.md: logic in the package,
narrative in the notebook) — every computation is an import, and their outputs are
the residual PNGs under `docs/fits/`. `fit_joint_pace.ipynb` carries the negative-
pool diagnostic and the `sc_burn_factor` sensitivity check; `fit_hazards_pit_loss.ipynb`
cross-checks track-status digits against race-control messages.

## How it connects

```
 Postgres (F01 superset + flags)          FastF1 cache (telemetry)
        │                                        │
   gate.py (F-14: quality reports exist?)        │
        │                                        │
   frames.py (E-14 held-out filter at the SQL door)
        │
        ├─► fuel.py ─► joint_pace.py ─► degradation.py ─┐
        ├─► hazards.py                                  ├─► clusters.py (T5)
        ├─► pit_loss.py (E-05 inputs)                   │
        └─► energy.py ◄──────────────────────────(cache)┘
                                │
                     params_writer.py ─► configs/physics_params.yaml
                                              │
                              F03 (synthetic 2026) and F05 (env) read it
```

F02 is the second box of the spec 5.1 pipeline: data in from F01's tables and the
FastF1 cache, one yaml artifact out, consumed by F03 and F05.

## Try it yourself

`make fit` needs `DATABASE_URL` pointed at the ingested `senna` database; it only
reads from it. A narrowed run never writes the yaml, so these are safe to repeat.

1. Read the artifact first. Open `configs/physics_params.yaml`, find
   `canadian_grand_prix` → `joint_pace` → `2026`, and explain every line to
   yourself: why `identified: true` here (`grep -c 'identified: true'` the file —
   it is the only one), why `k_m_s_per_kg` equals `globals.k_m_pooled_s_per_kg_2026`
   exactly, and why `trend_s_per_lap` carries no grade-C flag while `t0_s` does.
   You'll know it worked when you can state which yaml values would survive AR-10's
   fuel number being wrong, and which would move.

2. Run a narrowed battery:
   `make fit CIRCUIT="--circuit monaco_grand_prix" ONLY="--only joint_pace,degradation,hazards,pit_loss"`.
   Watch the log: the joint fit reports `identified=False` with its VIF, degradation
   fits per compound, and the last line says the yaml was *not* written. You'll know
   it worked when `git diff configs/physics_params.yaml` is empty afterwards and you
   can say why the orchestrator refuses.

3. Break the boundary shrink. In `hazards.per_lap_hazard`, delete the
   `if n_with == n_races` block and run `pytest tests/physics/fits/test_hazards.py -q`.
   You'll know it worked when `test_per_lap_hazard_saturated_rate_stays_finite`
   fails with a `math domain error` from `log(0)` — the exact crash the real 1-of-1
   circuit produced — and the other hazard tests still pass. Revert.

4. Reproduce the YAML float bug from a clean prompt:
   `python3 -c "import yaml; print(type(yaml.safe_load(repr(7e-06))))"` prints
   `str`, not `float`. Then remove the `text.replace("e", ".0e")` line in
   `params_writer._scalar` and run
   `pytest tests/physics/fits/test_params_writer.py -q`. You'll know it worked when
   the scientific-notation test fails on an `isinstance` check — the regression pin
   for a bug a notebook found. Revert.

5. Predict, then test: set `fuel.sc_burn_factor: 1.0` in `configs/fits.yaml` and
   rerun exercise 2's command against a circuit that currently identifies nothing.
   Prediction to make first: with SC laps burning like green laps, the fuel line
   never bends, so *no* circuit can identify, the pool is empty, and a full
   (non-narrowed) run would die in `validate_complete` listing null k_m paths
   rather than writing a yaml with invented attributions. You'll know it worked
   when the log shows `identified=False` with an infinite or huge VIF everywhere,
   and you can trace which guard would catch the full run. Revert.

## Check yourself

1. Fuel mass is "constructed, not observed". What exactly is constructed, and why
   does that construction make fuel-versus-evolution unidentifiable in a race with
   no interruptions?

2. Defend this design choice: when the fuel VIF exceeds the threshold, the code
   reports the combined trend with `identified: false` and decomposes it via a
   pooled k_m, instead of just reporting the OLS fuel coefficient the regression
   produced anyway.

3. Pooling all circuits' k_m estimates gave −0.005 s/kg. Why does the sign of that
   number prove the weak estimates were confounded rather than merely noisy, and
   what physically caused the confounding?

4. Why the Wilson interval instead of the textbook normal approximation for the
   hazard bands, and why does `per_lap_hazard` shrink a saturated count to n/(n+1)
   before taking the log?

5. `frames.py` filters in/out laps at the SQL layer and the joint fit's clean mask
   filters them again — yet `fit_degradation` still *raises* if it sees one, rather
   than filtering. Why raise, and why there?

---

### Answers

1. Total burn is set equal to the race allowance (F-06/T6) and spread over laps by
   a weight per lap — 1.0 green, `sc_burn_factor` slowed. In a clean race every
   weight is 1.0, so fuel remaining is exactly `allowance − c·lap_number`: a
   perfect line in lap number. The design matrix then contains two columns
   measuring the same direction, and OLS cannot split the observed downward trend
   between them — any k_m paired with a compensating evolution fits identically.
   Only an interruption bends the fuel line and creates (weak) separation.

2. Viva answer: the per-race attribution is mathematically unidentifiable, so
   reporting the raw OLS split would be presenting an arbitrary number as a
   measurement — the coefficient swings wildly with noise when VIF is high. The
   combined trend is always identified because it is directly observable, so we
   report what the data pins down, flag the attribution honestly, and borrow k_m
   only from circuits where the instrument was strong enough to trust; the fitted
   sum reproduces the observed trend either way, so E-10's actual failure mode,
   double-counting, cannot occur.

3. Noise is symmetric: averaging many noisy unbiased estimates converges on the
   truth, and inverse-variance pooling would have delivered a small positive
   number. A *negative* pooled mass sensitivity says heavier cars lap faster,
   which is physically impossible — so the estimates share a systematic bias, not
   noise. The mechanism: identification comes entirely from post-interruption
   laps, and those laps are also slow-then-fast for non-fuel reasons (cold tyres
   warming up, a bunched field spreading out, fresh rubber laid by the restart).
   The fit books those pace effects to the fuel column because that is where the
   variation is. Hence the rule: pool identified circuits only.

4. The normal approximation's width goes to zero at 0-of-n and 1.0-of-n — it
   claims certainty exactly where the data is thinnest, and most circuits give us
   four or five races. Wilson stays inside [0, 1] and gives 0-of-4 an upper bound
   near 0.49, which is the honest band. The shrink exists because
   `λ = −ln(1−p)/L` is infinite at p = 1: one race with one SC would otherwise
   mean a safety car every simulated lap forever. n/(n+1) is the mildest possible
   statement that the next race might stay green; interior counts are untouched.

5. Filtering inside the degradation fitter would *hide* an upstream failure: if an
   in/out lap ever reaches it, either frames.py or the residuals pipeline broke
   its contract, and silently dropping the row leaves that bug alive. Raising
   turns the contract violation into a loud, named error (E-09) at the one fit
   where the poison is worst — in-laps sit at stint end, so their pit delta reads
   as a tyre cliff and would corrupt exactly the coefficient this fitter exists to
   produce. Defence in depth, with the last layer refusing instead of coping.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| OLS with fixed effects | F02 | Least squares on a design matrix with drop-one 0/1 dummy columns per category level, so slopes are estimated within driver/session/compound. |
| Collinearity, VIF and condition number | F02 | Near-linear dependence between regressors; VIF = 1/(1−R²) of one column on the rest, condition number the same worry matrix-wide — both reported per fit (E-10). |
| Identifiability vs noise | F02 | Noise shrinks with data; unidentifiable means the data cannot distinguish two explanations — report what is pinned down and flag the rest (`identified: false`). |
| Partial residuals | F02 | Raw residuals plus one term's fitted contribution added back: "the data with everything except this term removed" — the degradation fit's input. |
| Inverse-variance pooling | F02 | Combine estimates weighted by 1/SE²; minimum variance for unbiased inputs, which is why confounded (not merely noisy) fits must be excluded first. |
| Wilson score interval | F02 | A proportion confidence band that stays usable at 0-of-n and small n, unlike the normal approximation's zero-width collapse at the boundaries. |
| Per-race probability to per-lap hazard | F02 | λ = −ln(1−p)/laps inverts "chance of ≥1 event in L laps of constant hazard"; saturated counts shrink to n/(n+1) before the log (5.5.3). |
| scipy curve_fit with bounds | F02 | Nonlinear least squares for models like a·age^b; bounds keep coefficients physical and p0 seeds the local optimiser. |
| KMeans and silhouette | F02 | Distance-based clustering on standardised features; silhouette scores pick k, and a fixed seed keeps transfer donors stable across reruns (T5). |
| Trapezoidal integration on irregular timestamps | F02 | Integrate with actual dt per sample pair, `dt·(y₁+y₂)/2`, never a nominal rate; stop at every trace break so dropouts donate nothing (AR-16/F-13). |
| The YAML 1.1 float trap | F02 | `repr(7e-06)` has no dot, so `safe_load` returns a string; scientific notation must be written `7.0e-06` to load back as a float. |
| Byte-deterministic artifacts | F02 | Same data in, identical bytes out: total ORDER BY on every query, sorted keys in the writer, and a data watermark instead of a clock. |
