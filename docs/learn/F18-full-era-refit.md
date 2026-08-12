# F18 — refitting the physics on the whole era

## What we built and why

Every lap SENNA simulates starts from a number fitted off real laps: `t0_s`, the base lap
time at a circuit for that regulation era. Bahrain's said 98.597 s. It was fitted on 1,958
laps. There were 3,705 sitting in the database, and on all of them the answer is 99.465 s.
Nearly nine tenths of a second per lap, on the constant that anchors everything else.

The file that held that number, `configs/physics_params.yaml`, carried a line at the top
saying where its data came from:

```yaml
generated_at: "seasons 2022-2026, round 6"
```

That line was true about the database and false about the fit. Every declared season really
was ingested. The file even carries a `hazards` block for `french_grand_prix`, a race held
only in 2022, with race counts identical to the refitted file. So 2022 and 2023 laps did
reach the hazard, pit-loss and energy fitters. They reached none of the pace regressions.
The pace stage ran on two seasons and the watermark advertised five, and nothing anywhere
in the repo recorded the difference.

F18 refits the physics on all four era-2024 seasons, regenerates everything downstream
(the T1-T8 transforms, eleven training runs plus the era-matched fine-tune, two surrogate
explainers, the whole M1-M11 result store), and adds the guards that make the mistake
impossible to repeat quietly. The `physics_params.yaml` diff touches 1,065 lines. That
diff is the deliverable; the retrain is bookkeeping.

Two things came out of it that I did not expect and that are better teaching material than
the fix itself. More data exposed a confound rather than resolving one, at Austria, and it
nearly inverted the sign of a physical constant across two thirds of the simulator. And the
headline result got better while the most examinable result got materially worse.

## New ideas in this feature

**Provenance that lies.** The interpretability contract says every number names its origin.
F18 is the case where the origin was named and wrong, which is worse than blank. A blank
watermark makes you go and check. A confident one ends the conversation. The whole mechanism
is three lines in `run.py`:

```python
    def data_through(self) -> str:
        last_season = int(self.index["season"].max())
        last_round = int(self.index.loc[self.index["season"] == last_season, "round"].max())
        return f"seasons {int(self.index['season'].min())}-{last_season}, round {last_round}"
```

`self.index` is the circuit index, meaning what the store holds. Minimum season, maximum
season, last round. Nowhere in there is a question about what any fit consumed. The
watermark was computed from availability and read by everyone as scope, and both the
pre-refit and post-refit files say `"seasons 2022-2026, round 6"`: identical strings over
numbers that differ by 0.9 s/lap. The viva answer: **the file's provenance line described
the ingest, not the regression, so it was accurate about the wrong thing; that is why F18
added a gate at the regression layer and a test that reproduces the file from data rather
than trusting what it says about itself.**

**Presence versus participation.** E-12 is the completeness edge case, first met in F01 as
"is this season ingested". F18 needs it twice, at two layers.
`assert_season_coverage(declared, ingested)` asks whether the season is in the store.
`assert_pace_season_coverage(reached, index_seasons)` asks whether the regression actually
consumed it. Only the second one matches this defect: the first would have passed the
defective run without a word, because the store was complete. Mental model: a lecture
register that records who is enrolled versus who turned up. The pre-refit file was a class
list with half the seats empty and full attendance printed at the top.

**A cleaning rule, not a patch.** The pace regression's design matrix includes tyre age as
a regressor. FastF1's `TyreLife` is patchy on older seasons: 520 of 2022's 24,882 laps have
none, and 178 laps repo-wide are otherwise perfectly clean slick laps with a missing age.
Those arrived at LAPACK as NaN columns and killed the whole battery with `LinAlgError: SVD
did not converge` on the third circuit, which is the recorded reason the pace stage could
only ever run on the two seasons that happened not to contain them. The tempting fix is
`nan_to_num`: fill the hole with zero, move on. That is a lie about a lap, because zero age
means a brand new set. E-09 and the 5.3.4 table say exclude, count and report, like every
other cleaning rule.

**Separable is not the same as physical.** VIF and identification came up in F02: VIF asks
whether the design matrix can tell two regressors apart, and `identified: false` means the
data cannot distinguish fuel burn from track evolution. Austria's fuel VIF fell from 131.7
to 22.5 on the wider data, crossed the gate at 30, and reported a mass sensitivity of
**-0.007421 s/kg**. A negative `k_m` says a heavier car is faster. It was statistically
identified and physically impossible.

Unguarded, that number would have become era 2024's only identified circuit-era, so
`pool_k_m` would have pooled it alone, `run.py` would have stamped it onto every
unidentified circuit in the era in place of 2026's borrowed +0.011905, and `synth` would
have carried it into two thirds of `transforms.yaml` — every circuit with no native 2026
fit falls through to the 2024 entry. One circuit crossing one threshold flips the sign of
the mass model for the whole simulator. The viva answer: **VIF asks whether the design can
separate two effects; it cannot ask whether the answer means anything, so E-10
identification now requires a positive estimate as well as a separable design, and a
circuit that fails either test takes the pooled decomposition like any other weak fit —
the trend it does pin down is unaffected either way.**

**A fingerprint is over bytes, not behaviour.** F08 introduced config overlays whose bytes
make a run's fingerprint self-describing. The mechanic underneath it: `config.fingerprint`
is a sha256 over the raw bytes of eleven named config files, in order. `fits.yaml` is one
of them. Adding two booleans to it moved the fingerprint from `e823d1b5a2ea` to
`70098e9d3425`, so every trained artifact recorded a preimage that no longer existed and
had to be retrained. Nothing in the environment reads either boolean. About two hours of
compute to change no number.

Which produced the accident. Eleven runs, trained twice under different fingerprints,
returned identical scores — not close, identical to the last float digit
(6.3549999999999995, 4.418333333333334, and the rest), with seed 331 promoted at step
1,769,472 both times. Nobody designed that check, and it is the strongest determinism
evidence in the project.

**Reporting a result that got worse.** M1 (paired position gain against the engineered
baseline) went from +2.083 to +2.279 places over the same 480 paired seeds. M2 — the exact
paired sign test against replayed real strategies, taught in F14, with its 9-of-10 bar
pre-registered in `configs/eval.yaml` before the first roll — went from 4W/5L/1T at p=1.000
to 1W/8L/1T at p=0.039, mean -3.66 places. The agent now reliably loses to what the real
teams did. On the old physics it did not lose significantly. The old reading, "competitive
with elite humans", was not a finding; it was an inconclusive test at n=10 being read
generously. Better physics converted an absence of evidence into evidence of a gap, and a
gap you can point at is worth more than a wash you have to hedge.

## The code, guided

### `configs/fits.yaml` — the gates, declared

Both gates are config, not code, because a constant that only exists in a Python file is
one nobody can find. Both are tagged `operational`, the fourth provenance origin from F10.

```yaml
gates:
  require_full_season_coverage: true  # operational — refuse to write physics_params.yaml
                                      # from a store missing a season configs/ingest.yaml
                                      # declares (E-12) ...
  require_finite_params: true         # operational — refuse NaN and Inf as well as null
```

The header above them says the only reason to run with either off: setting a gate false
reproduces the pre-F18 battery, which is how the defect was demonstrated rather than
argued.

### `senna/physics/fits/gate.py` — the two questions

```python
def assert_pace_season_coverage(reached: dict[str, set[int]], index_seasons: dict[str, set[int]]
                                ) -> None:
    for era in sorted(index_seasons):
        seen = reached.get(era, set())
        missing = sorted(index_seasons[era] - seen)
        if missing:
            raise IncompletePaceCoverageError(...)
```

Four lines, and each one is doing something. `reached` is built by the battery as it fits, a
set of seasons per era that actually entered a pace regression. `index_seasons` is what the
store holds per era. The loop is `sorted` so the error message is deterministic, which
matters because that message gets pasted into an issue. The comparison is set difference
rather than a count: **1,958 laps looks like a healthy sample, and that is exactly how a
whole missing season stays invisible.**
Per era, not over one flat season list, because 2026 is its own era and legitimately holds
one season; a flat check would fire on every correct run.

The docstring carries the rule that stops this crying wolf: a season contributing to no
circuit at all is the failure, one circuit skipped for want of dry slick laps is ordinary
and stays quiet. A gate that fires on normal wet years gets switched off within a month.

### `senna/physics/fits/run.py` — where each gate is consulted

```python
            if not narrowed and config.get(fits_cfg, "gates.require_full_season_coverage"):
                assert_season_coverage(seasons, sorted(index["season"].unique().tolist()))
```

This sits immediately after the circuit index is read and before any fitting, because
`_run_energy` streams four seasons of FastF1 telemetry and nobody should wait through that
to be told 2022 never landed. `not narrowed` is load-bearing: `--only` and `--circuit` runs
read a smaller index by design and never write the yaml, so they must not trip a gate about
the full artifact.

The second gate sits at the write, because it needs results that only exist after fitting:

```python
        if config.get(fits_cfg, "gates.require_full_season_coverage"):
            assert_pace_season_coverage(
                battery.pace_seasons,
                {era: set(rows["season"].astype(int))
                 for era, rows in index.groupby("era")},
            )
        validate_complete(
            params, require_finite=config.get(fits_cfg, "gates.require_finite_params")
        )
        validate_origins(params)
        text = render_params(params, generated_at=battery.data_through())
        args.params_out.write_text(text)
```

Read the order. Coverage, then completeness, then provenance tags, then render, then write.
`validate_complete` now refuses NaN and Inf as well as null, because it only ever tested
`is None` and a NaN is not None, so a failed fit would have rendered the bare literal `nan`
into the yaml for F05 to load back as a float that poisons every lap it touches. Every
refusal happens before `write_text`, so a failed run leaves no artifact, and three tests in
`test_coverage_gate.py` assert exactly that with `assert not params_out.exists()`.

`battery.pace_seasons` is filled in one place, in the joint-pace loop:

```python
                self.pace_seasons.setdefault(era, set()).update(
                    int(s) for s in laps["season"].unique()
                )
```

after the empty-frame skip, so a circuit that contributes nothing contributes nothing to
the coverage claim either.

### `senna/physics/fits/joint_pace.py` — the clean mask

```python
    usable = (
        laps["is_green"]
        & laps["is_accurate"]
        & laps["lap_time_s"].notna()
        & laps["pit_in_time_s"].isna()
        & laps["pit_out_time_s"].isna()
    )
    has_age = laps["tyre_life"].notna()
    return usable & has_age, int((usable & ~has_age).sum())
```

`is_green` keeps safety-car and red-flag laps out, since they are not racing pace.
`is_accurate` is FastF1's own timing-quality flag. `lap_time_s.notna()` because the
regression's target cannot be missing. The two pit columns drop in-laps and out-laps, which
carry pit-lane time rather than lap pace. `has_age` is the new line, and the reason it
belongs is narrow and worth memorising: **`tyre_life` is a regressor in this function's own
design matrix, not merely a column on the frame.** The function returns the count alongside
the mask so the exclusion is a number someone can look up, not a smaller `n` nobody
notices.

Both callers use this identical mask, and that is a correctness requirement rather than
tidiness. `age_partial_residuals` feeds the degradation fitter, and a lap present in one
frame and absent from the other would silently misattribute the age term (partial
residuals, F02).

### `senna/physics/fits/joint_pace.py` — separable, then physical

```python
    separable = bool(np.isfinite(vif_fuel) and vif_fuel <= vif_max and rank == len(names))
    identified = bool(separable and k_m_ols is not None and k_m_ols > 0.0)
```

Two lines carry the whole argument. `separable` is the old E-10 test: a finite VIF under the
configured ceiling of 30, and a full-rank design. `identified` adds one clause,
`k_m_ols > 0.0`. Nothing is thrown away — `k_m_ols_s_per_kg` keeps the raw negative estimate
on the fit object for the notebook's diagnostic. It just may not be published as an
attribution.

The same principle guards the pool one level up:

```python
    pooled = float(np.sum(weights * values) / np.sum(weights))
    if pooled <= 0.0:
        return None
```

Inverse-variance pooling (F02) is minimum-variance for unbiased inputs, so a negative pool
is not a small number that rounds away. Returning `None` hands the era back to the fallback
an unidentified era already uses, and a borrowed number with the right sign beats an own
number that is impossible.

`test_a_single_confounded_circuit_cannot_invert_the_era` pins the interesting middle case:
one confounded circuit at -0.0074 and two healthy ones at 0.0119 and 0.0131 still pool, to
0.008883, because the healthy weight drags the mean down without taking it through zero.
That literal is pinned rather than asserted as "is None or > 0", which the contract makes
true either way and so could never fail.

### `tests/physics/fits/test_refit_reproduces_committed.py` — the only guard that caught it

```python
def test_refit_reproduces_the_committed_params(ingested_store, tmp_path):
    refitted = tmp_path / "physics_params.yaml"
    run.main(["--params-out", str(refitted)])

    produced = refitted.read_text()
    committed = COMMITTED_PARAMS.read_text()
    if produced == committed:
        return
```

Restore the snapshot, run the fit, compare bytes. That is the A-09 promise stated as an
executable claim instead of a paragraph in a runbook, and it works only because
`params_writer` is byte-deterministic (F02: sorted keys, shortest-repr floats, a data
watermark instead of a clock). Both coverage gates would have passed the run that produced
the defective file. This one was red on `main` by construction.

The failure path is deliberate:

```python
    diff = difflib.unified_diff(
        committed.splitlines(), produced.splitlines(), "committed", "refitted", n=1, lineterm=""
    )
```

A whole-file assert dumps two thousand lines and teaches nothing. The first divergence names
the circuit and the constant, which is where the investigation starts. The test also skips
rather than fails on a cold FastF1 cache or an empty database, because a test that blames
the fitters for the operator's missing cache gets ignored.

## How it connects

F18 does not add a box to the 5.1 diagram. It re-runs the first one and everything
downstream of it.

```
   ingested laps (F01, Postgres)
            |
            v
   [ fits battery ]  <-- gates: season coverage, pace coverage, finite, origins
            |
            v
   configs/physics_params.yaml  ---- byte-identity round-trip test (A-09)
            |
            v
   make synth -> configs/transforms.yaml + physics_2026 c_lc/c_atk/p_der
            |
            v
   F1RaceEnv  ->  make headline / ablate / finetune  ->  models/*
            |                                              |
            |                                              v
            |                                    make explain -> surrogates, 14,460 cards
            v
   make eval -> docs/results/F14/store/*.json -> make report -> Chapter 7
```

Every arrow is a stage that reads the previous stage's committed artifact, which is why a
mistake at `fit` only becomes visible at `eval` hours later, and why the plan's instruction
was to read the fit diff before spending any compute.

What the era bought, read out of that diff as the spec required: seven degradation curves
that did not exist before (Azerbaijan SOFT in both eras, Canada's full set, France HARD and
MEDIUM, all circuits raced only in 2022 and 2023), native curves 85 to 91, circuits with
native era-2024 fits 23 to 25. What it did not buy: E-10 identification did not move at all,
and T5 cluster transfers went 53 to 54 rather than down. Both contradict the spec's stated
expectation, and both are in the record anyway.

## Try it yourself

1. **Read the defect out of git.** Pull Bahrain's era-2024 pace block from both versions:

   ```
   git show main:configs/physics_params.yaml | awk '/^  bahrain_grand_prix:/{f=1} \
     f&&/joint_pace/{p=1} p{print} p&&/vif_fuel/{exit}'
   ```

   then the same `awk` over `configs/physics_params.yaml` on this branch. Four numbers moved:
   `n_laps` 1958 to 3705, `t0_s` 98.597 to 99.465, `sigma_driver_s` 0.5653 to 0.6571,
   `vif_fuel` 395.7 to 75.9. Now `head -4` both files. You'll know it worked when the
   `generated_at` line is byte-identical across a 0.9 s/lap change, which is the whole lesson
   in two commands.

2. **Count the results the spec expected to move.** `grep -c "identified: true"` and
   `grep -c "cluster transfer (T5)"` on both versions of `configs/physics_params.yaml`. You'll
   know it worked when you get 1 and 106 on `main` against 1 and 108 now — identification
   unchanged, transfers up by one curve, both against expectation.

3. **Break the cleaning rule.** Delete `& has_age` from the return of `_clean_mask` in
   `senna/physics/fits/joint_pace.py` and run
   `pytest tests/physics/fits/test_tyre_age_cleaning.py`. You'll know it worked when
   `test_a_frame_of_only_ageless_laps_raises_rather_than_fitting_nothing` fails on the
   message assertion rather than the exception type: numpy's `LinAlgError` is itself a
   `ValueError`, so the type proves nothing and only the words "SVD did not converge"
   come back. That is the failure an operator got before F18. Revert.

4. **Break the physicality guard.** Remove the `if pooled <= 0.0: return None` block from
   `pool_k_m` and run `pytest tests/physics/fits/test_joint_pace.py`. Two go red —
   `test_a_non_positive_pooled_k_m_is_refused` and
   `test_a_single_confounded_circuit_cannot_invert_the_era` — and note that `-k pool` finds
   only the first, because the second is named after the consequence rather than the
   function. Then read `senna/physics/synth/run.py:253-258` and write down, in one sentence,
   how a negative pool at one circuit reaches `transforms.yaml` for circuits that were never
   raced in 2022. You'll know it worked when your sentence mentions the fallback chain: the
   circuit's own 2026 fit, then its 2024 fit, then the pool.

5. **Recompute a fingerprint, then move it on purpose.** Run

   ```
   .venv/bin/python -c "import json; from senna import config; \
     m = json.load(open('models/headline/manifest.json')); \
     print(config.fingerprint(m['config_files'])[:12], m['fingerprint'][:12])"
   ```

   The manifest names its own preimage, so this recomputes what the model was trained
   under from the configs on disk. You'll know it worked when both halves read
   `70098e9d3425` — the property `main` never had, where committed configs hashed to
   `2368883a49c5` against a recorded `6b6edb78d84e`. Now append a blank comment line to
   `configs/fits.yaml`, rerun, and watch the two disagree after changing nothing the
   environment reads. Revert, confirm they match again, and you have reproduced the
   accidental determinism experiment in miniature.

## Check yourself

1. The pre-refit `physics_params.yaml` claimed `seasons 2022-2026`, and that claim was
   literally true of the database. So what exactly was wrong with it?
2. You have two coverage gates. Which one would have caught this defect, and what does the
   other one actually protect against?
3. Austria's fuel coefficient was statistically identified — VIF 22.5, comfortably under
   the gate at 30. Defend refusing it. Is that not discarding evidence you dislike?
4. Why is a lap with no tyre age excluded rather than filled with zero, and where is the
   cost of that rule recorded?
5. M2 moved from an inconclusive p=1.000 to a significant p=0.039 against the agent.
   Defend publishing that instead of the earlier number.

## Answers

1. The line described the ingest, not the regression. It was rendered by `data_through()`
   from `self.index`, the store's circuit index, so it recorded availability while every
   reader took it as scope. The pace regressions consumed 2024 and 2025 only. Wrong
   provenance is worse than none, because a blank field prompts a check and a confident one
   closes the question — and there is no code line reading "2024 and 2025 only" to grep for,
   which is precisely why the byte-identity round-trip test is the guard that found it.

2. `assert_pace_season_coverage` is the matching gate: it compares the seasons that entered
   a pace fit against the seasons the store holds for that era, per era.
   `assert_season_coverage` protects against a genuinely partial ingest — a season declared
   in `configs/ingest.yaml` and absent from the store — and it would have passed the
   defective run without a word, which the module docstring now says out loud. It earns its
   place anyway, and it runs before the battery rather than after, because waiting through
   four seasons of FastF1 telemetry to be told 2022 never landed is a bad afternoon.

3. **The VIF gate answers whether the design matrix can separate fuel mass from track
   evolution, and it said yes at Austria. It cannot answer whether the separated estimate is
   physically admissible, and -0.007421 s/kg says a heavier car laps faster, which no
   amount of statistical identification makes true.** Nothing is discarded: the raw estimate
   stays on the fit object as `k_m_ols_s_per_kg` for the diagnostic notebook, and the
   circuit still publishes the combined trend it does pin down. Only the attribution is
   withheld, and the circuit takes the pooled decomposition like any other weak fit. The
   stake was concrete — unguarded, that one circuit becomes era 2024's sole identified fit,
   sets the era pool, and inverts the mass transform for two thirds of `transforms.yaml`.

4. Because tyre age is a regressor in that regression's own design matrix, so a lap without
   one carries no information about the term being fitted, and zero-filling asserts a fact
   that is false (a fresh set). E-09 and the 5.3.4 table say cleaning rules exclude, count
   and report, so `_clean_mask` returns the count as `n_excluded_no_tyre_age`, the fit log
   prints it per circuit, and the committed per-season quality reports carry the row — 2022
   has 520 of 24,882 laps with no age, the 2.1% the spec cites. It is deliberately not
   written into `physics_params.yaml`: a diagnostic in the constants file would be a
   diagnostic pretending to be a constant.

5. **The bar was pre-registered in `configs/eval.yaml` before the first roll, so the test
   was chosen for the question rather than for the answer, and reporting only the flattering
   run of it would make every other number in the chapter unreadable.** The earlier 4W/5L/1T
   at p=1.000 was never a finding of parity; it was a failure to reject at n=10, and it was
   being read as "competitive with elite humans". Better physics turned an absence of
   evidence into evidence of a gap, mean -3.66 places with CI [-5.82, -1.16], and the README
   and INDEX carry both figures side by side so the change is auditable. It also sits beside
   M5's VSC recall coming off zero — ten calls, none of them wrong, where the old physics
   produced none at all — which is the same honesty working in the other direction.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| Provenance that lies | F18 | A watermark rendered from availability (`data_through()` reads the store's circuit index) while readers take it as fit scope: identical strings over numbers 0.9 s/lap apart, and worse than a blank field because a confident origin ends the check. |
| Presence vs participation gates (E-12, two layers) | F18 | `assert_season_coverage` asks whether a declared season is in the store; `assert_pace_season_coverage` asks whether the regression consumed it — only the second matches the F18 defect, and it compares sets per era because a healthy-looking `n` is how a missing season hides. |
| A regressor gates its own clean mask (E-09) | F18 | `tyre_life` earns a line in `_clean_mask` because it is a column in that fit's design matrix; the lap is excluded, counted (`n_excluded_no_tyre_age`) and reported in the quality report, never `nan_to_num`'d into a false fresh set. |
| Separable is not physical (E-10) | F18 | Identification now requires `k_m_ols > 0.0` as well as a VIF under the gate, and `pool_k_m` refuses a non-positive pool — Austria passed VIF at 22.5 with -0.007421 s/kg and would have inverted the mass transform for two thirds of `transforms.yaml`. |
| Byte-identity round-trip on a fitted artifact (A-09) | F18 | `make fit` over the frozen snapshot must render `physics_params.yaml` byte-for-byte; the only guard that caught a file whose recorded scope and actual scope disagreed, and it works only because the writer is deterministic (F02). |
| Fingerprint over bytes, not behaviour | F18 | `config.fingerprint` is a sha256 over eleven config files' raw bytes, so two booleans nothing reads moved it `e823d1b5a2ea` to `70098e9d3425` and forced a retrain — which returned eleven runs identical to the last float digit, the project's strongest determinism evidence. |
| Absence of evidence vs evidence of a gap | F18 | M2's 4W/5L/1T at p=1.000 was a failure to reject at n=10 being read as parity; the refit made it 1W/8L/1T at p=0.039, and publishing the worse number against a pre-registered bar is what makes the rest of the chapter readable. |
