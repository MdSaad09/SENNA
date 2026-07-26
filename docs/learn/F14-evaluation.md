# F14 — The evaluation suite: M1–M11, confidence intervals, era-matched counterfactuals

## What we built and why

Everything before this feature built the thing. F14 is where we ask whether the thing is
any good, and answer in a form someone hostile can check.

The pit wall version: we take the frozen agent, put it in 480 races it has never seen,
against rivals tuned harder than the ones it trained on, and count. How many places does
it gain over the engineer's rule book? How close does it get to a strategist who can see
the whole race in advance? When a safety car comes out, does it make the call a
retrospective analysis says was right, and does it also stay out when staying out was
right? How much of the finishing position is the agent, and how much is the day it had?

The software version: a new `senna/eval/` package that rolls each battery, writes one
JSON per metric into a committed store, and a `make report` that turns that store into
the Chapter 7 tables without touching a model, a GPU or a database. Spec 5.12 defines the
eleven metrics. Its real design idea is that each metric ships with the way it can be
gamed or misread, because a target without its failure mode is a number pretending to be
evidence. Those notes live in `configs/eval.yaml` and travel into the report verbatim.

Two things went wrong during the build, and both are the reason evaluation code needs its
own tests. The oracle charged a flat pit loss no matter the track status, so a stop under
a safety car cost it about 12.7 s more than it should have at Bahrain, which would have
handed M3 a ceiling the agent could beat without deserving to. And a renamed event
(`barcelona_grand_prix` against `spanish_grand_prix`) had been quietly dropping a whole
held-out round out of the sim-to-real numbers since F03. Neither would have crashed
anything. Both would have flattered the results.

## New ideas in this feature

**Why a confidence interval, and what a bootstrap does.** The agent beat the baseline by
2.08 places on average over 480 races. Would it beat it by 2.08 on the next 480? No. The
sample mean is one draw from a distribution and you want to know how wide that
distribution is. The bootstrap is an almost embarrassingly simple way to find out. You
cannot re-run the season, so you fake re-running it: draw 480 races out of the hat with
replacement, 10,000 times, take the mean each time, and read the 2.5th and 97.5th
percentiles of those means. Lucky races sometimes appear twice and sometimes not at all,
and the wobble that creates is your estimate of sampling noise. The point estimate stays
the real sample's mean, never the average of the resamples, so changing the bootstrap seed
moves the interval and can never move the answer. 5.12's M1 target has two halves for
exactly this reason: the mean must clear +1.0 *and* the interval must exclude zero (A-06).

In the viva: "The bootstrap estimates sampling variability without assuming normality by
resampling the observed races with replacement and reading the percentiles of the
resampled means. The interval says how much the mean would move if we could rerun the
experiment; it says nothing about whether the simulator matches reality, which is M8's
job."

**The exact paired sign test, and declaring the bar first.** M2 has ten races. Ten. A
bootstrap at n=10 is decoration, so the primary claim there is the exact two-sided
binomial test on the *signs* of the ten deltas: forget the magnitudes, count wins. At n=10
you need 9 to clear p < 0.05, and the config recorded that before the first race was
rolled. The ordering matters, because a test picked after seeing the numbers is a test
picked to pass. Ties are dropped from the denominator rather than split, since a dead heat
is evidence for neither side.

**Precision and recall, and why recall alone is free.** M5 asks whether the agent uses
safety cars well. Frame each neutralisation window as a yes/no question: was pitting here
the better move? Recall is "of the windows where pitting was right, how many did the agent
take?" Precision is "of the windows where the agent pitted, how many should it have?" An
agent that pits under every single safety car has recall 1.0 by construction and has
demonstrated nothing. Its precision collapses instead. 5.12 replaced v2's single "SC
exploitation" number with the pair for that reason, and E-03 adds that VSC and SC are kept
apart end to end, since a discounted stop and a nearly-free stop are different
opportunities.

**The decision-timing rule.** This one is small and it changes the metric. In
`F1RaceEnv`, the action for lap L is chosen against the mask built at the end of lap L−1.
So a safety car deployed on lap 30 is first *visible* to the decision taken for lap 31. If
the agent happens to pit on lap 30, it decided that blind, before the safety car existed.
Grading that as a brilliant safety-car call would credit foresight it did not have.
Hence M5's published denominator: a window counts as one decision opportunity only if it
offers at least one informed lap. The same rule sets compound legality at pit entry, which
is why the oracle reads `trace.wetness[L-2]` and not `[L-1]` (E-08).

**Splicing an alternative future.** To ask "what if it had stayed out?", you replay the
same frozen race with just that decision changed and let the agent keep driving afterwards.
`ScriptedActions` from F06 holds station once its script runs out, which is right for
driving a twin to a branch point and wrong for everything after one: the alternative has
to keep racing to the flag. `SplicedPolicy` replays a fixed prefix then hands control back
to a live policy. The continuation is the agent's *own* policy on purpose. Re-optimising
the tail with full knowledge would grade the call by a perfect future, which is M3's
question, not M5's.

**Variance decomposition and the luck share.** M11 (A-08) asks how much of a finishing
position the race explains and how much the decisions do. Roll a grid: 20 event seeds per
circuit down the rows, 25 sampled-decision repetitions across the columns. If positions
within a row are all similar but rows differ a lot, the events dominate. If positions bounce
around within a row, the decisions do. Formally that is a one-way random-effects model and
the luck share is its intraclass correlation, between-seed variance over total variance.

Two honesty clauses ride with it. The served policy is deterministic, so a decision
distribution only exists if you sample the policy's own head instead of taking the argmax,
and mean head entropy is printed alongside so a reader can see how wide that probe was.
And because the env consumes randomness policy-dependently, a re-sampled decision also
meets different events downstream. That entangled variance is charged to the *decision*
side, which makes the published luck share a deliberate lower bound on what the event
draws explain. Overstating luck would flatter the novelty; understating it costs a
footnote.

**Era matching, and the confound it removes (F-24).** M2 replays 2023 and 2024 races.
Running the 2026-physics agent against them would compare two things at once: better
strategy and a different car. The agent would partly "win" because it has 350 kW of
electric power and half the fuel load, and an examiner would rightly ask which effect the
number measured. So the frozen headline is warm-started onto the 2024 constants for a
short Stage C fine-tune, and it is that model the counterfactuals run.

Already taught, one line each: trace pairing and the deterministic twin are F06 (ledger:
*Deterministic twin / EventTrace*), the served pair-job version is F13 (*Trace-donor
pairing*); the era switch itself is F05 (*Era switch (A-10)*); the frozen 2026 round split
is F03 (*Frozen train/validation split*); the DP oracle is F06.

## The code, guided

### `configs/eval.yaml` — targets and their failure modes in one file

Nothing in the suite hard-codes a bar. What is unusual is that every target is followed by
a `gaming_note` that the report prints word for word:

```yaml
m5:                                 # SC/VSC decision quality against the ex-post afterstate optimum
  precision_target: 0.75            # sourced 5.12 — "both at least 0.75"
  recall_target: 0.75               # sourced 5.12
  label_margin_s: 1.0               # stylised — a window counts as a real decision only when pitting and
                                    # staying out differ by more than this...
```

The margin is the interesting constant. Real signal here is about half a pit loss, roughly
5–12 s under a neutralisation, so 1.0 s sits far below signal but above tie-breaking dust.
Windows inside the band are excluded from both precision and recall *and* counted, because
a silent exclusion is a thumb on the scale.

The file also freezes the ten M2 races with a per-race rationale, before any of them were
rolled (plan decision 2: no race gets swapped out because the agent loses it), and the 23
circuits with genuine 2024 fits. Canada and France are absent on purpose: `build_scenario`
would hand them 2026 constants under an era-2024 label, which is exactly the lie the era
match exists to remove.

### `senna/eval/bootstrap.py` — the interval and the sign test

Six lines carry the whole idea:

```python
    rng = np.random.default_rng(seed)
    draws = rng.integers(sample.size, size=(resamples, sample.size))
    means = sample[draws].mean(axis=1)
    tail = (1.0 - level) / 2.0
    low, high = np.quantile(means, [tail, 1.0 - tail])
    return Interval(mean=float(sample.mean()), low=float(low), high=float(high), n=int(sample.size))
```

Line by line. `default_rng(seed)` makes the interval reproducible from the frozen report
seed, so a rerun regenerates the same table. `rng.integers(sample.size, size=(resamples,
n))` draws index positions, not values, which is what "with replacement" means in practice
and lets the whole thing be one vectorised gather. `sample[draws].mean(axis=1)` is 10,000
resampled means in one shot. `tail` splits the missing 5% evenly between both ends, giving
the percentile interval. And the returned `mean` is `sample.mean()`, the real one: the
resamples price the uncertainty and never touch the estimate.

Above it, an empty input raises rather than returning zeros, because "a confidence interval
over zero observations is not a claim".

The sign test:

```python
    wins = sum(1 for delta in values if delta > 0.0)
    losses = sum(1 for delta in values if delta < 0.0)
    ties = len(values) - wins - losses
    if wins + losses == 0:
        return SignTest(wins=wins, losses=losses, ties=ties, p_value=1.0)

    result = binomtest(wins, wins + losses, 0.5, alternative="two-sided")
```

The null hypothesis is a coin: under "the two strategies are equally good", each non-tied
race is a 50/50. `binomtest` computes the exact probability of a split at least this
lopsided, no normal approximation, which matters at n=10. Ties leave the denominator
entirely.

### `senna/eval/record.py` and `pairing.py` — the rollout substrate

Every eval race is rolled twice, and the reason is worth memorising:

```python
            agent = run_episode(live, policy, seed=seed, capture=True)
            try:
                trace = live.recorded_trace()
            except RuntimeError:
                excluded.append({"circuit": circuit, "seed": int(seed), "reason": "ego_dnf"})
```

The live roll is the deployment world: stochastic pace, drawn pit service, real
tyre-failure hazard. M4, M9 and M10 report on it, because they ask what the agent actually
does. Then `recorded_trace()` hands back the EventTrace and the same policy is replayed on
it with noise off. M3, M5 and M6 branch from that twin, because they ask what else the
agent could have done in *the same* race, and pricing an alternative against a noisy
baseline would price the noise. A race whose ego retired early has no usable trace (the
unseen tail would read as green), so it is dropped by name and counted.

`pairing.py` is M1's legs. The baseline records live, both legs twin-roll that recording,
and the *stored* baseline result is its own twin roll rather than its noisy run — so both
sides face identical deterministic physics and a policy paired against itself is a dead
tie. `band_robustness` runs the scripted baselines under both rival bands on the same
seeds, which is the only way a test-band agent result can be separated from "the opponents
simply got harder" (the debt F06 left open).

### `senna/eval/metrics.py` — the arithmetic that needs no simulator

M1 refuses to restate the sign convention:

```python
    outcomes = [
        pair_outcome(pair.agent_position, pair.agent_dnf,
                     pair.baseline_position, pair.baseline_dnf)
        for pair in pairs
    ]
```

`pair_outcome` is the F07 training gate's function: a finisher beats a DNF by the position
gap, both-DNF is no evidence, a tie counts against the agent. Reimplementing it here would
let the headline metric and the gate that promoted the model drift apart.

M4's loop is four lines of accounting with one rule in it:

```python
        for lap in race.laps:
            if lap["track_status"] in _NEUTRALISED:
                continue
            green_laps += 1
            deployed_mj += float(lap["deploy_mj"])
            budget_mj += float(race.e_dep_mj)
            derated += bool(lap["derated"])
```

Green laps only, because deployment behind a safety car is not a strategic choice and
counting it would let a lucky neutralisation move the number. `e_dep_mj` is the circuit's
per-lap deployment budget, so utilisation is deployed over available. Note there is no
per-lap deploy *cap* anywhere here: the 4 MJ figure is the battery's usable SOC window, not
a limit on deployment (F-02, taught in F12).

M9 counts races, not failures: `failed = sum(1 for race in races if any(lap["forced_pit"]
for lap in race.laps))`. A race that loses two tyres still counts once, because the
denominator is races per hundred.

M10 counts coerced actions and snapped stops separately. A snapped stop is legal but is not
what the policy asked for, so it still costs the set its clean badge.

### `senna/eval/afterstate.py` — windows and the splice

Window extraction is a run-length scan over `trace.status` with one exclusion:

```python
    windows, start, current = [], None, None
    for index, raw in enumerate(trace.status):
        status = _WINDOW_STATUS.get(int(raw))
        if status != current:
            if current is not None:
                windows.append(Window(status=current, first_lap=start, last_lap=index))
            start, current = index + 1, status
```

`_WINDOW_STATUS` maps only VSC and SC, so red never opens a window and, because the mapping
returns `None` for it, a red flag also *breaks* the runs on either side of it. Under red the
tyre change is free, a different mechanism from a discounted pit loss, and mixing them
would pollute the metric (E-04).

Then the timing rule, in one line:

```python
        return list(range(self.first_lap + 1, min(self.last_lap, last_completed_lap) + 1))
```

`first_lap + 1` because the onset lap was decided blind. `min(..., last_completed_lap)`
because a window running past the flag offers nothing. And the filter after the scan drops
any window with no informed lap: not an opportunity the agent declined, so not in the
denominator.

`SplicedPolicy.act` is four lines and does what its name says: serve the prefix, then
delegate.

### `senna/eval/sc_quality.py` — M5

Each variant rewrites the window's decisions on the realised action list:

```python
    variant = [action.copy() for action in actions]
    for lap in decision_laps:
        index = lap - 1
        if index < len(variant):
            variant[index][0] = 0  # hold station through the window by default
    if pit_lap is not None:
        variant[pit_lap - 1][0] = compound + 1  # pit head: 0 stay, else compound code + 1
```

Everything outside the window is untouched, so the comparison isolates the window. The
default clears every in-window stop (that is the stay-out leg), then one lap is set to pit
on one compound. `legal_codes_at` supplies the compounds the mask would have allowed at
that lap's pit entry, so no variant wins by doing something illegal.

The scoring block is a plain confusion matrix per status, and the shape of it is the whole
argument:

```python
        tp = sum(1 for v in rows if v["label"] == "pit" and v["agent_called_pit"])
        fp = sum(1 for v in rows if v["label"] == "stay" and v["agent_called_pit"])
        fn = sum(1 for v in rows if v["label"] == "pit" and not v["agent_called_pit"])
        tn = sum(1 for v in rows if v["label"] == "stay" and not v["agent_called_pit"])
```

`precision = tp/(tp+fp)` and `recall = tp/(tp+fn)`, computed per status key so SC and VSC
never pool. When the agent pitted in no window at all, `tp+fp` is zero and precision is
NaN rather than 0.0, which is the honest answer to "of the calls it made, how many were
right?" when it made none.

### `senna/eval/pit_accuracy.py` — M6

For each voluntary stop the sweep asks: could this stop have been better on another lap,
holding everything else fixed? The corridor is built first:

```python
    for candidate in range(max(previous_out + 1, 2), min(upper, n_laps + 1)):
        if candidate - previous_out - 1 > _cliff_cap(scenario, previous_compound):
            continue
        following = (next_out - candidate - 1 if next_out is not None
                     else n_laps - candidate)
        if following > _cliff_cap(scenario, compound):
            continue
        if code not in legal_codes_at(scenario, trace, candidate):
            continue
```

Bounded by the neighbouring stops, filtered so neither adjacent stint runs past its
compound's cliff (no candidate may bank on a tyre failure), and filtered again by pit-entry
legality. Each survivor is then rolled in full, not costed from the oracle's stint tables.
The tables are blind to the pit-loss discount under a neutralisation, to dirty air and to
the pit-lane FIFO, which is precisely the set of things that move an optimal stop lap.

Ties in the argmin are genuine, since the twin is deterministic, so all are returned and
the hit rule takes the *nearest*: grading against the further of two equally good laps
would penalise an agent that found the other one.

### `senna/strategy/oracle.py` — the two fixes

The first defect. `_plan_table_cost` used to charge `scenario.pit_loss_mean_s * len(plan.stops)`,
flat. The fix:

```python
def _pit_loss_at(scenario, status: int) -> float:
    mult = scenario.env["pit_loss_mult"]
    if status == events.SC:
        return scenario.pit_loss_mean_s * mult["sc"]
    if status == events.VSC:
        return scenario.pit_loss_mean_s * mult["vsc"]
    return scenario.pit_loss_mean_s
```

At Bahrain the mean pit loss is 25.359 s and the SC multiplier is 0.5 (E-03), so the old
code overpriced an SC stop by 12.68 s and a VSC stop by 8.88 s. On an event-rich trace that
pushes the genuinely best plans below the top-K roll cut, and the oracle then reports a
worse race time than it should. Since M3 is agent-minus-oracle, a weakened oracle makes the
agent look better. The direction of the bug is what makes it dangerous, and
`test_stage1_pit_charge_is_status_aware` now pins it: an SC-window stop must table-rank
above its green-shifted copy.

The second change is the wet extension. `enumerate_plans` used to take slicks only and
`solve_oracle` raised `NotImplementedError` on any wet trace. Now the compound offered at
each stop is whatever the mask would allow at pit entry, so a wet race enumerates
intermediates and wets and a dry race enumerates exactly what it always did.
`test_dry_enumeration_unchanged_by_the_wet_extension` pins that byte-identically, which is
how you extend a frozen component without silently changing the numbers it already
produced.

`oracle_regret.py` then does one careful thing: it enters the agent's own realised plan as
a contender in the oracle's search. That makes the oracle at least as good as the agent on
the pit dimension by construction, so a negative regret can only come from the energy
dimension, where the oracle schedules greedily per lap. Those negatives get reported, not
clipped: they are published assumption 4 becoming visible.

### `senna/eval/luck.py` — M11

The estimator is method of moments on a one-way random-effects model:

```python
    row_means = values.mean(axis=1)
    between_ms = n_reps * float(np.var(row_means, ddof=1)) if n_seeds > 1 else 0.0
    within_ms = float(np.mean(np.var(values, axis=1, ddof=1))) if n_reps > 1 else 0.0

    raw_between = (between_ms - within_ms) / n_reps
    between = max(0.0, raw_between)
    total = between + within_ms
```

Rows are event seeds, columns are decision repetitions. `within_ms` is the average spread
*inside* a row: same race, different decisions. `between_ms` is the spread of row means,
scaled by `n_reps` so the two are on the same footing, and it already contains a share of
within-row noise. Subtracting gives the pure between-seed component. That subtraction can
go negative when the true between-seed variance is near zero, which is sampling noise
rather than a finding, so it is clipped at zero and the clip is counted.

`share = between / total` is the intraclass correlation. Two degenerate cases are named
instead of swallowed: zero total variance gives NaN with `undefined_zero_variance`, and
zero within-row variance gives 1.0 flagged `degenerate_zero_within`. Circuits with a NaN
share are excluded from the headline mean with their flag kept, so an undefined split
cannot quietly read as zero luck.

`decision_seed(event_seed, rep, stream=173)` runs the three inputs through a `SeedSequence`
so neighbouring reps do not get neighbouring streams. Reps are nested inside event seeds,
never crossed with them: the same torch seed consumes its variates differently under a
different observation sequence, so "rep 3" names nothing shared across two races.

### `senna/eval/traces.py` — a real race as an EventTrace

M2 asks what the agent would have done with the team's own race in front of it. Replaying
the team's stops into a synthetic dry race asks something much easier, because the real
strategy stops looking like a response to anything. So the events come from ingested laps,
and each rule is origin-labelled.

Track status is the strict part:

```python
            state = _status_from_digits(track_status)
            if state is not None:
                index = to_sim(lap_number) - 1
                status[index] = max(status[index], state)
```

FastF1 digits map 4 → SC, 5 → RED, 6 and 7 → VSC (5.3.2), with 6 and 7 staying one state
because collapsing VSC into SC is the E-03 mistake. `max` across cars takes the worst state
anyone reported on that lap: a neutralisation is a property of the track, so one car's
missing digit must not erase it. `to_sim` rescales real lap numbers onto the sim distance.

Weather is the stylised part, and the code says so. The samples record whether it was
raining, not how wet the track was, so a rainfall flag sustained for
`m2.trace.wet_after_laps` laps targets full WET and anything shorter targets DAMP, with
wetness approaching the target through the same first-order integrator the env uses
(`level += (target - level) / n_sectors`). A synthesized crossover therefore sits where a
simulated one would, and the crossover lap it implies is the assumption the British GP
write-up owes (E-08). Tyre failures are all False and rival modes balanced, both stated:
neither is identifiable from timing data.

`_grid_order` compacts real grids, since penalties and withdrawals leave gaps: classified
starters keep their order, pit-lane starters fall behind them, and a short field is padded
with phantom cars that carry no stops. `require_native_era_fits` refuses any circuit whose
2024 scenario is really the 2026 fits wearing an era label. The pair loop that consumes
these traces is the remaining M2 wiring; it follows F13's donor convention.

### `finetune.py`, the era seam, and the suite plumbing

Block level, because none of it is new machinery. `overlay_configs` copies `configs/`,
rewrites Stage C's era, circuit list and budget, and hands the directory to the ordinary
`train_run` (F08's overlay trick). The overlay's bytes are what the fingerprint hashes, so
the fine-tuned checkpoint cannot collide with the headline's version and the configs it
trained under sit beside its weights.

The seam in `senna/train/` is one idea repeated: `era = stage_cfg.get("era", "2026")` in
`envs.py` and `run.py`, and `evals.py`'s module constant `_ERA` demoted to a `_DEFAULT_ERA`
with an `era=` keyword on every entry point. `run.py` also passes
`circuits=stage_cfg["circuits"]`, so an era-matched run is validated only on circuits it
trained. The committed `curriculum.yaml` never gains an `era` key, which
`test_committed_config_fingerprint_is_unchanged` pins: only an overlay opts in.

`splits.py` is thirty lines of refusal: `refuse_calibration_rounds` raises on any 2026
round in 1–6, naming the offenders, because scoring the agent on the rounds that calibrated
the generator is circular and the output would look fine (E-14). A companion AST test keeps
`senna/physics/synth/heldout.py` importable from exactly one module in the package.

`run_suite` rolls the recorded races once and reuses them across M3, M5 and M6. Each
battery writes one JSON through `store.write_metric`, which sorts keys, fixes the indent
and stamps an envelope of model versions, config hash, seeds fingerprint and git commit
(A-09), with no timestamps anywhere. `make report` then reads only that store, so
"deterministic given the run store" is checkable from a clone with no model, DB or GPU.
Figures use the Agg backend and `metadata={"Software": None}`, because matplotlib otherwise
stamps a creation date into the PNG and every committed figure would differ on every run.

### The Barcelona alias

`senna/physics/synth/validate.py` looked circuits up by their ingested slug. F1 renamed the
Circuit de Barcelona-Catalunya round for 2026, so `barcelona_grand_prix` stopped matching
the fitted `spanish_grand_prix`, `_mc_spec` returned `None`, and the log said "skipped".
Held-out round 7 had been missing from the sim-to-real numbers ever since, and nothing
failed. The fix is a `slug_aliases` block in `configs/synth.yaml` read through a
`_canonical()` helper, put in synth config rather than `circuits.yaml` so the training
fingerprint stays untouched.

### What the store says today

Read from `docs/results/F14/store/` on this branch. Four batteries have run the full
480-race bank. The rest (M3, M5, M6, M11 and the band table) are still at smoke grain, 2
circuits and 4 races, so treat them as wiring proof rather than results, and expect the
generated `docs/results/F14-evaluation.md` to disagree with the table below until the last
full run lands and the report is regenerated.

| Metric | Value | Status |
|---|---|---|
| M1 paired delta | +2.083 places, 95% CI [1.710, 2.475], n=480, finish-ahead 0.627 | target met |
| M4 energy | utilisation 0.649, derates 0.080 of 27,160 green laps | miss on both halves |
| M9 tyre failures | 37.29 per 100 races (179/480) | miss, target < 2.0 |
| M10 legality | 0 coerced actions, 0 snapped, 480 races | clean |

M1 clearing its bar with an interval well clear of zero is the headline. M9 at 37 per 100
is a real finding and the interesting kind: read jointly with M1, it says the agent is
buying position by stretching stints past the point where the cliff bites. That is a
strategy an evaluation suite is supposed to expose.

M8 is the documented miss. Held-out lap-time KS sits at 0.704 (Barcelona), 0.872 (Britain),
0.918 (Austria) and 0.946 (Belgium) against a 0.15 target
(`docs/synth/validation_summary.yaml`). The cause is in the F03 lesson: the T1/T2
point-mass transform's straight-line gain outweighs its corner loss, so it predicts 2026
laps roughly 4–6 s too fast, and two distributions that barely overlap drive KS toward 1.
E-14 forbids fixing it by refitting on the held-out rounds, because a generator tuned on
its own test set has no test set left. So the number ships with its mechanism attached.
That is validation doing its job. A sim-to-real suite that never reported a miss would be
telling you it cannot detect one.

## How it connects

```
  configs/seeds.yaml (480 test seeds)      models/headline (frozen triplet, F07)
  configs/eval.yaml  (targets + notes)     rival band "test" (E-06)
            |                                         |
            +--------------------+--------------------+
                                 v
                    senna/eval/record.py
             live roll  --->  EventTrace  --->  twin roll
                                 |
     +---------+---------+-------+------+-------------+-----------+
     v         v         v              v             v           v
  pairing   metrics   afterstate   oracle_regret    luck      band_check
   (M1)   (M4,7,9,10) (M5, M6)        (M3)          (M11)    (robustness)
     |         |         |              |             |           |
     +---------+---------+------+-------+-------------+-----------+
                                v
                   docs/results/F14/store/*.json      <- make suite
                                v
              make report -> docs/results/F14-evaluation.md + figures

  era branch:
  configs/eval.yaml era_finetune -> overlay configs -> train_run(Stage C, era 2024)
        -> models/era2024 -> serve/loader registry -> POST /counterfactuals
  ingested laps -> senna/eval/traces.py -> EventTrace with real events -> M2 pair
```

Inputs are the frozen model, the reserved seeds and the ingested 2023/24 races. Outputs are
JSON rows, a markdown table and three figures. Nothing here writes to the database, and
nothing in training can reach the test bank or the test band: `load_reserved_test_bank`
answers only to the consumer string `"F14"`, and `stage_venv` raises on any band but train.

## Try it yourself

1. **Prove the wiring.** Run `make suite SMOKE=1 ONLY=m1,m4` and then `make report`. Read
   `docs/results/F14-evaluation.md`. You'll know it worked when the table shows M1 over 4
   pairs with a wide interval, and the provenance block names the headline model version.

2. **Move a materiality threshold and predict first.** In `configs/eval.yaml`, change
   `m5.label_margin_s` from `1.0` to `30.0`. Before running anything, write down what you
   expect. Then `make suite SMOKE=1 ONLY=m5` and open
   `docs/results/F14/store/m5_windows.json`. You'll know it worked when almost every window
   carries `"label": "immaterial"` and the `excluded` block counts them, with precision and
   recall going NaN. Restore the 1.0 afterwards.

3. **Put both defects back and read the failures.** First, change `Window.decision_laps` in
   `senna/eval/afterstate.py` to start at `self.first_lap`, then run
   `.venv/bin/python -m pytest tests/eval/test_sc_quality.py -q`. Second, make `_pit_loss_at`
   in `senna/strategy/oracle.py` return `scenario.pit_loss_mean_s` unconditionally and run
   `.venv/bin/python -m pytest tests/strategy/test_oracle_wet.py -q`. You'll know it worked
   when `test_m5_onset_lap_pit_is_not_counted_as_a_call` fails on `assert not
   verdict["agent_called_pit"]` (a blind stop now scores as a safety-car call) and
   `test_stage1_pit_charge_is_status_aware` fails on the ranking assertion. For each, say in
   one sentence which direction the bug moves the metric.

4. **Add a CI to M9.** `tyre_failure_rate` in `senna/eval/metrics.py` returns a bare rate.
   Give it one: build a per-race 0/1 list and pass it to `share_interval` from
   `senna/eval/bootstrap.py` with the bootstrap config, then add the bounds to the returned
   dict and to `_m9` in `report.py`. Write the test first in `tests/eval/test_metrics.py`.
   You'll know it worked when the report's M9 row shows an interval and
   `.venv/bin/python -m pytest tests/eval -q` stays green.

5. **Watch the era overlay get built.** Run `make finetune DRY=1`, then read
   `models/overlays/era2024-s<seed>/curriculum.yaml` and diff Stage C against
   `configs/curriculum.yaml`. You'll know it worked when exactly four keys differ (era,
   circuits, budget_steps, eval_every_steps) and the run's `model_version` differs from the
   headline's. Note that the dry run still promotes its 256-step checkpoint to
   `models/era2024`, so move a real one aside first if you have already fine-tuned.

## Check yourself

1. Two policies get the same seed in the same env. Why are they not racing the same race,
   and what does F14 do instead?
2. What does M1's bootstrap interval tell you, and name one thing it definitely does not
   tell you.
3. An agent pits under every safety car. What does M5 report, and why is that not a pass?
4. The oracle used to charge a flat pit loss. Which way did that bias M3, and why is a
   bug that flatters the agent worse than one that punishes it?
5. Defend this: why fine-tune a separate 2024 model for the counterfactuals instead of just
   running the frozen 2026 headline against the 2024 races?

### Answers

1. `F1RaceEnv` consumes randomness policy-dependently: a tyre only rolls for failure once
   past its cliff, a stop only draws a service time when it happens. After the first
   different decision the two RNG streams are at different positions, so the events diverge
   and the "identical draws" a paired test assumes are fiction. F14 pairs on event traces
   instead (A-06): one leg records its race as an EventTrace, both legs then twin-roll that
   frozen trace, and a policy paired against itself is a dead tie by construction.

2. It tells you how much the mean of +2.083 places would move if you could rerun the
   experiment with a fresh draw of 480 races from the same setup, which is why 5.12 asks
   for the interval to exclude zero as well as the mean to clear +1.0. It tells you nothing
   about whether the simulator resembles reality, nothing about whether the rivals are
   realistic, and nothing about whether the metric is measuring what you think. Those are
   M8, the rival-band check and the gaming notes respectively.

3. Recall 1.0, precision at whatever fraction of windows genuinely called for a stop. 5.12
   requires both at 0.75, and the pair is reported per status type (E-03), so the
   always-pit strategy fails on precision immediately. Recall alone is gameable because the
   cost of a wrong pit never enters it.

4. It overpriced every plan that stops under a neutralisation (12.68 s per SC stop at
   Bahrain), which pushes genuinely good plans below the top-K roll cut and leaves the
   oracle reporting a slower best race. M3 is agent-minus-oracle, so a weakened oracle
   shrinks the reported regret and the agent looks closer to optimal than it is. A bug that
   punishes the agent gets found because someone investigates a disappointing number; a bug
   that flatters it gets written into a dissertation.

5. Because a 2026-physics agent racing a 2024 race is being compared on two axes at once:
   strategy quality and regulation change. Its 350 kW deployment and roughly 70 kg fuel
   load are not what the real strategist worked with, so any win is partly the car (F-24).
   The era-matched fine-tune (A-10, OQ-9's confirmed default) warm-starts the same policy
   onto the 2024 constants for a bounded Stage C run, so both legs of the counterfactual
   race the same physics and only the strategy differs. The honest fallback is stated too:
   if the fine-tune fails to beat the frozen headline on the 2024 validation banks, the
   run ships as `pending-F14` and the write-up names which model produced the numbers.

## Ledger update

| Concept | First taught in | One-line definition |
|---|---|---|
| Percentile bootstrap confidence interval (A-06) | F14 | Resample the observed races with replacement 10,000 times, take the 2.5/97.5 percentiles of the resampled means; the point estimate stays the real sample's mean, so the seed moves the interval and never the answer. |
| Exact paired sign test and the pre-registered bar | F14 | Binomial test on the signs of paired deltas with ties dropped from the denominator; M2's 9-of-10 threshold at alpha 0.05 is written into `configs/eval.yaml` before the first roll. |
| Precision and recall as an inseparable pair (E-03) | F14 | Recall alone is free (always-pit never misses an opportunity), so M5 reports both, per status type, with the denominator published. |
| Decision-timing rule (informed decision lap) | F14 | The action for lap L is chosen against the mask built at the end of lap L−1, so a stop on a neutralisation's onset lap was decided blind and is excluded from M5's denominator; pit-entry legality reads `trace.wetness[L-2]`. |
| Afterstate branching and SplicedPolicy | F14 | Replay a fixed prefix of the realised actions, change one decision, then hand the race back to the agent's own policy — the alternative keeps racing without being re-optimised with hindsight, which would be M3's question rather than M5's. |
| Coordinate-wise post-hoc optimum (information set) | F14 | M6's optimum is the argmin over feasible laps for one stop on the frozen trace, all other stops, compounds and energy actions held fixed; the 3-lap tolerance is the stated allowance for the search seeing a future the agent did not. |
| Variance decomposition / intraclass correlation (A-08) | F14 | One-way random-effects method of moments over an event-seed x decision-rep grid; luck share = between-seed variance over total, with entangled variance charged to the decision side so the published share is a conservative lower bound. |
| Era-matched fine-tune and the regulation confound (F-24) | F14 | Comparing a 2026-physics agent against 2024 races measures strategy and rule change at once, so the headline is warm-started onto the 2024 constants via a config overlay and it is that model the counterfactuals run. |
| Committed run store and the pure-function report (A-09) | F14 | One envelope-stamped JSON per metric under `docs/results/F14/store` with sorted keys and no timestamps; `make report` reads only that, so the Chapter 7 tables regenerate byte-identically from a clone with no model, DB or GPU. |
| Gaming notes as first-class config | F14 | Every 5.12 target in `configs/eval.yaml` carries the way it can be gamed or misread, and the report prints the note verbatim beside the number — a target without its failure mode is not evidence. |
