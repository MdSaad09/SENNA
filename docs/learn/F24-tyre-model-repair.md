# F24 — the tyres were free

## What we built and why

This one started in the dashboard, not in a test. Watching run 491 in the live view:
the agent pits on lap 3, takes softs, and then never stops again. Fifty-five laps on
one set, to P2. No strategist would do that, because a soft that old is a cliff waiting
to happen. Our simulator disagreed, so the diagnosis went to the tyre model.

The finding: 37 of the 145 fitted degradation curves in `configs/physics_params.yaml`
were stored with `a = 0.0`. The degradation model is `grip(age) = 1 − a·age^b` (F02),
fitted with scipy's `curve_fit` under an `a >= 0` bound. On a circuit where the age
residuals are flat — too little running, too much noise — the optimiser slides downhill
into the bound and stops there. That zero was then serialised as if it were a
measurement. Zero amplitude means zero wear at any age. The 2026 soft was free at
nearly every circuit, all three compounds were free at Canada, and the T5 ratio
transfer spread the zeros to circuits that had never seen a 2026 race. The trained
policy found the exploit, because that is what policies do: M9 (tyre failures per 100
races, bar of 2) measured it at 37.9.

F24 fixes it in five layers and then pays the full price of the fix. A fit is
`identified` only when its predicted wear over its own observed ages clears a noise
floor, and a parameter pinned at a `curve_fit` bound is never identified. Unidentified
fits are repaired from a ladder — a pooled per-compound refit over every circuit, then
the other era's pooled curve — with every substitution labelled. A fit that is neither
identified nor repaired is never written as a curve. `build_scenario` refuses to serve
a zero-wear slick even if one somehow reaches the file. And the T5 transfer now demands
identified curves on both ends, after a review found it laundering borrowed amplitudes
(more on that below, because it forced a second retrain).

Then the headline was retrained from scratch, three seeds, unchanged curriculum,
everything downstream re-rolled, and M1–M11 re-run against the unchanged bars. M9 went
37.9 to 0. M1 went +2.28 to +1.79 places — smaller, still over the bar, and the shrink
is honest: part of the old margin was bought with tyres that never wore. M2 against the
real teams' strategies went from losing 8 of 10 (F18's sobering number) to 3W/2L/5T, a
wash. And the agent's whole habit inverted, from pit-lap-3-then-never-stop to mid-window
stops that respond in the right direction to every degradation perturbation we throw at
them.

## New ideas in this feature

**Bound-clipping as silent failure.** F02 taught identifiability versus noise, and F18
taught that a separable fit can still be unphysical (Austria's negative `k_m`). This is
the third face of E-10: an optimiser pinned at a constraint has not answered your
question, it has refused to. `curve_fit` with `a >= 0` and flat residuals returns the
closest legal point to the answer it wanted, which is the boundary. Mental model: ask
someone's age, accept only non-negative numbers, and they hand you 0 — that is not a
newborn, that is your form rejecting their answer. The smallest example is in the tests:
zero-mean noise over ages 1–25 fits to `a ≈ 1e-10`, and only the identification rule
knows that number is a refusal.

**Signal floors.** "This tyre does not wear" and "this data cannot see wear" are
different claims, and a point estimate cannot tell them apart. The floor makes the
distinction operational: the curve's predicted lap-time delta at its own maximum
observed age must exceed half the circuit's clean-lap sigma (`s_ref_s`), or the fit is
unidentified. Half a sigma because below that the whole predicted effect fits inside
ordinary lap noise over the range the data covers — the fit is not wrong, it is
uninformative, and E-10 says you report that rather than a number. It is the same move
as a detection limit in a lab: below the limit you say "not detected", never "zero".

**Repair ladders with named rungs, and a write gate.** When the local estimate fails,
fall back to a better-fed estimator, and record which rung you landed on. Rung one is
the pooled per-compound refit over every circuit's residuals at once (the soft may be
unidentifiable at any single circuit and still perfectly measurable across 25 of them).
Rung two is the other era's pooled curve. Rung three is refusal: no rung held, so the
fit stays unidentified and the write gate declines to serialise it as a curve — the
compound is simply absent from the file, and absence is what the F-16 mask already
knows how to handle (F08's `UNFITTED_COMPOUND` reason). The precedent is `_pool_k_m`'s
cross-era borrow from F18, generalised and made mandatory. The provenance contract does
the rest: `source: pooled` or `source: prior_cross_era` on every substituted row,
forever.

**Provenance laundering through derived values.** A labelled substitution can lose its
label the moment something derives from it. The T5 transfer computes
`a_2026 = a_2024_target × (donor_2026_a / donor_2024_a)`; run that ratio through a
*repaired* 2024 target and the output carries the pooled curve's borrowed amplitude
wearing a `source_circuit: <donor>` label — the borrowing is laundered behind a
respectable name. The subagent review caught exactly this after the first retrain
(Qatar MEDIUM and Saudi HARD in the first emission), and the fix — the transfer now
requires an identified target as well as identified donors — forced a second full
retrain-and-eval loop. Worth remembering when the reviews feel slow: this one paid for
the whole battery.

**The agent as an adversarial auditor.** F08 taught reward hacking: a policy maximises
the written reward, not the intent. F24 is the same failure one layer down — the reward
was fine, the *physics* had a defect, and four million training steps of gradient
ascent found it the way a fuzzer finds a buffer overflow. Two consequences. First, an
RL agent's weirdest habit is a diagnostic: run 491 was a free audit report, read off
the UI. Second, the only honest fix is refit-plus-retrain. The frozen policy's weights
encode "tyres are free" in every layer; patching around it (masking long stints,
penalising old tyres) would leave a policy optimised for a world that no longer exists,
fighting its own guardrails. You fix the world, then you let the agent re-learn it.

## The code, guided

### senna/physics/fits/degradation.py

The degradation fitter, which F02 built and F24 made honest. It still refuses poisoned
input outright (`_refuse_poisoned` raises on in/out or inaccurate laps, E-09 — taught
in F02), and it still fits `a·age^b` on the joint fit's partial residuals. What changed
is the dataclass and the `identified` rule. This is core domain logic, so line by line.

```python
@dataclass(frozen=True)
class DegradationFit:
    a: float  # grip loss per age^b, as a fraction of t0 (grip(age) = 1 - a*age^b)
    b: float
    n_laps: int
    max_age_seen: int
    low_confidence: bool
    # False means the data could not measure wear over the ages it covers — a
    # statement about the data, never a measurement of zero wear (E-10, F24)
    identified: bool
```

`identified` joins `low_confidence` rather than replacing it because they answer
different questions: `low_confidence` is the thinness gate (few laps, few stints),
`identified` is the signal gate. A fit can be thick and still see nothing.

The heart of `fit_degradation`, per compound:

```python
        max_age = int(age.max())
        fits[str(compound)] = DegradationFit(
            a=float(amplitude_s) / t0_s,  # seconds of delta over t0 = fractional grip loss
            b=float(exponent),
            ...
            identified=(
                float(amplitude_s) * max_age ** float(exponent) >= signal_floor_s
                and not _pinned(float(exponent), bounds[0][1], bounds[1][1])
            ),
        )
```

Take the `identified` expression apart, because every piece has a reason:

- `amplitude_s * max_age ** exponent` is the curve's own prediction of total lap-time
  delta at the oldest age this data actually contains. It asks the fit "over the range
  you saw, how much wear do you claim?" — a claim the data could in principle check.
- `>= signal_floor_s` is the noise floor, passed in by the caller as
  `0.5 × s_ref_s` (the circuit's clean-lap sigma). Below it, the claimed effect
  drowns in ordinary lap noise, so it is not a measurement.
- There is deliberately no `a == 0` test. Two reasons, both in the inline comment:
  scipy's trust-region solver lands at roughly `1e-10`, not exactly `0.0`, so an
  equality check misses the clip — while `1e-10 × anything` fails the floor
  arithmetically. The floor catches the amplitude pin as a side effect of catching
  everything uninformative.
- `not _pinned(exponent, ...)` handles the *other* parameter. An exponent stuck at
  either bound (0.3 or 3.0) is the same refusal in a place the floor cannot see — a
  pinned `b` with a healthy `a` can clear the floor while still being the optimiser
  giving up. `_pinned` is a tolerance comparison (`abs(value - bound) <= 1e-6`),
  because floats near a bound are the whole problem here.

`fit_pooled_degradation` is rung one of the ladder — one curve per compound over every
circuit's residuals at once:

```python
    for compound, rows in frac_residuals.groupby("compound"):
        age = rows["tyre_life"].to_numpy(dtype=float)
        frac = rows["frac_residual"].to_numpy(dtype=float)
        (a, b), _ = curve_fit(
            lambda x, a_, b_: a_ * x**b_, age, frac, p0=p0, bounds=bounds, maxfev=maxfev
        )
```

The one design decision that makes pooling legal is the units: `frac_residual` is
`pace_residual_s / t0_s`, so an 80 s Austria lap and a 105 s Singapore lap contribute
comparable numbers, and the fitted `a` comes out t0-free — which is exactly what lets
it stand in at any circuit. The pooled fit skips the thinness gates (`low_confidence`
stays False; a 25-circuit pool is never thin) but keeps the signal floor and the pin
test: a pooled curve that cannot see wear either is refused the same way, which is what
rung two exists for.

`repair_degradation` walks every circuit-era and substitutes:

```python
        for compound, fit in compounds.items():
            if fit.identified:
                continue
            rung = pooled_curve_for(era, compound, pooled_by_era)
            if rung is None:
                continue
            source, donor = rung
            out[compound] = replace(fit, a=donor.a, b=donor.b, low_confidence=True)
            sources[(slug, era, compound)] = source
```

- `if fit.identified: continue` — identified fits are never touched, and the tests pin
  that (the identified neighbour comes back unchanged, no source invented for it).
- `if rung is None: continue` — no rung held, so the fit *stays unidentified* rather
  than being promoted to any curve. Refusal is a legal terminal state; the write gate
  and the scenario backstop are downstream to handle it.
- `replace(fit, a=donor.a, b=donor.b, low_confidence=True)` — borrow only the shape.
  The circuit keeps its own `n_laps` and `max_age_seen`, because the tyre-failure cliff
  (`cliff_age_laps`, F12's one-rule-two-callers function) is "a few laps past where
  *this circuit's* data ran out". A borrowed curve at Monaco says how fast grip fades;
  it says nothing about how long a set has ever survived there. `low_confidence=True`
  because a substitution must advertise itself even to a reader who never checks the
  sources dict.
- `sources[(slug, era, compound)] = source` — the substitution record, and *only*
  substitutions: the dict is exactly the diff the repair made, which is what the params
  writer turns into per-row provenance.

`pooled_curve_for` encodes the ladder's order: the era's own pooled curve if
identified, else the first identified cross-era pooled curve (`sorted` so the walk is
deterministic), else `None`.

### senna/physics/fits/run.py

The battery orchestrator (F02/F18). Three F24 blocks, treated at block level.

`_repair_degradation` runs immediately after the per-circuit fits and *before*
`tyre_style` and `clusters`, so every downstream consumer reads repaired values —
ordering is the whole reason it lives where it does. It assembles the fractional
residual pool per era, sets the pooled floor to the **median** of the per-circuit
floors (one pooled curve cannot honour 25 different sigmas; the median resists the
outlier circuits), and pre-computes `_transfer_horizon` from
`obs.tyre_age_norm_laps` — a transferred curve has no observed ages, so its
signal-floor probe uses the fallback horizon its cliff will actually use in the sim.
Then it calls the two functions above and logs every substitution
(`degradation repair <slug>/<era> <compound> <- pooled`).

The transfer gate in `_transfer_missing_2026` is the review's fingerprint. The comments
carry the history, which is why I quote them:

```python
                # F24: a donor must have measured wear in both eras — a repaired
                # (pooled-substituted) fit may race, but it may not donate; ratio
                # transfer through an unidentified curve just launders the clip
                donors = [...]
                # the target must be identified too, not merely a > 0: a repaired
                # 2024 fit carries a borrowed pooled amplitude, and ratio transfer
                # through it would launder that borrowing behind a source_circuit
                # label (F24 review blocker — qatar MEDIUM and saudi HARD did
                # exactly this in the first emission)
```

Both ends of the T5 ratio must be identified: donors, because a pool of zeros transfers
zero; the target, because of the laundering. And the transferred curve then faces the
same signal floor over the fallback horizon — Las Vegas HARD came out of a legitimate
ratio at 0.01 s over its whole cliff horizon, a free tyre by an entirely different
route. A transfer that fails the floor falls to the pooled curve; no pooled curve, and
the compound is left unfitted for the mask (F-16).

The write gate in `_put_degradation` is the last line of the fitting side:

```python
            if not fit.identified and source is None:
                # the F24 write gate: a bound-clip is never serialised as a curve.
                log.info("degradation %s/%s %s: unidentified and unrepaired — not written", ...)
                continue
```

Two adjacent details earn a sentence each. Amplitudes are written at 10 decimal places
instead of the file's usual 6, because a real cliff-shaped curve (tiny `a`, `b` near 3)
truncates at 6 dp back to the very zero this feature repairs. And an era block is never
written empty: `build_scenario`'s era fallback treats a falsy block as absent, so an
empty 2026 dict would silently hand a 2026 race the 2024 curves.

### senna/env/scenario.py

`build_scenario` is the last gate between the params file and the F-16 mask, so the
backstop lives here. Line by line:

```python
    allow_zero_deg = bool(config.get(envc, "race.allow_zero_deg_compounds"))
```

The escape hatch exists for one directory: `tests/env/fixtures/pinned_configs`, where
the F16 golden photograph must keep serving the world exactly as it ran — free tyres
included. F16 taught behaviour-identity refactors: the fixture is evidence *because*
it is frozen, so you preserve the old behaviour by config rather than re-recording the
fixture under new physics, which would prove nothing. Everywhere else the flag is
false, with the provenance comment saying so.

```python
    available = tuple(
        c for c in SLICKS
        if c in deg and (allow_zero_deg or float(deg[c]["a"]) > 0.0)
    )
```

`c in deg` is the old rule — the write gate means an unrepaired compound simply is not
in the file. `float(deg[c]["a"]) > 0.0` is the backstop behind the gate: even if a zero
reaches the file (hand edit, stale artifact), it never reaches
`available_compounds`, and `available_compounds` is what the mask serves. A tyre the
menu does not list is a tyre the agent cannot select, by construction.

```python
    min_dry = int(config.get(envc, "race.min_dry_compounds"))
    if len(available) < min_dry:
        raise ValueError(...)
```

The two-compound rule (F-20) needs at least two dry compounds servable; below that the
race is unsatisfiable, so refuse it by name rather than serve a race the rules cannot
be met in. The `2` was an inline literal before F24 — the interpretability contract
says an inline constant is a defect, so it moved to `configs/env.yaml` with its F-20
citation.

```python
    if START_COMPOUND not in available:
        raise ValueError(...)
```

Every car launches on MEDIUM (the 5.5 grid rule), and `dynamics` falls back to the
hardest fitted curve for an unfitted compound — so a race whose grid compound was just
refused would run lap 1 on exactly the physics the guard above rejected. Refusing the
race is the only answer that does not smuggle the zero back in through the start grid.

### The configs

`configs/fits.yaml` carries `signal_floor_frac_of_s_ref: 0.5`, tagged `operational`
with the full rationale in the comment (under half the clean-lap sigma is
indistinguishable from lap noise; below it the fit is stored unidentified and
repaired — never serialised as a zero, "the run-491 defect"). `configs/env.yaml` adds
the `race:` block: `min_dry_compounds: 2` tagged `sourced` against F-20, and
`allow_zero_deg_compounds: false` tagged `operational` with the pinned-configs
exception named. Note what changing the floor costs: `fits.yaml` is in the
fingerprint's eleven files (F18), so editing it invalidates every trained artifact.

### senna/eval/archetypes.py

`fit_provenance` classifies each circuit's 2026 tyre model by how much of it is its
own, so the M1/M3 slices can be read against data quality. F24 added the `repaired`
class between `calibrated` and `synthesised`, and the ordering inside the function is
load-bearing: repaired rows are `low_confidence` *by construction* (the substitution
marks itself), so the source check must run before the low-confidence check or every
repaired circuit would reclassify as `unusable`. `repaired` also demands the circuit's
own laps under every compound — an all-pooled-fallback block has zero own data and is
`synthesised` by any honest reading. The docstring records the uncomfortable truth
plainly: since F24 no 2026 circuit is `calibrated`, because the soft's wear was
unidentifiable everywhere, even pooled — and saying so is the class's job.

### The tests

`tests/physics/fits/test_deg_repair.py` was written before the implementation (tests
first) and pins each rung: a bound-clip on synthetic zero-mean noise is stored
unidentified; planted wear above the floor stays identified; the pooled refit recovers
wear planted across three different `t0` circuits (which only works because the pool is
fractional); each ladder rung records its source string; and — the one that matters
most — when nothing is identified the fit comes back *unchanged and unidentified*, for
the backstop to refuse.

`tests/env/test_scenario_guards.py` holds the env side. The fixture plants its own
zeros on a copy of the live configs, because the repair scrubbed the committed ones —
a test that trusted the file would go vacuous the day the file got healthy (F14's
vacuous-test lesson, applied). `test_no_free_tyres_property` is run 491 as an
invariant over the committed configs: everything `build_scenario` actually serves has
real wear on every slick, refusals are legal outcomes, and a canary
(`served >= 20`) stops the property going vacuous if a bug made the guard refuse
everything. `test_australia_2026_soft_wears_at_age_55` is run 491 by name, and it
asserts a *strategy-sized* delta (over 0.5 s at age 55), because `a = 1e-10` satisfies
`> 0` and satisfies nothing else.

## How it connects

```
laps (F01) ──> joint pace fit ──partial residuals──> fit_degradation
                                                          │ identified?
                                    no ──> repair ladder: pooled ──> cross-era ──> refuse
                                                          │  (source label on every rung)
                    write gate (_put_degradation) ──> physics_params.yaml
                                                          │
                 T5 transfer (identified donors AND target, floor-checked)
                                                          │
              build_scenario backstop: no zero-wear slicks, F-20 min, grid compound
                                                          │
              available_compounds ──> F-16 action mask ──> MaskablePPO retrain (F07)
                                                          │
              M1–M11 vs unchanged bars (M9: 37.9 → 0)     fit_provenance → M1/M3 slices
```

Five layers between a flat residual and the agent's action space, each one sufficient
on its own for the specific failure it guards. The pre-repair result store is archived
at `docs/results/F14-pre-repair/` so the before/after comparison stays reproducible
(A-09).

## Try it yourself

1. **Move the floor.** In `configs/fits.yaml`, drop `signal_floor_frac_of_s_ref` from
   `0.5` to `0.1` and predict what changes: fits whose predicted delta sat between 0.1
   and 0.5 sigma flip to identified, so fewer `degradation repair` substitutions. Run
   `python -m senna.physics.fits.run --only joint_pace,degradation` (narrowed, so no
   yaml is written) and compare the count of `degradation repair ... <- pooled` log
   lines against a run at 0.5. Revert before committing — this file is in the
   fingerprint, and F18 documents what an idle byte change costs. You'll know it
   worked when the repair count drops and the run ends without writing params.

2. **Break the guard in two layers.** Hand-edit `configs/physics_params.yaml`: set
   Bahrain 2026 SOFT's `a` to `0.0`. Run
   `pytest tests/env/test_scenario_guards.py` — everything stays green, because the
   backstop quietly drops SOFT from the menu and two compounds still satisfy F-20.
   Now flip `race.allow_zero_deg_compounds` to `true` in `configs/env.yaml` and rerun:
   `test_no_free_tyres_property` goes red and names the exact
   `(bahrain_grand_prix, 2026, SOFT)` triple. Predict before trying: what happens if
   you zero MEDIUM instead of SOFT with the flag still false? (The grid-compound
   refusal fires and Bahrain refuses to build at all.) Revert both files. You'll know
   it worked when you have seen one zero absorbed silently and the same zero caught
   loudly, and you can say which layer did each.

3. **Audit the write gate's contract.** One-liner against the committed file: load
   `configs/physics_params.yaml` and check that every degradation row with
   `identified: false` carries a `source` key — the write gate promises no
   unidentified, unrepaired row exists. Then `grep -n prior_cross_era
   configs/physics_params.yaml` to see which compounds had to cross eras. You'll know
   it worked when the audit finds zero violations and you can name the cross-era rows.

4. **Classify the calendar.** Import `fit_provenance` from `senna/eval/archetypes.py`,
   feed it the loaded params for every circuit, and tally the classes. Predict first:
   no circuit is `calibrated`, and the E-14 calibration rounds land in `repaired`.
   You'll know it worked when your tally matches the table in
   `docs/results/archetypes.md`.

## Check yourself

1. The `identified` rule never compares `a` to `0.0`. Give both reasons.
2. `repair_degradation` borrows the donor's `a` and `b` but keeps the circuit's own
   `max_age_seen`. What breaks if the donor's age range came along too?
3. Defend this design choice to an examiner: why is a zero-wear compound removed from
   the action mask (and the race refused when too few compounds remain) rather than
   discouraged with a reward penalty for over-long stints?
4. Defend this one too: the fix retrained the headline from scratch. Why not fine-tune
   the frozen policy on the repaired physics, at a fraction of the compute?
5. The first retrain shipped Qatar MEDIUM and Saudi HARD with `source_circuit` labels,
   and the review rejected both. What was wrong, and why did requiring identified
   *donors* not prevent it?

## Ledger update

| Concept | First taught in | One-line definition |
|---|---|---|
| Bound-clipping as silent failure (E-10) | F24 | An optimiser pinned at a constraint has refused to answer, not answered zero; scipy lands at ~1e-10, so the check is a predicted-effect floor plus a bound-proximity test, never `== 0`. |
| Signal floor (no effect vs effect below noise) | F24 | A fit is `identified` only if its predicted delta over its own observed ages clears half the circuit's clean-lap sigma; below that the honest statement is "not detected", never "zero". |
| Repair ladder with named rungs and a write gate | F24 | Unidentified fits fall to the pooled per-compound refit (fractional units), then the other era's pool, then refusal — every substitution labels its `source`, and an unrepaired fit is never serialised as a curve. |
| Provenance laundering through derived values | F24 | A ratio transfer through a repaired target re-emits a borrowed pooled amplitude under a `source_circuit` label, so T5 now requires identified curves on both ends and floors the result — the review blocker that forced the second retrain. |
| The agent as adversarial auditor (refit and retrain, never patch) | F24 | Gradient ascent finds physics defects the way it finds reward bugs (run 491, M9 37.9/100), so a weird habit is a diagnostic and the fix is repairing the world and retraining in it — a patched policy still encodes the broken world in its weights. |

---

## Answers

1. First, the clip never lands exactly on `0.0`: scipy's trust-region solver stops at
   roughly `1e-10`, so an equality test misses every real clip. Second, the equality
   test asks the wrong question even when it works — the failure mode is "effect
   indistinguishable from noise over the observed range", which also covers tiny
   non-clipped amplitudes and (via the separate `_pinned` check on `b`) an exponent
   stuck at its bound. The floor on predicted delta at `max_age_seen` answers the right
   question and catches the amplitude clip arithmetically for free.

2. The cliff. `cliff_age_laps` is a margin past the compound's `max_age_seen`, meaning
   "a few laps beyond where this circuit's data ran out, failure hazard engages". A
   donor pool's `max_age_seen` reflects the longest stints anywhere, so importing it
   would push Monaco's failure cliff out to ages Monaco has never evidenced — the
   borrowed curve says how fast grip fades, the local ages say how long a set has been
   seen to survive, and the repair deliberately keeps those claims separate.

3. Viva answer: compliance in SENNA is architectural, not economic — action masks plus
   physics clipping give 100% legality by construction (F-16), and F08 showed
   empirically that a penalty is a price a sufficiently rewarded policy will pay. A
   zero-wear compound is a data defect, not a sporting rule, so there is no correct
   fine for it (F08's data-limit versus sporting-rule distinction): the compound must
   be structurally unselectable, and where the menu falls below F-20's two dry
   compounds the race itself is unsatisfiable and refusing it loudly is the only
   answer that cannot be gamed.

4. Viva answer: the defect was in the training environment, so "tyres are free" is
   baked into the frozen policy's value estimates and habits at every layer, and a
   fine-tune starts from — and tends to preserve — exactly those priors, leaving open
   whether residual behaviour is strategy or fossilised exploit. Retraining from
   scratch under the repaired physics with the curriculum and bars unchanged makes the
   comparison clean: whatever survives (M1 +1.79) was earned in the honest world, and
   whatever vanished (part of the old +2.28, the lap-3 habit) is thereby shown to have
   been the exploit. The era-matched fine-tune (F14) is different in kind: there the
   base physics is trusted and only the regulation constants move.

5. Both rows were ratio transfers computed through a *repaired* 2024 target: the
   target's `a` was itself a pooled substitution, so the "transferred" amplitude was
   the pooled curve's, re-emitted under a `source_circuit` label that claimed
   circuit-specific measurement — laundering, because the borrowing disappeared from
   the provenance. The donor gate could not catch it because the donors genuinely were
   identified in both eras; the defect entered through the other operand of the ratio.
   The fix requires `target_2024.identified` as well, and floors the transferred curve
   over its fallback horizon so a legitimate ratio cannot shrink a real curve into a
   free tyre by another route.
