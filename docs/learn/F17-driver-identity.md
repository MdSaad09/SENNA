# F17 — driver identity, and the number the fit was already computing

## What we built and why

Until this feature every car on the grid was the same driver with a different random
number. `reset()` drew `driver_s ~ N(0, sigma_driver_s)` for all twenty-two seats, the
rival archetypes deliberately carried no pace offset, and `senna/eval/traces.py` said the
quiet part out loud in its own docstring: *"Driver pace offsets are drawn, not fitted,
because per-driver skill is deliberately not modelled."* That module is handed
`laps_by_driver` keyed by real driver codes. It knew which seat was Verstappen's and gave
him a coin flip.

The number that fixes this was already being computed and then thrown away. The joint pace
regression (F02, refitted in F18) puts a dummy column in its design matrix for every driver
so that fuel burn and track evolution are estimated *within* a driver rather than across
them. Those dummy coefficients are per-driver lap-time offsets in seconds. `joint_pace.py`
folded their mean into `t0_s`, kept their standard deviation as `sigma_driver_s`, and
dropped the vector on the floor.

F17 keeps the vector. It adds a second, smaller fit — one number per driver saying how fast
they wear a set relative to the curve everyone shares — and writes both into a generated
`configs/drivers.yaml`: 31 drivers in era 2024, 22 in era 2026, every leaf carrying the
laps and seasons behind it. `F1RaceEnv(..., drivers=["VER", "HAM", ...])` then runs a race
as *this* grid rather than *a* grid.

The code is small. One multiplication in `lap_time_s`, one overwrite in `reset`, one dict
persisted instead of averaged. What is large is a config file of numbers about named real
people, which is why most of this lesson is about honesty rather than about arrays. The
best thing in the feature is a bug: a centring error that displaced twenty-two published
claims by 0.95 s a lap, that both reviewers caught, and that the test written to prevent it
was structurally incapable of catching.

## New ideas in this feature

**A nuisance parameter is a measurement.** You already met fixed effects in F02 (drop-one
dummy columns per category, so slopes are estimated within driver, session and compound).
The new idea is what they are *for*. A fixed effect is usually a nuisance: you include the
driver dummies because otherwise a fast driver's laps bias the fuel coefficient, and then
you ignore them. But the coefficient on "is this lap Verstappen's" is a real estimate with
a real sample behind it, and at Monaco in era 2024 it is −1.70 s a lap. F17's fitting side
is almost entirely "stop discarding this". The viva version: **the driver dummies exist so
that the fuel and evolution terms are identified within a driver, and their coefficients
are the by-product; F17 publishes the by-product with its lap count and its seasons instead
of collapsing it to a mean and a standard deviation.**

**It is a seat effect, not a skill measurement.** Era 2024 pools 2022 through 2025. Session
fixed effects absorb per-session mean pace, so what survives in the driver coefficient is
that driver's offset within their own sessions — driver plus car, lap-weighted across the
seasons they raced. Verstappen's era-2024 number is four seasons of Red Bull. This is the
spine of the whole feature, and it is why the leaf is called `seat_pace_s` rather than
`pace_s`: the key states the limitation before anyone reads the comment. The file header
says it too, and so does every cell, because a circuit can only carry the seasons it was
raced in — Verstappen's Monaco cell is 65 laps from 2025 alone, so calling it "four cars"
would be false at that one circuit.

**Centring, and why a publication gate breaks it.** The design is drop-one coded, so the
raw coefficients are relative to whichever driver sorted first, and `t0_s` has already
absorbed their mean. Persist them raw and every lap time shifts by that mean. So the fit
centres them: subtract the mean, spread untouched. That was caught in planning, and it has
a test.

Then the second one, which nobody planned for. Publishing a per-circuit cell requires 30
clean laps at that circuit (below that the driver keeps their mean over the circuits that
did clear). The fit centres over *every* level in the design; the gate then removes the
thinnest levels. At Suzuka in era 2024 one driver had a single clean lap and an effect of
+21.6 s — one lap of a regression is arbitrarily far from the mean — so he set the centre
for that column and was then dropped from the file. Every one of the 22 surviving cells was
published 0.95 s too fast. Every driver at Suzuka read as quicker than the field average,
which a centred contrast cannot be.

The general shape is worth memorising, because it will happen again anywhere you gate after
you normalise: **a quantity centred on set A, published on subset B, is only centred if you
re-centre on B.** The fix is one extra pass over the cells in `run.py`, after the gate and
before the write.

**Cluster-robust standard errors.** A degradation residual is not independent lap to lap. A
set that runs hot is slow for its whole life, so eighteen laps of one stint are closer to
one observation than to eighteen. A textbook standard error divides by the square root of
the lap count and comes out too small — on the real era-2024 fit, 2.3x too small at the
median. Fix it by summing the estimating equation *within* each stint first and then
squaring, so correlated laps cannot each claim to be fresh evidence. This matters because
the precision gate is the only thing standing between a thin driver and a fitted-looking
number: without clustering, everyone passes any gate you would be willing to write down.

**Reparameterise until the thing is estimable.** SENNA refuses a per-driver degradation
*curve* for a real statistical reason (`degradation.py` has a `min_drivers` floor; one
driver's stints cannot identify a power law). But a single multiplier on the pooled curve
is estimable, and the way F17 estimates it is the interesting part: it regresses the
driver's partial residual on *the degradation the pooled curve predicts for that lap*,
not on tyre age. Circuits and compounds have wildly different `a` and `b`, so a slope
against age would mean a different thing at every circuit and get averaged anyway. A slope
against the prediction is dimensionless-by-construction and pools correctly.

**Draw, then overwrite.** F16's lesson, back for a second look: a seeded generator hands out
variate 1, 2, 3 in call order, so moving or removing a draw changes every seeded race in the
repo. `reset` therefore draws all 22 offsets exactly as it always did and *then* overwrites
the named seats. Three things fall out for free. `drivers=None` is byte-identical, so F16's
golden fixtures still prove the default path did not move. A named race is the same race as
the unnamed race at that seed, with people in it. And an unnamed seat needs no special case:
it simply keeps what it drew.

**Zero is not neutral.** The obvious fallback for a driver the table has never heard of is
0.0. It is wrong, and the reason is worth holding on to: the effects are centred, so zero is
the field *average*, and on a grid the average is quicker than most of it. Defaulting an
unknown driver to zero quietly hands them one of the best cars on the track. `lineup.py`
carries NaN there instead and lets the drawn value stand.

## The code, guided

Reading order: where the numbers come from, how they get written down honestly, then how a
race reads them.

### `senna/physics/fits/joint_pace.py` — the effects, kept

The design matrix has not changed at all. It is worth re-reading the drop-one loop anyway,
because everything downstream is arithmetic about it:

```python
    for factor in ("session_id", "driver", "compound"):
        levels = sorted(fit_laps[factor].unique())
        for level in levels[1:]:  # drop-one: the first level is the baseline
            columns.append((fit_laps[factor] == level).to_numpy(dtype=float))
            names.append(f"{factor.replace('session_id', 'session')}={level}")
```

`levels[1:]` is why the coefficients are contrasts. If you gave every driver a column the
matrix would be rank-deficient (the driver columns would sum to the intercept), so one
driver is folded into the intercept and everyone else is measured against them. Which driver
is arbitrary (whoever sorts first alphabetically), and that arbitrariness is exactly what
centring removes.

`_centred_effects` is the new function, and it is four lines of work:

```python
    by_name = {name: float(coef[i]) for i, name in enumerate(names)}
    raw = {
        str(level): by_name.get(f"{prefix}{level}", 0.0)
        for level in sorted(levels.unique())
    }
    mean = sum(raw.values()) / len(raw)
    return {level: value - mean for level, value in raw.items()}
```

`by_name` pairs coefficients with their column names, because `coef` is a bare array and
the names are the only thing that knows which slot is whose. The `.get(..., 0.0)` default is
the dropped baseline driver: they have no column, and their coefficient is zero by
construction. `mean` is what `t0_s` already absorbed on line 136 of the same file. The
subtraction is the whole point — spread unchanged, so the centred effects still have
standard deviation `sigma_driver_s`, which is what keeps a named lineup and the random draw
distributionally matched, which is what keeps M1 comparing like with like.

Three fields ride alongside on `JointPaceFit`: `driver_effects_s`, `driver_laps` and
`driver_seasons`. The sample travels with the estimate because "how do you know Verstappen's
number?" is answered by laps and seasons, not by the value.

### `senna/physics/fits/run.py` — building the file, and the re-centring fix

`driver_tree` turns the battery's `(slug, era) -> fit` dict into the shape
`configs/drivers.yaml` wants. The gate is one condition:

```python
            if laps >= min_laps_for_seat_pace:
                cells.setdefault((code, era), {})[slug] = _Cell(...)
```

30 laps, from `configs/fits.yaml`. It clears 628 of 652 era-2024 driver-circuit cells and
91 of 127 era-2026 ones, which is the shape you want from a gate: it bites the tail without
gutting coverage. Below it the cell is simply absent, and the driver keeps
`seat_pace_mean_s` — E-10's "do not publish what the design could not identify", one layer
down from where F02 met it.

Then the fix, which runs immediately after the gate and before anything is written:

```python
    columns: dict[tuple[str, str], list[float]] = {}
    for (_code, era), by_circuit in cells.items():
        for circuit, cell in by_circuit.items():
            columns.setdefault((era, circuit), []).append(cell.effect_s)
    centre = {key: sum(values) / len(values) for key, values in columns.items()}
    for (_code, era), by_circuit in cells.items():
        for circuit, cell in by_circuit.items():
            by_circuit[circuit] = replace(
                cell, effect_s=cell.effect_s - centre[(era, circuit)]
            )
```

First pass collects each circuit-era column of *surviving* cells. `centre` is that column's
mean. Second pass subtracts it. The key is `(era, circuit)` rather than circuit alone
because era 2024 and era 2026 are separate regressions with separate fields, and mixing them
would centre a four-season column on a six-race one.

The docstring is where the honesty lives, and it does something I want you to copy: it
prices its own side effect. Re-centring costs a small absolute offset against `t0_s` — the
mean of the dropped cells, under 0.02 s on every healthy circuit. Where it is larger, `t0_s`
and `sigma_driver_s` were carrying the same outlier and are wrong by the same amount, so
the offset removes error rather than adding it. Fixing it properly means gating the
regression's driver factor, which moves every fitted constant in the repo, and that is not
this feature's job.

`_driver_entry` renders one driver's era block. Read the provenance strings rather than the
structure:

```python
            f"{DRIVER_NB} — {cell.laps} clean laps, "
            f"season(s) {', '.join(str(s) for s in cell.seasons)}"
            + (" (grade C via AR-10 fuel)" if cell.grade_c else "")
```

Per cell, not per driver, and the comment above it explains why: France last ran in 2022,
Las Vegas from 2023, so a driver-level union of seasons would tell a reader their Le
Castellet number came from four cars when it came from one. `grade_c` is subtler and worth
following: a driver coefficient only meets the fuel column where the circuit's attribution
was identified, because an unidentified fit refits without fuel entirely
(`_splice_fuel_zero`, F18). So AR-10's constructed 2026 fuel grade travels onto the cells
that saw it and stays off the ones that did not.

One more line, small and load-bearing:

```python
            round(style.rel_se, 4) if np.isfinite(style.rel_se) else "inf",
```

The relative standard error is published even on refusals — especially on refusals, since
it is the number that explains them — and rendered as the string `"inf"` when the design had
no degradation signal at all, following `vif_fuel`'s precedent. A bare `inf` is a
non-finite constant and `validate_complete` refuses those, rightly.

### `senna/physics/fits/tyre_style.py` — the second fit

`deg_prediction_s` computes what the pooled curve says this lap's tyre has already cost, and
it does so by calling the simulator's own `tyre_deg_s`. Not a second spelling of T5. The
multiplier is a slope against this quantity, so if the two ever drifted apart the fitted
style would be scaling a curve the race does not run.

`_one_driver` is the estimator, and every line earns its place:

```python
    stints = laps.groupby(["session_id", "stint"], dropna=False)
    sample = {"n_stints": int(stints.ngroups), "n_laps": int(len(laps))}

    signal = float(predicted_s @ predicted_s)
    if signal <= 0.0:
        return {"mult": 1.0, "se": np.inf, "rel_se": np.inf, **sample}

    mult = float(residual_s @ predicted_s) / signal
    error_s = residual_s - mult * predicted_s
```

The cluster key is `(session_id, stint)` and it needs both fields: stint numbers restart
every session, so keying on `stint` alone silently merges a driver's Bahrain second stint
with their Monaco second stint, and both the count and the error bar come out wrong.
`dropna=False` keeps laps whose stint number is missing — FastF1 loses that channel in
session-sized holes — because dropping them would leave those laps in the denominator and
take them out of the numerator, and the error bar would get *tighter* the patchier the data.

`signal` is Σd̂², the denominator of the least-squares slope. The guard above it is a
denominator guard the plan did not anticipate: 26% of the committed degradation curves sit
at exactly `a = 0`, where the fitter hit its lower bound on a flat residual cloud. A driver
whose whole sample came from those has no degradation to be fast or slow at, so the honest
answer is "unidentified", not a division quietly returning infinity.

`mult` is Σ(r·d̂)/Σd̂² — one parameter, closed form, no optimiser. Then the clustered error:

```python
    meat = sum(
        float((group["_predicted_s"] * group["_error_s"]).sum()) ** 2
        for _, group in laps.assign(...).groupby(["session_id", "stint"], dropna=False)
    )
    se = float(np.sqrt(meat) / signal)
```

Read the order of operations, because it is the entire idea: sum `d̂·e` *within* a stint,
then square, then sum across stints. The naive version squares each lap and sums, which
assumes every lap is independent evidence. A hot set contributes eighteen same-signed terms
that cancel nothing, and the clustered sum notices. Median inflation on the era-2024 fit:
2.3x.

`fit_deg_multipliers` applies two gates and then normalises:

```python
    identified = {
        code: fit for code, fit in raw.items()
        if fit["n_stints"] >= min_stints and fit["rel_se"] <= max_rel_se
    }
    scale = _normalising_scale(identified)
```

`min_stints` is 12 and is a floor rather than a filter — the thinnest era-2024 driver
already has 12 stints and the median has 132. `max_rel_se` is 0.10 and is the gate that
bites: it identifies 31 of 31 drivers in era 2024 and 15 of 22 in era 2026. Look at who
fails in 2026 and the two gates separate cleanly: five drivers fail on precision (STR at
0.174, ALB 0.133, BOR 0.124, BOT 0.116, ALO 0.110) and two on the count floor (HUL with 11
stints, LIN with 10) despite comfortable precision. That is a gate doing its job where the
data is thin, not manufacturing refusals where it is not.

`_normalising_scale` is centring's cousin. The pooled `a` was fitted on all these drivers
together, so their weighted average *is* the curve by construction. Divide the identified
multipliers by their lap-weighted mean and the published vector averages to exactly 1.0;
skip it and naming a full grid would move every stint length in the race at once instead of
redistributing wear between seats. `rel_se` is invariant under the division, so no driver
crosses the gate as a side effect of being normalised.

Is `deg_mult` just seat pace wearing a second name? Partly, and the notebook measures how
much: the two correlate at r = +0.404, so r² = 0.163 and 84% of the tyre-style spread is
something other than how quick the seat was. Both quantities carry the car, so a slower seat
wearing its tyres harder is the expected shape rather than a surprise — bad cars slide more.
The 84% is what a named race actually uses.

### `senna/env/lineup.py` — the ladder

Seventy-six lines, most of them docstring. `resolve` walks the seats and tries three rungs:

```python
        cell_s = (entry.get("seat_pace_s") or {}).get(circuit)
        mean_s = entry.get("seat_pace_mean_s")
        if cell_s is not None:
            seat_pace_s[seat], levels[seat] = float(cell_s), _CIRCUIT
        elif mean_s is not None:
            seat_pace_s[seat], levels[seat] = float(mean_s), _DRIVER_MEAN
```

The array starts as `np.full(n_cars, np.nan)`, so a seat nothing answered for stays NaN and
the third rung happens by omission. `levels` records which rung answered, so a reader can
tell a measured seat from an inferred one without rerunning the fit. `deg_mult` is resolved
outside that if/elif on purpose: the two gates are separate, so a driver can carry a
publishable tyre style without a publishable seat pace.

`_table` swallows `FileNotFoundError` and returns `{}`. That is not a silent default for a
fitted constant, which the loader is right to refuse. It is the statement that the table is
an optional overlay whose absence has a defined meaning. Without it, M2 would refuse to run
on a fresh clone.

### `senna/env/race_env.py` and `dynamics.py` — two edits

```python
            driver_s = self._rng.normal(0.0, self.scenario.sigma_driver_s, n)
            if self.scenario.lineup is not None:
                named_s = self.scenario.lineup.seat_pace_s[:n]
                driver_s = np.where(np.isnan(named_s), driver_s, named_s)
```

The draw is unconditional and comes first. `np.where` on the NaN mask is the whole fallback
ladder's third rung, expressed as one vectorised line. All of it sits in the else branch of
the twin check: in a replay the trace owns `driver_s`, as it always has, and only `deg_mult`
comes from the lineup.

In `lap_time_s`:

```python
    if scenario.lineup is not None:
        a = a * scenario.lineup.deg_mult[: a.size]
```

`a` is the fitted degradation amplitude, already looked up per car by compound. T5's form is
untouched: scaling `a` means a fresh set still costs nobody anything, and only the growth
with age changes. The `[: a.size]` slice is what lets a one-car solo race work off a
full-width lineup, and `test_a_solo_race_takes_the_named_seat` pins it — widen it to a suffix
and every 22-car test still passes while a solo race drives on seat 21's tyres.

The observation deliberately does not change. Feature #10 (`tyre_grip_est`) still reads the
pooled `scenario.deg_a`, and so do the heuristic and the oracle. That reads correctly as
physics: the agent's model of the tyre is the engineer's model, and a driver's realised wear
differing from it is exactly what `deg_mult` represents. It also keeps F20 as the feature
that owns observation changes, and therefore the retrain.

### `senna/eval/traces.py` — the seat that started all this

```python
    drawn_s = rng.normal(0.0, sigma_driver_s, n_cars)
    named = resolve(
        list(laps_by_driver), circuit=circuit, era=era, n_cars=n_cars, configs_dir=configs_dir
    )
    return np.where(np.isnan(named.seat_pace_s), drawn_s, named.seat_pace_s)
```

Same pattern as `reset`, for the same reason, through the same resolver — one loader means
the trace and the env cannot disagree about who is fast. `list(laps_by_driver)` is car
order, which is how the harness knows which column is the driver being counterfactualled,
and the phantom cars padding a short field out to 22 are nobody, so they keep a drawn
offset.

## What it did to M2

M2 is the counterfactual: the agent races the real grid's race, against a replay of what the
real team actually did. Re-measured with fitted seat pace:

| Reading | Mean delta | 95% CI (descriptive) | Sign test |
|---|---|---|---|
| Drawn driver pace (F18 chapter) | −3.66 | [−5.82, −1.16] | 1W/8L/1T, p = 0.039 |
| Fitted seat pace (F17) | **−4.58** | [−8.38, −1.20] | 1W/8L/1T, p = 0.039 |

The pre-registered sign test does not move: the same nine races fall the same way, so the
conclusion is unchanged and only its size worsened. This agent loses reliably to replayed
real strategies. The direction was not knowable before the roll, and the plan is committed
saying so, which is the only reason that claim is worth anything.

The mechanism matters more than the number. The seat offset largely cancels *inside* each
pair, because both legs share the lineup and the counterfactualled driver is car 0 in both.
What moves is field context: giving the real grid its real pace changes where that car sits
among the rivals, and therefore changes the strategic problem. Las Vegas swings furthest, to
−18, because a fitted Verstappen seat puts the replay baseline on the front row and hands
the agent that much more to lose.

And the re-run exposed something nobody was looking for. A twin replay is near-deterministic
by construction — the trace supplies the events, `TraceSource` returns zero lap noise and the
fitted pit-service mean with no draw, because that is what makes M3's oracle regret a clean
ceiling. So the five seeds per race were never varying pit service, whatever the config
comment claimed. They were varying the random driver draw, the very coin flip F17 removed.
Nine of the ten races are now identical across all five seeds. `seeds_per_race` stays at 5
and `configs/eval.yaml` now carries the correction in capital letters, because changing the
shape of a published metric is a decision, not a side effect.

## What did not come out clean

Two things went wrong during the build itself and were caught before landing. Both are
worth more than the parts that went smoothly.

**The centring guard was vacuous, and it was the guard written for the incident.** The
first version of
`test_a_published_column_is_centred_on_the_cells_that_survived_the_gate` was well written,
well named, and green with `_recentre_published_columns` deleted. Its fixture handed
`driver_tree` effects that were already centred over the drivers that survive the gate, so
adding the one-lap outlier displaced nobody — while the real pipeline centres over every
level *including* the outlier, which is exactly what displaces everyone else. Neutering the
fix reddened `test_a_cell_below_the_lap_gate_is_not_published` instead, via arithmetic about
Monaco that nobody would find by reading the name.

Read the shape of that twice, because it is the same shape as the bug. The original defect
was a test asserting on the fit's effects (which summed to zero *with* the outlier) while
the published file was displaced. The fix for it then shipped with a test asserting on a
fixture that could not display the defect. Both times the assertion was true and about the
wrong object. The fixture now centres over every level before handing it over, and exercise
5 walks you through breaking it both ways.

Neither reviewer found this one, and neither did the test suite. It was found by reading the
test and asking what it would take for it to fail.

**A config comment that described a different computation.** `configs/fits.yaml` claimed
`min_laps_for_seat_pace` cleared "190 of 235" era-2026 cells. The real numbers are 91 of
127 — the 235 came from a query counting every 2026 session rather than the six calibration
rounds the fit is allowed to see (E-14). The era-2024 half, 628 of 652, was right all along.
That is F18's lesson recurring at comment scale: a confident provenance line describing a
different computation from the one in front of the reader. It is corrected, and the notebook
now executes both eras so the number has a cell behind it rather than a memory.

## How it connects

F17 adds no box to the 5.1 diagram. It adds an output to the first box and an optional input
to the middle one.

```
   ingested laps (F01, Postgres)
            |
            v
   [ fits battery ]
      joint_pace ──► driver fixed effects ──► centred ──┐
            |                                            │
            └─► degradation ──► tyre_style ──► deg_mult ─┤ (gates: 30 laps, 12 stints,
                                                         │  rel_se <= 0.10)
                                          re-centre on published cells
                                                         │
                                                         v
                                            configs/drivers.yaml  (A-09 round-trip)
                                                         │
                    drivers=[...] (opt-in) ──────────────┤
                                                         v
   build_scenario ──► scenario.lineup ──► reset overwrites driver_s (named seats only)
                                     └──► lap_time_s scales `a` by deg_mult
                                                         │
   eval/traces.py ──► EventTrace.driver_s ───────────────┤
                                                         v
                                              M2 counterfactuals
```

Everything on the default path (`drivers=None`) reads none of it: training, F14's other
metrics, the frozen model. `drivers.yaml` is deliberately kept out of `train.CONFIG_FILES`
for that reason, and put into `M2_CONFIG_FILES` and the M2 envelope's
`drivers_fingerprint`, because M2 names a lineup for every race and the hash has to identify
what produced the number.

## Try it yourself

`source .venv/bin/activate` first.

1. **Read one driver out of the table.**

   ```
   python -c "import yaml; e=yaml.safe_load(open('configs/drivers.yaml'))['drivers']['VER'][2024]; \
     print(e['seat_pace_s']['monaco_grand_prix'], e['seat_pace_mean_s'], e['deg_mult'], e['deg_mult_rel_se'])"
   ```

   then `awk '/^  VER:/,/^  VET:/' configs/drivers.yaml | grep monaco`. You'll know it
   worked when the numbers are −1.7023, −1.1163, 1.0243, 0.0294 and the comment beside the
   Monaco cell says "65 clean laps, season(s) 2025" — one season, so that specific number is
   one car, and you can now answer "how do you know that?" for it without leaving the file.

2. **Build a named grid.**

   ```
   python -c "from senna.env.scenario import build_scenario; \
     s=build_scenario('monaco_grand_prix','2024',drivers=['VER','HAM','LEC']); \
     print(s.lineup.levels[:4]); print(s.lineup.seat_pace_s[:4]); print(s.lineup.deg_mult[:4])"
   ```

   You'll know it worked when the fourth seat reads `drawn`, `nan` and `1.0` while the first
   three are `circuit` with real numbers. Now swap `'LEC'` for `'ZZZ'` and predict all three
   lines before you run it.

3. **Check a column really is centred.**

   ```
   python -c "import yaml; d=yaml.safe_load(open('configs/drivers.yaml'))['drivers']; \
     col=[e[2024]['seat_pace_s']['japanese_grand_prix'] for e in d.values() \
          if 'japanese_grand_prix' in e.get(2024,{}).get('seat_pace_s',{})]; \
     print(len(col), sum(col)/len(col))"
   ```

   You'll know it worked when you get 22 cells averaging about −1.4e−05. Before the fix this
   printed −0.95: twenty-two drivers all faster than the average of themselves.

4. **Break the tyre-style path and read the failures.** In `senna/env/dynamics.py`, delete
   the line `a = a * scenario.lineup.deg_mult[: a.size]` and run
   `python -m pytest tests/env/test_lineup.py -q`. Predict first: which of the ten tests
   should notice? You'll know it worked when exactly two go red —
   `test_the_table_s_multiplier_reaches_the_lap_time` and
   `test_tyre_management_lengthens_the_useful_stint` — and
   `test_a_faster_driver_finishes_ahead_on_equal_strategy` stays green, because pace does not
   travel through that line. Revert.

5. **Check that the centring guard actually holds the centring fix.** In
   `senna/physics/fits/run.py`, comment out the call to `_recentre_published_columns(cells)`
   and run `python -m pytest tests/physics/fits/test_drivers_writer.py -q`. Predict which
   tests fail. You'll know it worked when two go red, and one of them is
   `test_a_published_column_is_centred_on_the_cells_that_survived_the_gate` — the test named
   after the thing you broke. Restore it.

   Now do the more interesting half. Put the fix back and instead delete these two lines
   from `_tree` in the test file:

   ```python
       mean_s = sum(bahrain_effects_s.values()) / len(bahrain_effects_s)
       bahrain_effects_s = {code: v - mean_s for code, v in bahrain_effects_s.items()}
   ```

   Then comment out `_recentre_published_columns` again. The centring test now *passes*
   against an implementation that does nothing, and the only failure is
   `test_a_cell_below_the_lap_gate_is_not_published` via arithmetic about Monaco that nobody
   would find by reading the name. Those two lines make the fixture behave like the
   regression, which centres over every level *including* the one the gate is about to drop.
   Without them the fixture arrives pre-centred on the survivors and the displacement the
   test exists to catch never happens.

   This is exactly how the test shipped in the first place, and it was caught by someone
   reading it rather than by running it. Restore both changes, then write down in one
   sentence what you would have to see before believing a green test protects anything.

## Check yourself

1. Where does Verstappen's −1.27 s at Bahrain come from, given that nobody ever fitted a
   model of driver skill?
2. An examiner says: "So you are claiming Verstappen is 1.1 seconds a lap better than the
   average driver." What is wrong with that sentence, and how does the config file
   pre-empt it?
3. The effects are already centred by the fit, and there is a test asserting they sum to
   zero. Explain how the published file was still displaced by 0.95 s a lap at one circuit.
4. Defend this design choice: `reset` draws twenty-two random offsets and then throws most
   of them away when a lineup is named, instead of only drawing the ones it needs.
5. Defend this design choice: the tyre-style standard error is clustered by stint, and the
   gate is a relative standard error rather than a minimum stint count.

---

### Answers

1. From the joint pace regression's driver fixed effects. The design matrix carries a
   drop-one dummy per driver so that fuel burn and track evolution are estimated within a
   driver rather than across them; the coefficient on that dummy is a per-driver lap-time
   offset in seconds, and it was always being computed — `t0_s` absorbed its mean and
   `sigma_driver_s` kept its standard deviation, and the vector itself was discarded. F17
   persists it, centred, with the lap count and seasons that produced it. No new model, no
   new data, one fewer thing thrown away.

2. **It is a seat effect, not a skill measurement: era 2024 pools 2022 to 2025, session
   fixed effects absorb per-session mean pace, so the coefficient is that driver's offset
   within their own sessions across whatever cars they drove — driver plus car, and the two
   are not separable from timing data.** The file states its own limitation three times over:
   the leaf is named `seat_pace_s` rather than `pace_s`, the header says "read these as SEAT
   effects", and every cell carries the seasons and lap count behind it, so the Monaco number
   visibly comes from 65 laps in 2025 while the Bahrain one comes from four seasons.

3. Centring and gating happened in that order on different sets. `_centred_effects` centres
   over every level in the design; the 30-lap publication gate then drops the thinnest cells.
   A level with one clean lap can carry an effect of tens of seconds — Suzuka era 2024 had
   one at +21.6 s — so the level most likely to be dropped is the one most likely to have set
   the centre. All 22 surviving cells were displaced by its share. The fit-level test could
   not see it, because at fit level the effects genuinely do sum to zero *with* the outlier
   included; the property that broke is one about the published subset, and
   `_recentre_published_columns` restores it by re-centring each circuit-era column on the
   cells that survived.

4. **Because a seeded generator's draw order is part of the seed: skipping the driver draw
   would shift every variate after it and silently change every seeded race in the repo —
   the frozen model's evaluation, the Stage B traces, all of F14 — while nothing appeared to
   break.** Drawing and overwriting costs 22 floats per reset and buys three properties:
   `drivers=None` stays byte-identical so F16's golden fixtures remain valid evidence, a
   named race is the same race as the unnamed race at that seed with people in it, and an
   unnamed seat falls back for free rather than needing a special case (which is also where
   zero would have been the wrong default, since a centred zero is the field average).

5. **Degradation residuals are correlated within a stint — a set that runs hot is slow for
   its whole life — so a lap-level standard error counts eighteen laps of one set as
   eighteen independent observations and comes out 2.3x too small at the era-2024 median,
   which is enough to walk a thin driver through any precision gate you would write.** The
   gate is a relative standard error rather than a count because counts do not bite here:
   the thinnest era-2024 driver has 12 stints and the median has 132, so a count-only gate
   would be theatre. Precision is the honest analogue of E-10's VIF — it asks whether the
   design pinned the number down, not whether rows arrived — and on the real fit it
   identifies 31 of 31 drivers in era 2024 and 15 of 22 in era 2026, refusing exactly where
   the data is thin. The count floor of 12 stays as a floor, and it does catch two era-2026
   reserve seats with good precision on almost no running.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| A nuisance parameter is a measurement | F17 | The joint fit's driver dummies exist so fuel and evolution are identified within a driver; their coefficients are per-driver lap-time offsets, and F17 persists them (with laps and seasons) instead of collapsing them into `t0_s` and `sigma_driver_s`. |
| Seat effect, not skill (era pooling) | F17 | Era 2024 pools 2022-2025 and session fixed effects absorb per-session pace, so a driver coefficient is driver-plus-car within their own sessions — hence the leaf name `seat_pace_s` and the per-cell seasons list. |
| Re-centre on the published set | F17 | A quantity centred on set A and published on subset B is only centred if you re-centre on B: one Suzuka driver with a single clean lap and a +21.6 s effect set the centre, was dropped by the 30-lap gate, and displaced all 22 published cells by −0.95 s (`_recentre_published_columns`). |
| Cluster-robust standard error | F17 | Sum the estimating equation within each `(session_id, stint)` group before squaring, because a set that runs hot is slow for its whole life; the lap-level error bar runs 2.3x small at the era-2024 median and would pass every driver through any precision gate. |
| Reparameterise until estimable | F17 | A per-driver degradation curve is not identifiable but a per-driver multiplier on the pooled curve is, and regressing the partial residual on the *predicted* degradation (not on age) makes one number pool across circuits whose `a` and `b` differ by an order of magnitude. |
| Draw, then overwrite | F17 | An optional feature stays stream-neutral by consuming the same variates and overwriting afterwards: `reset` draws all 22 offsets and replaces only named seats, so `drivers=None` is byte-identical and a named race is the same race with people in it (F16's draw-order rule applied). |
| Zero is not a neutral default | F17 | For a centred quantity, zero means "field average", and on a grid the average is quicker than most of it — so an unknown driver gets NaN and keeps their drawn offset rather than quietly becoming one of the best cars on the track. |
| Seeds that varied only the thing you removed | F17 | A twin replay is near-deterministic (trace events, zero lap noise, fitted pit service), so M2's five seeds per race were only ever varying the random driver draw; with seat pace fitted, nine of ten races are identical across all five seeds and each per-race delta is one number. |
