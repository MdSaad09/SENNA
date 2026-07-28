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

Two more turned up in the review pass, and they are a different species. Four of the tests
written for this feature passed while the behaviour they claimed to pin was deleted. And
the ingested database had been erased by the test suite three times, twice in one session,
despite `.env.example` having politely asked it not to be since F01. Neither of those is
about Formula 1. Both are about the gap between writing a rule down and enforcing it, and
they are the parts of this feature most worth carrying into anything you build after it.

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

**A written convention is not a guard.** `.env.example` had carried this since F01: the DB
tests drop and recreate every table, so point them at their own database, never at the
ingested one. The ingested database got erased anyway. Three times, twice in one session.
Rewording the comment would not have helped, because a rule whose only enforcement is a
reader's attention has no enforcement at all. So the rule moved into
code that runs whether or not anyone read anything, and it lives in `senna/data/db.py`
rather than in the test tree because it is a property of the database, not of pytest:
dropping every table is safe on a database someone has declared disposable and on no other.

The escape hatch is the examinable part. A guard with no override gets commented out by
whoever is in a hurry, so there has to be one, and its shape decides whether it protects
anything. `SENNA_ALLOW_DESTRUCTIVE_DB=1` would be a blanket yes, and a blanket yes is the
kind of thing that gets exported once in a terminal and is still set forty minutes later
when the full suite runs. This one takes the database's name instead:
`SENNA_ALLOW_DESTRUCTIVE_DB=senna` authorises `senna` and nothing else. The operator has to
type out the thing they are about to destroy, which is a small ritual that makes the
dangerous case feel dangerous.

In the viva: "The guard is on the database because the invariant is about the database.
The override names its target rather than setting a flag, so authorisation cannot outlive
the operation it was granted for."

**Knowing whether a test tests anything.** A green test is evidence about your code only if
it would have gone red without it. That is not automatic, and nothing in pytest checks it.
The four vacuous tests in this feature all looked plausible. One compared
`Path(store)/"smoke"` against `Path(store)` and asserted they differ, which is true for
every possible value of `store` and stays true with the branch it was guarding deleted.
One called `build_report` twice in the same process and asserted the strings matched,
which cannot detect the exact bug it was written for, because Python's string hash salt is
fixed for the life of a process. One listed three module names and grepped them for a
call, which by construction cannot notice the fourth module that forgets it. One asserted a
key exists in `configs/eval.yaml` without checking anything reads it.

The technique that catches all four is one sentence long: break the code on purpose and
confirm the test goes red. Delete the branch, re-inject the bug, then run the test. If it
still passes, the test is decoration. This is mutation testing done by hand, and at the
scale of one review it is quicker to do than to set a tool up for. Worth building the habit
now: all four of these had been sitting in the suite looking like coverage.

There is a second question to ask once a test does go red, and one of the fixes here failed
it: what did the test *do* on its way to failing? A regression test for the database guard
was written to point at the production database and call the real drop, so it reported the
regression accurately and erased the store while doing so. Red at the right moment is not
the same as safe. Both cases are worked through below.

In the viva: "I verify a test by re-introducing the defect it claims to catch and watching
it fail. Four tests in the evaluation suite passed against deliberately broken code, which
is how I found they were asserting tautologies rather than behaviour."

**The sensitivity run as a paired experiment.** Config overlays are F08 (ledger: *Config
overlays and the write-ahead run ledger*). What is new here is using one to answer a regulatory
question the frozen model cannot be retrained for. The FIA cut maximum permitted recharge
to 7 MJ in April 2026, after the headline was trained at the 8.5 MJ baseline (E-02). You
cannot edit `configs/circuits.yaml` to find out what that costs, because the served
triplet's manifest records that file's fingerprint and the edit would invalidate every
number in the chapter. So the newer figure runs against a throwaway copy of `configs/` in a
temp directory, and both arms roll the same seeds.

The design point worth defending: both arms build an overlay, including the one that just
reproduces the committed value. Reusing the base configs for the trained arm would be one
fewer copy and one real hazard, because the moment a circuit's committed cap already
equalled the refined figure, the two arms would become the same run and the report would
print a measured null result.

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

One more accumulator runs beside those, and it changes how the miss reads:

```python
            deliverable_mj += min(
                float(race.e_dep_mj),
                float(lap["soc_mj"]) + intra_lap_share * float(lap["harvest_mj"]),
            )
```

What the store held at the start of the lap plus the share of this lap's harvest that
arrives in time to be spent, capped at the budget. At several circuits `e_dep_mj` exceeds
what the battery can physically deliver, so 5.12's 0.90 bar is unreachable there by
construction. Reporting only `utilisation` would let that read as an agent declining to
deploy. The suite publishes both: 0.649 of budget, against an attainable ceiling of 0.914,
which is 0.710 of what was actually available. Still a miss, but a smaller and more
specific one.

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
2024 scenario is really the 2026 fits wearing an era label.

### `senna/eval/harness.py` — the M2 pair loop

This is the module that turns those traces into the counterfactual result. It reads a real
race out of Postgres (three SQL statements: laps, weather, grid), builds the trace, and
races two policies through it.

The ego column is chosen by reordering the drivers:

```python
    ordered = {driver: inputs.laps_by_driver[driver],
               **{d: rows for d, rows in inputs.laps_by_driver.items() if d != driver}}
```

Car 0 is the ego in `F1RaceEnv`, so the counterfactualled driver has to be first. Every
other car keeps its own real stops and becomes traffic the agent has to deal with, which is
the whole point: replaying Verstappen's Bahrain with the other 19 cars scripted to their
real strategies is a much harder question than a synthetic field.

Then the pair, four lines:

```python
        env = F1RaceEnv(circuit, era, twin=trace, configs_dir=configs_dir)
        baseline_policy = RealStrategyReplay(real_plan, scenario, replay_cfg)
        baseline = run_episode(env, baseline_policy, seed=int(seed))
        agent = run_episode(env, policy, seed=int(seed))
```

Same env, same trace, same seed, two policies. `twin=trace` is what makes the pairing real
rather than approximate (A-06). `RealStrategyReplay` is F06's scripted baseline holding the
driver's actual stop laps and compounds, extracted by `plan_from_rows` and rescaled onto the
sim's lap count. `policy` is the era-matched model, not the 2026 headline, because otherwise
this measures the regulation change (F-24).

One honesty line rides in the stored row:

```python
            "snapped_stops": baseline_policy.snapped,
```

A real stop the mask had to move (a compound not legal at that pit entry, say) makes the
replay a weaker opponent than the strategy the team actually ran, so the count travels with
the result instead of being absorbed into it (A-07). Across the ten races it is 25 snapped
stops, which is not nothing and is stated in the report.

The module's docstring names a deliberate duplication: `worker/jobs.py` answers the same
question for the dashboard, but it is wired to Postgres job rows, Redis and frame
persistence. The dozen lines that matter here are the two legs and the trace they share, so
they are re-implemented rather than imported, and the offline battery runs without a queue.

`summarise` states the statistics in order of authority: `paired_sign_test` first as the
claim, `mean_interval` second with `"ci_note": "descriptive only: a bootstrap over ten
races is not a claim"` written into the payload beside it.

### `finetune.py`, the era seam, and the suite plumbing

Block level, because none of it is new machinery. `overlay_configs` copies `configs/`,
rewrites Stage C's era, circuit list and budget, and hands the directory to the ordinary
`train_run` (F08's overlay trick). The overlay's bytes are what the fingerprint hashes, so
the fine-tuned checkpoint cannot collide with the headline's version and the configs it
trained under sit beside its weights.

The run has happened, and its number is the most quotable thing in the feature.
`senna-ppo-db031aead155-C-02211840` (seed 331, warm-started from the headline, 2.21M Stage C
steps on the 2024 constants) scores **6.336 mean points** on the 2024 validation banks. The
frozen 2026 headline, on the same banks, scores **3.802**. That gap is the F-24 confound
measured rather than argued about: roughly two and a half points of a 2026 agent's apparent
performance on 2024 races is the car, not the strategy. Before this run, "era matching
matters" was a plausible claim in a plan document. Now it has a size, and any examiner who
asks why you bothered gets a number instead of an argument.

Read the direction carefully. 6.336 > 3.802 means the era-matched model does *better* in
the 2024 world, which is what you would expect from a policy adapted to the car it is
driving. The confound would have shown up in M2 as an agent that looked good or bad partly
because of its power unit. Removing it is why M2's honest wash (below) can be reported as a
strategy result at all.

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

### `senna/eval/sensitivity.py` — what a 7 MJ cap costs the frozen agent

The overlay builder is six lines and the comment in its docstring is the contract: a copy
of the configs with every circuit's harvest cap rewritten, nothing else moved, so a diff of
the overlay is the complete statement of the counterfactual. The tests hold it to that,
including one that reads `configs/circuits.yaml` before and after and asserts the bytes are
unchanged.

The arms loop is the part to read line by line:

```python
    with tempfile.TemporaryDirectory() as scratch:
        for label, h_max_mj in (("trained", baseline_mj), ("refined", float(block["h_max_mj"]))):
            overlay = overlay_configs(base_dir=base_dir, dest=Path(scratch) / label,
                                      h_max_mj=h_max_mj)
            races, excluded = record.record_eval_races(policy, banks=banks,
                                                       configs_dir=overlay)
            dropped[label] = {(row["circuit"], row["seed"]) for row in excluded}
```

`TemporaryDirectory` because an overlay is scratch by definition and a committed one would
eventually be edited by someone who thought it was real config. The tuple names both arms
explicitly, so `baseline_mj` is read from the committed configs rather than assumed to be
8.5. Each arm gets `Path(scratch) / label`, its own directory keyed by the arm rather than
by the value, which is the review fix. The earlier version read `base_dir` directly for the
arm whose cap already matched, so the day a circuit's committed cap equalled the refined
figure, both arms would run the same configs and the report would print an identical pair
of rows as a measured null result. Same `banks` for both, so the comparison is paired by
construction. `dropped` collects retirements as a set of `(circuit, seed)` keys, which sets
up the check after the loop:

```python
    if dropped["trained"] != dropped["refined"]:
        raise ValueError(
            f"the arms dropped different races (trained {sorted(dropped['trained'])}, "
            f"refined {sorted(dropped['refined'])}) — the comparison is no longer paired"
        )
```

If a race survives under one cap and retires under the other, the two arms are averaging
over different race sets and the delta is no longer a delta. Raising is right here: there is
no honest way to report a number produced that way, so there is no reason to let the run
finish.

`trained_cap` refuses a bank spanning two different committed caps. It used to read
`next(iter(banks))`, the first circuit's value, and AR-05 permits per-event harvest values,
so a mixed bank has no single trained cap and labelling the arm by whichever circuit
iterated first would be a quiet lie in a table header. Now it collects the set and raises if
there is more than one, telling you to narrow `--circuits` or report per circuit.

The result, over 24 circuits at 5 seeds each (120 races per arm):

| Cap | Utilisation | Attainable ceiling | Derate share | Mean finish |
|---|---|---|---|---|
| trained, 8.5 MJ | 0.648 | 0.914 | 0.078 | P4.81 |
| refined, 7.0 MJ | 0.627 | 0.819 | 0.182 | P4.94 |

The agent loses 0.13 places on average while its derate share more than doubles, 0.078 to
0.182. The mechanism is visible in the ceiling column: a tighter harvest cap lowers what the
battery could physically deliver per lap from 0.914 of the deployment budget to 0.819, so
the same policy asking for the same deployment hits the floor of the store more often. It
keeps its results and pays for them in derates, which is what operating closer to a limit
looks like.

The `reading` string is written into the payload rather than into the report's prose, and
the report prints it verbatim:

```python
        "reading": (
            f"the frozen agent's robustness under a {block['h_max_mj']} MJ cap, not what a "
            f"model re-optimised for {block['h_max_mj']} MJ would do — ..."
        ),
```

That distinction is the whole claim. This measures how a policy trained at 8.5 copes when
the rule changes under it. It does not measure how good a 7 MJ agent could be, which would
need a retrain and would be a different question. Conflating them would let a robustness
result read as a regulation-compliance claim.

`_sensitivity_section` in `report.py` derives every clause of its sentence from the payload,
including the direction words:

```python
    verb = "costs" if places > 0 else ("gains" if places < 0 else "moves")
    derate_clause = ("runs out of energy more often" if derate > 0
                     else "derates less often" if derate < 0
                     else "derates at the same rate")
    if refined_mj < trained_mj:
        direction, reading = "Tightening", "operating closer to a limit"
    elif refined_mj > trained_mj:
        direction, reading = "Loosening", "operating with more headroom"
    else:
        direction, reading = "Holding", "the two arms carrying the same cap"
```

A higher finishing position is a worse one, so even the verb has to read a sign rather than
assume it. This got two passes. The first still ended with the fixed clause "the agent keeps
its results but ... which is what operating closer to a limit looks like", which is a
hard-coded verdict: false at three places lost, and self-contradictory if the cap ever
loosened and the derate share fell. A fixed sentence beside a generated table is one config
edit away from contradicting it, and in a chapter built on the idea that a number carries its
honest reading, that is the worst defect available.

### The Barcelona alias

`senna/physics/synth/validate.py` looked circuits up by their ingested slug. F1 renamed the
Circuit de Barcelona-Catalunya round for 2026, so `barcelona_grand_prix` stopped matching
the fitted `spanish_grand_prix`, `_mc_spec` returned `None`, and the log said "skipped".
Held-out round 7 had been missing from the sim-to-real numbers ever since, and nothing
failed. The fix is a `slug_aliases` block in `configs/synth.yaml` read through a
`_canonical()` helper, put in synth config rather than `circuits.yaml` so the training
fingerprint stays untouched.

### `senna/data/db.py` — the guard that replaced a comment

Three test modules drop and recreate every table. Pointed at the ingested store they erase
123,708 laps that take minutes to rebuild from a warm FastF1 cache and hours without one.
`require_disposable` is six statements and every one of them earns its place:

```python
    url = url or database_url()
    name = database_name(url)
    if not name:
        raise ProductionDatabaseError(
            f"'{url}' names no database, so the server would pick one — most likely the "
            "role's own. Put the database in the URL before dropping anything."
        )
```

`url or database_url()` lets a caller pass a URL explicitly (the tests do) or fall back to
the environment (a real run does). The empty-name branch was the review's find: a URL with
no path is legal, and asyncpg then defaults the database to the role's own name, which here
is `senna`, the ingested one. Worse, an empty name also matched an empty override string, so
`SENNA_ALLOW_DESTRUCTIVE_DB=""` plus a path-less URL opened the gate completely. Both holes
close with one refusal.

`database_name` started as `urlsplit(url).path.lstrip("/")` and had to grow, which is the
second lesson in this file about guards:

```python
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    for key in ("database", "dbname"):
        if query.get(key):
            return query[key][-1]
    return parsed.path.lstrip("/")
```

Both Postgres dialects let a `database=` or `dbname=` query parameter override the path. So
`postgresql+asyncpg://senna:senna@localhost/senna_test?database=senna` reads as disposable
by the path and connects to the ingested store. A guard that parses a URL differently from
the driver that will use it is not guarding the connection, it is guarding a string. The
query wins here for the same reason it wins in the driver, and `[-1]` takes the last value
because that is what a duplicated parameter resolves to. Generalise it: whenever you write a
check on a value that some other component will interpret, the check has to interpret it the
same way, or you have built two doors into one room and locked one of them.

```python
    override = os.environ.get(_OVERRIDE)
    if name.endswith(_DISPOSABLE_SUFFIX) or (override and override == name):
        return url
```

Two ways through. The name ends in `_test`, which is the ordinary path and needs no
ceremony. Or the operator has named this exact database in the environment. `override and`
is what stops the empty string from being a universal key; without it, `"" == ""` is a
match, and that is the bug the review caught before it could matter.

The refusal itself is worth reading, because a guard that only says no gets bypassed:

```python
    raise ProductionDatabaseError(
        f"refusing to drop every table on '{name}': destructive tests run against a "
        f"database whose name ends in '{_DISPOSABLE_SUFFIX}'. Create one and point the "
        f"tests at it:\n"
        f"    docker compose exec postgres createdb -U senna {name}{_DISPOSABLE_SUFFIX}\n"
        ...
```

The message hands over the exact two commands that make the problem go away. A guard whose
error costs five minutes of searching is a guard people learn to route around.

The rest of the wiring is boring on purpose. `tests/api/conftest.py`,
`tests/data/test_ingest_resume.py` and `tests/explain/test_persist.py` each call
`require_disposable(db_url)` before `drop_all`. CI's Postgres service is renamed `senna_test`
rather than given an exemption, so the invariant holds on the runner too. And
`scripts/postgres-init/10-create-test-database.sh` creates `senna_test` on the container's
first boot, because a guard that adds a manual setup step to a fresh clone is a guard
someone will disable.

### Five tests that pinned nothing, or pinned it dangerously

Nothing in this section is about F1, and it is the part of F14 you will use most often
elsewhere.

**One: a tautology.** A smoke run must not write into the store the report reads, because a
four-race median stamped with a full run's provenance would print in the headline table.
Here is what pinned it:

```python
def test_the_committed_store_and_the_smoke_store_are_different_places():
    committed = config.load("eval")["store"]["committed_dir"]
    assert (config.REPO_ROOT / committed / "smoke") != (config.REPO_ROOT / committed)
```

`Path(x) / "smoke" != Path(x)` is true for every string `x`. It is a fact about `pathlib`,
not about `run_suite`. Delete the smoke branch from the runner and this stays green. The
fix exercises the thing:

```python
    monkeypatch.setattr(run_module.store, "write_metric", fake_write)
    ...
    run_module.run_suite(only=["m10"], smoke=True, models_dir=tmp_path)

    assert written, "the runner wrote nothing, so this pins nothing"
    assert written["m10_legality"] == committed / "smoke"
```

Note the second-to-last line. If every stub returns nothing and the runner writes no
metric, the assertions below would be vacuous again, so the test asserts it did work before
asserting it did the right work. That guard-the-guard move shows up three times in this
feature.

**Two: an invariant a single process cannot observe.** `make report` must be deterministic
given the store, and the specific hazard is iterating a `set` or an unsorted `dict`
somewhere in the render. Python salts string hashing per process, so set iteration order is
stable *within* one process and can differ between runs. Calling `build_report` twice in the
same interpreter therefore compares two renders that were always going to agree:

```python
def test_report_is_byte_identical_on_a_fixture_store(store):
    first = build_report(store, figures=False)
    again = build_report(store, figures=False)
    assert first == again
```

The property being claimed is "a marker regenerates this from a clean clone", which is a
statement about processes. So the fixed test renders in three subprocesses under different
`PYTHONHASHSEED` values and collects the results in a set:

```python
    renders = {
        _render_in_subprocess(store, hash_seed) for hash_seed in ("0", "1", "12345")
    }
    assert len(renders) == 1, "the report depends on hash ordering somewhere"
```

The original test stays, because two renders in one process is still worth checking. It is
just not the whole claim.

**Three: a hard-coded list of the thing being discovered.** The failure mode the DB guard
exists for is a *new* module that drops tables and forgets the guard. A test parametrised
over three known module names cannot ever see that module. The fix inverts it: find the
modules by what they do.

```python
def _destructive_modules():
    here = Path(__file__).resolve()
    return sorted(
        path for path in (config.REPO_ROOT / "tests").rglob("*.py")
        if path.resolve() != here and "drop_all" in path.read_text()
    )
```

Grepping for `drop_all` in every test file, excluding this one (which mentions the string
while discussing it). Discovery has its own failure mode, though: if the search returns
nothing the parametrised test silently runs zero cases and pytest reports green. So there is
a canary:

```python
def test_at_least_one_module_still_drops_tables():
    # if this ever empties, the discovery below is silently vacuous
    assert _destructive_modules()
```

And because a substring check would still pass if someone deleted the guard call but left
the import, three tests call the real entry points and demand the exception. That fix needed
a second pass, and the second pass is the better story, so it gets its own item below.

**Four: a config key nothing has to read.** `assert "seed_stream" in m7` proves the yaml has
the key. It says nothing about whether `_diversity` uses it, and an inlined literal in the
runner would keep it green while the config became decoration. The first fix asserted on the
source text:

```python
    import inspect
    assert 'cfg["m7"]["seed_stream"]' in inspect.getsource(run_module._diversity)
```

That closes the hole and pins a spelling, so a harmless rename breaks it and a reader learns
to stop trusting it. The version that landed asserts the behaviour instead: call `_diversity`
twice with the configured stream id differing by one, capture the seeds it draws, and require
that they differ.

```python
    run_module._diversity(None, {"bahrain_grand_prix": (1,)}, base, None, smoke=True)
    shifted = {**base, "m7": {**base["m7"], "seed_stream": base["m7"]["seed_stream"] + 1}}
    run_module._diversity(None, {"bahrain_grand_prix": (1,)}, shifted, None, smoke=True)

    assert len(seen) == 2
    assert seen[0] != seen[1], "the configured stream id does not reach the draw"
```

An inlined literal produces identical draws under both configs and this goes red. It also
survives a rename, and it states the interpretability claim directly: the number in the yaml
is the number in force.

**Five: a test that proved the guard by firing the gun.** This one is my favourite and it
was not on the original list of four. The fix for item three included a test that pointed
`DATABASE_URL` at the production database and called the real `reset_schema`:

```python
    monkeypatch.setenv("DATABASE_URL", PRODUCTION)
    with pytest.raises(ProductionDatabaseError):
        reset_schema()
```

It works. If the guard regresses, this goes red. It goes red *after* dropping every table,
because a regressed guard lets `reset_schema` through and `reset_schema` drops tables. And
it needs no environment variable from the operator, so a plain `pytest tests/data` on a
machine with a regressed guard would have become the thing that erased the ingested store.
A regression test for a destructive incident had been written so that its failure mode is
the incident.

The landed version replaces the engine constructor with something that raises, so a
regressed guard hits a stub instead of Postgres:

```python
def _explode(*args, **kwargs):
    raise AssertionError(
        "a destructive fixture reached the database layer with DATABASE_URL pointing at "
        "the production store — the guard did not fire"
    )
```

`monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", _explode)` plus the same
on the module under test, then all three destructive entry points run through one
parametrised case. Two properties now hold at once: the test fails when the guard fails, and
the failure costs nothing. Getting only the first of those is the trap, and it is easy to
walk into, because a test that goes red at the right moment feels finished.

The common thread across all five: they asserted something *about* the code (a path shape, a
config key, a name list, a source string) instead of exercising it, or they exercised it in a
way whose failure mode was the disaster. The way to tell is mechanical. Break the code, run
the test, and read what it cost you to find out.

### What the store says

Every battery has now run at full scope: 24 circuits, 20 reserved test seeds each, 480
races, against the held-out rival band. These are the numbers in
`docs/results/F14/store/*.json` and in the generated `docs/results/F14-evaluation.md`, and
they are the Chapter 7 table.

| Metric | Value | Verdict |
|---|---|---|
| M1 paired position delta | +2.083 places over 480 pairs, 95% CI [1.710, 2.475], finish-ahead 0.627 | met |
| M2 counterfactual vs actual | 4W/5L/1T, p = 1.000, mean -0.60 places over 10 races | miss |
| M3 oracle regret | median 33.09 s, mean 86.98 s, p05 4.01 / p95 313.16 | reported, no bar |
| M4 energy | utilisation 0.649 of budget (ceiling 0.914, so 0.710 of attainable), derates 0.080 of 27,160 green laps | miss on both halves |
| M5 SC decision quality | precision 0.942, recall 0.308 over 374 windows | miss on recall |
| M5 VSC decision quality | precision undefined, recall 0.000 over 300 windows | miss |
| M6 pit window accuracy | 0.228 of 457 stops, CI [0.190, 0.267] | miss, target 0.72 |
| M7 strategy diversity | 0.226 nats mean over 24 circuits | reported, no bar |
| M8 sim-to-real | 0 of 4 held-out circuits within KS 0.15, worst 0.946 | miss |
| M9 tyre failures | 37.29 per 100 races (179/480), mean stint 29.4 laps, max 76 | miss, target < 2.0 |
| M10 regulatory legality | 0 coerced actions, 0 snapped stops over 480 races | met by construction |
| M11 luck share | 0.758 of finishing-position variance, CI [0.679, 0.820] | reported, no bar |

Two met, seven missed, three reported without a bar. That ratio is worth being calm about.
A suite where every metric passes is a suite whose bars were set after the run.

M1 is the headline and it holds: +2.08 places against the engineer heuristic with an
interval nowhere near zero. The band table beside it prices the opponents, since a paired
result inside one band cannot tell you whether the band itself is doing the work. The same
scripted heuristic finishes P6.85 under the train band and P6.63 under the test band, a
shift of 0.22 places in its own favour. Whatever the harder archetypes do to a fixed
strategy, it is about a fifth of a place, and M1's two places are not that.

Read M1 with M9 and a strategy appears. 37 tyre failures per 100 races against a target
under 2, on stints averaging 29.4 laps with one running to 76: the agent buys track
position by running tyres past the point where the cliff bites, and eats the failures. It
is a coherent way to play the simulator and a terrible way to run a real race team, and it
is exactly the behaviour an evaluation suite exists to surface.

M6 at 0.228 says roughly one stop in four lands within three laps of the post-hoc optimum.
Read it with the M5 caveat in the gaming notes: the search sees the whole race and the agent
did not, so the number is a ceiling comparison and not a grade.

M3's shape matters more than its median. 33 s median regret against a mean of 87 s and a
95th percentile of 313 s means the distribution has a long right tail: most races are close
to the oracle's ceiling and a few are catastrophic. Six races carry negative regret, which
is the oracle's greedy-energy assumption showing rather than a bug, and they are reported
rather than clipped.

M11 puts 0.758 of finishing-position variance on the event draws, at a mean policy head
entropy of 0.605 nats over 12,000 sampled episodes. Three quarters of where you finish is
the day you had. That is a lower bound by design (entangled variance is charged to the
decision side), and it is the number that should follow any claim about strategy quality in
this domain.

M8 is the documented miss and its cause is not in this feature. Held-out lap-time KS sits at
0.704 (Barcelona), 0.872 (Britain), 0.918 (Austria) and 0.946 (Belgium) against a 0.15
target (`docs/synth/validation_summary.yaml`). The mechanism is in the F03 lesson: the
T1/T2 point-mass transform's straight-line gain outweighs its corner loss, so it predicts
2026 laps roughly 4–6 s too fast, and two distributions that barely overlap drive KS toward
1. E-14 forbids fixing it by refitting on the held-out rounds, because a generator tuned on
its own test set has no test set left. So the number ships with its mechanism attached. A
sim-to-real suite that never reported a miss would be telling you it cannot detect one.

### Two results worth arguing about

**The agent is blind to virtual safety cars.** Across 311 VSC windows it pitted zero times.
Not rarely. Never. And the afterstate search says 134 of those windows were worth taking:
pitting would have finished the race faster by more than the 1.0 s materiality margin. Under
full safety cars, the same agent is good at this. It called 53 stops; of the 52 that landed
in a scored window, 49 were right and 3 were wrong, which is precision 0.942. It also missed
110 opportunities, so recall is 0.308. Conservative under SC, absent under VSC.

The reason this is visible at all is E-03. The spec insists VSC and SC stay separated end to
end: in the status codes, in the pit-loss multipliers, in the window extraction, and in the
M5 confusion matrix. Pool them and the report reads precision 0.942, recall 0.167 over 674
windows, which looks like one mediocre skill instead of one competent skill and one missing
one. The separated version tells you where to look. My guess, and it is a
guess the suite does not test, is that a VSC's smaller pit-loss discount never clears
whatever internal threshold the policy learned under SC, and the observation may not
distinguish the two states sharply enough for the agent to learn a separate response. That
is a stated hypothesis and F15 work, not a finding.

In the viva: "E-03 required that virtual and full safety cars be kept apart everywhere in
the pipeline because they are economically different opportunities. Separating them in the
M5 report is what turned a mediocre pooled score into a specific, actionable finding: the
policy never pits under VSC, across 311 windows, 134 of which were worth taking."

**M2 is an honest wash and gets reported as one.** Ten era-matched counterfactuals against
the real teams' own strategies: 4 wins, 5 losses, 1 tie, mean -0.60 places, exact sign test
p = 1.000. The bootstrap interval [-2.98, 1.76] is printed with `"descriptive only"`
attached. There is no result here in either direction, and that is a legitimate thing to
report.

It is only legitimate because the bar was set first. `configs/eval.yaml` fixed the ten races
with a per-race rationale, named the sign test as the primary claim, and recorded the alpha
before any race was rolled. Without that, a 4-5-1 split is an invitation: swap two races,
switch to the mean, quote the bootstrap interval as if it were the test, argue that the tie
should count as half. Every one of those moves is available after the fact and none of them
is available before. The 25 snapped stops in the replay baseline are reported alongside,
because a real strategy the mask had to alter is a weaker opponent and pretending otherwise
would tilt the wash.

In the viva: "M2 is null: 4 wins, 5 losses, one tie, p = 1.0 on a pre-registered exact sign
test. Pre-registration is why I can report that rather than renegotiate the analysis, and
at n = 10 the sign test needs 9 of 10 to reach significance in the first place, which the
config recorded before the races were rolled."

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
  ingested laps -> senna/eval/traces.py -> EventTrace + harness.py -> M2 pair

  sensitivity branch (make sensitivity):
  configs/ --copy--> tmp/trained (8.5 MJ) --+
  configs/ --copy--> tmp/refined (7.0 MJ) --+--> same seeds --> harvest_sensitivity.json
```

Inputs are the frozen model, the reserved seeds and the ingested 2023/24 races. Outputs are
JSON rows, a markdown table and three figures. Nothing here writes to the database, and
nothing in training can reach the test bank or the test band: `load_reserved_test_bank`
answers only to the consumer string `"F14"`, and `stage_venv` raises on any band but train.
`senna/data/db.py::require_disposable` sits outside this diagram entirely, on the one edge
where a test process can touch the ingested store.

## Try it yourself

1. **Prove the wiring.** Run `make suite SMOKE=1 ONLY=m1,m4` (2 circuits, 2 seeds each), then
   render that store on its own without touching the committed one:
   `.venv/bin/python -m senna.eval.report --store docs/results/F14/store/smoke --out /tmp/smoke.md --no-figures`.
   You'll know it worked when the smoke table shows M1 over 4 pairs with an interval far
   wider than the committed [1.710, 2.475], and the provenance block names the headline
   model version. Plain `make report` after this still prints the full 480-race numbers,
   which is the point of the smoke store being a different directory.

2. **Move a materiality threshold and predict first.** In `configs/eval.yaml`, change
   `m5.label_margin_s` from `1.0` to `30.0`. Before running anything, write down what you
   expect. Then `make suite SMOKE=1 ONLY=m5` and open
   `docs/results/F14/store/smoke/m5_windows.json` (the smoke directory, not the committed
   root). You'll know it worked when almost every window carries `"label": "immaterial"` and
   the `excluded` block counts them, with precision and recall going NaN. At the committed
   1.0 s margin only 16 of 690 windows are excluded that way, so the contrast is stark.
   Restore the 1.0 afterwards.

3. **Break things on purpose.** This is the technique from the vacuous-test section, run
   twice on domain logic and twice on the tests themselves.

   Domain first. Change `Window.decision_laps` in `senna/eval/afterstate.py` to start at
   `self.first_lap`, then run `.venv/bin/python -m pytest tests/eval/test_sc_quality.py -q`.
   Then make `_pit_loss_at` in `senna/strategy/oracle.py` return
   `scenario.pit_loss_mean_s` unconditionally and run
   `.venv/bin/python -m pytest tests/strategy/test_oracle_wet.py -q`. You'll know it worked
   when `test_m5_onset_lap_pit_is_not_counted_as_a_call` fails on `assert not
   verdict["agent_called_pit"]` and `test_stage1_pit_charge_is_status_aware` fails on its
   ranking assertion. For each, say in one sentence which way the bug moves the metric.

   Now the tests. In `senna/eval/run.py`, delete the `"smoke"` suffix so a smoke run writes
   to the committed store, and run `.venv/bin/python -m pytest tests/eval/test_run_wiring.py
   -q`. Then in `senna/data/db.py`, put the empty-name branch back the way it was by
   deleting the `if not name:` block and changing the override test to
   `os.environ.get(_OVERRIDE) == name`, and run
   `.venv/bin/python -m pytest tests/data/test_db_guard.py -q`. You'll know it worked when
   `test_a_smoke_run_never_writes_where_the_report_reads` and
   `test_a_url_without_a_database_is_refused` both go red, then green again once you check
   the files out at HEAD. Now do the same injuries against the versions of those tests at
   commit `78fd1ee` and `72911d4` and watch them stay green. That contrast is the whole
   lesson.

4. **Run the sensitivity on two circuits.** `make sensitivity CIRCUITS=bahrain_grand_prix,monaco_grand_prix`
   (5 seeds each, so 10 races per arm), then open
   `docs/results/F14/store/subset/harvest_sensitivity.json`. Predict the sign of
   `delta.derate_share` before you look. You'll know it worked when the subset lands in
   `store/subset/` and never in the store root, the envelope carries `"subset": true` with
   `"circuits": 2`, and `git status` shows `configs/circuits.yaml` unmodified even though the
   run rewrote every harvest cap in it twice. Then pass one real circuit and one misspelled
   one and check that `scope.circuits` says 1: the envelope counts circuits rolled, not
   names typed.

5. **Add a CI to M9.** `tyre_failure_rate` in `senna/eval/metrics.py` returns a bare rate.
   Give it one: build a per-race 0/1 list and pass it to `share_interval` from
   `senna/eval/bootstrap.py` with the bootstrap config, then add the bounds to the returned
   dict and to `_m9` in `report.py`. Write the test first in `tests/eval/test_metrics.py`,
   and before you write the code, check the test fails for the right reason. You'll know it
   worked when the report's M9 row shows an interval and
   `.venv/bin/python -m pytest tests/eval -q` stays green.

## Check yourself

1. Two policies get the same seed in the same env. Why are they not racing the same race,
   and what does F14 do instead?
2. What does M1's bootstrap interval tell you, and name one thing it definitely does not
   tell you.
3. An agent pits under every safety car. What does M5 report, and why is that not a pass?
   Then: SENNA's agent has the opposite problem. Describe it in numbers.
4. The oracle used to charge a flat pit loss. Which way did that bias M3, and why is a
   bug that flatters the agent worse than one that punishes it?
5. Defend this: why fine-tune a separate 2024 model for the counterfactuals instead of just
   running the frozen 2026 headline against the 2024 races?
6. A test suite is green. What would convince you that a particular test in it is actually
   testing something? Then: a test does go red when you break the code. Name the second
   question you should still ask about it.
7. `.env.example` had asked people not to point the tests at the ingested database since
   F01, and it was erased three times anyway. What changed, and why does the override take
   a database name instead of a boolean?
8. Defend this: the harvest-cap sensitivity says a 7 MJ cap costs the agent 0.13 places.
   What are you entitled to claim from that, and what would an examiner be right to push
   back on?

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
   cost of a wrong pit never enters it. SENNA's agent is the mirror image: under SC it
   called 53 stops of which 49 were right, precision 0.942, and missed 110 opportunities
   for recall 0.308. Under VSC it pitted zero times in 311 windows, 134 of which the
   afterstate search says were worth taking, so recall is 0.000 and precision is undefined
   rather than 0.0 (there were no calls to be right or wrong about). Both fail 5.12, and
   they fail it for opposite reasons, which is only visible because E-03 keeps the two
   statuses apart.

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
   race the same physics and only the strategy differs. And the size of the confound is now
   measured rather than assumed: on identical 2024 validation banks the fine-tuned model
   scores 6.336 mean points against the frozen headline's 3.802, so about two and a half
   points of a 2026 agent's apparent 2024 performance is the car.

6. By breaking the code it claims to cover and confirming the test goes red. A test that
   stays green against deliberately broken code is asserting a tautology, not a behaviour.
   The worked example: `assert (REPO_ROOT / committed / "smoke") != (REPO_ROOT / committed)`
   was supposed to stop a smoke run writing into the store the report reads, but
   `Path(x) / "smoke" != Path(x)` holds for every `x`, so deleting the branch it guarded
   changed nothing. The replacement calls `run_suite(smoke=True)` with a stubbed writer and
   asserts where the write landed, plus one line asserting a write happened at all, so an
   over-stubbed version cannot go quietly vacuous either.

   The second question is what the test did on its way to failing. The database guard's
   first regression test pointed `DATABASE_URL` at production and called the real
   `reset_schema`, so a regressed guard let the drop through and the test reported the
   regression from the far side of an erased database. It also required no opt-in, so
   `pytest tests/data` would have been the thing that erased it. The landed version stubs
   `create_async_engine` with a function that raises, which keeps the red and removes the
   cost. Red at the right moment and safe at that moment are two separate properties.

7. The rule moved from prose into `senna/data/db.py::require_disposable`, which every
   destructive site calls before `drop_all`, and which refuses any database whose name does
   not end in `_test`. That is the whole change: a convention enforced by a reader's
   attention has no enforcement, and this one is enforced by the code path that does the
   damage. The override names its target (`SENNA_ALLOW_DESTRUCTIVE_DB=senna`) rather than
   accepting a flag, because a bare `=1` is a blanket authorisation that survives in a shell
   long after the operation that needed it, whereas a named one only authorises the exact
   database the operator typed. The review also closed a hole in it: an empty override
   string matched an empty database name, so a URL with no path was accepted, and asyncpg
   would then have defaulted to the role's own database, which is the ingested one.

8. You are entitled to say that the frozen agent degrades gracefully under the FIA's refined
   cap: it gives up 0.13 places on average while its derate share goes from 0.078 to 0.182,
   and the mechanism is visible, since a 7 MJ cap drops the physically attainable deployment
   ceiling from 0.914 to 0.819 so the same policy hits the floor of the store more often.
   You are not entitled to say anything about how good a 7 MJ agent could be, because that
   needs a retrain and this measures robustness rather than re-optimisation. The fair
   pushback is on power: 120 races per arm at 5 seeds a circuit, no interval on the 0.13,
   and a paired design that makes the comparison clean but does not make it precise.

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
| Vacuous tests and break-it-on-purpose verification | F14 | A green test is evidence only if it would go red without the code; four F14 tests asserted tautologies (`Path(x)/"smoke" != Path(x)`, two renders in one process, a hard-coded module list, a config key nothing reads), so each fix exercises the code and carries a canary assertion that the exercise happened. |
| A test whose failure mode is the incident | F14 | The guard regression test pointed `DATABASE_URL` at production and called the real drop, so it went red only after erasing the store and needed no operator opt-in; the fix stubs the engine constructor to raise, so the test fails when the guard fails and costs nothing when it does. |
| Enforced convention (the named-target escape hatch) | F14 | `.env.example` asked for a disposable test database and the real one was erased three times anyway, so the rule moved into `require_disposable`; the override takes the database's name rather than a boolean, and `database_name` reads `database=`/`dbname=` the way the driver does, because a guard that parses a URL differently from its driver guards a string rather than a connection. |
| Overlay sensitivity as a paired experiment (E-02) | F14 | A regulation change the frozen model cannot be retrained for is measured by rolling both arms on the same seeds against throwaway config copies; both arms build an overlay, a bank spanning two committed values is refused, and a race dropped in one arm only fails the run. |
