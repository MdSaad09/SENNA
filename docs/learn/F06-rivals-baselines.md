# F06 — Rivals, baselines, the oracle and the throughput number

## What we built and why

F05 gave the agent a race to learn in, but the field it raced against was a placeholder:
21 identical cars, all on the same scripted one-stop, all equally quick. An agent that
beats 21 clones has learned nothing you could defend in a viva. F06 replaces that field
and builds the whole measuring apparatus around it — the opponents the agent trains
against, the yardsticks its result is quoted against, and one benchmark number that says
whether the training plan is even affordable.

Race terms first. Real rivals have styles. Some teams pit early to jump you during the
stops (the undercut); some nurse one set of tyres to the flag and never flinch; some sit
and wait for a safety car to hand them a cheap stop. F06 gives the field three such
characters, drawn fresh each race, so the agent learns to strategise against recognisable
behaviour instead of against noise. Then it builds three reference strategies — a sensible
pit-wall heuristic, a real 2024 winner's actual stops replayed against 2026 physics, and a
monkey pressing legal buttons — so that when we later claim "the agent gained 1.5 places,"
we can say gained *against whom*, under identical luck. Then the oracle: a search that,
knowing the whole race in advance, finds close to the best race anyone could have driven —
the ceiling. And last, a stopwatch on the environment itself.

Two ideas carry the feature and both deserve the words up front. The first: you cannot
fairly compare two strategies just by handing them the same random seed, because a race
consumes randomness at a rate that depends on what you do. Pit a lap earlier and every
dice roll afterwards lands on a different lap, for everyone. The fix is a recorded,
replayable race — the deterministic twin. The second: a rival field is easy to make
accidentally memorisable. If every car answered a safety car with one shared rule, the
agent would memorise that single pattern rather than learn strategy. E-06 forbids exactly
that, and the archetypes are built around the ban.

## New ideas in this feature

**Rival archetypes and the train/test parameter split (E-06).** An archetype is a named
rule set — undercutter, tyre_saver, opportunist — plus a band of numbers those rules fire
on. Every race, each rival is assigned a character and then draws its own pit threshold,
safety-car eagerness and pace scatter uniformly from that character's band. SENNA does
this because a field of identical scripted cars is both unrealistic and trivially
exploitable: the agent would overfit to one opponent. The bands come in two disjoint
versions. The agent trains against the `train` band and is later evaluated against a
`test` band that is pushed *further* toward each character's extreme — the undercutter
boxes even earlier, the tyre_saver runs even deeper. So the eval measures robustness to
harder, unseen opponents, not memorisation of the ones it trained on. Mental model: you
learn to play chess against a pool of club players, then get tested against a slightly
stronger pool you have never met. Smallest example: an undercutter with `pit_age_frac`
band `[0.50, 0.70]` might draw 0.61 this race, meaning it boxes at 61% of its tyre's life;
next race, same character, it might draw 0.53.

**Degeneracy avoidance and the per-car coin flip (E-06).** The one behaviour E-06 names
explicitly is the response to a safety car, because it is the highest-leverage decision in
the race and the easiest to make into a single memorable pattern. If the field ran "old
tyres box under SC" as a shared rule, a safety car would trigger one predictable stampede
the agent could bank on. SENNA breaks that: when a neutralisation begins, each rival makes
an independent Bernoulli draw — a weighted coin flip — against its own per-race response
probability, so the field's answer is a spread, never a single move. The viva answer:
**E-06 is avoided by making the safety-car response a per-car Bernoulli against a per-race
drawn probability rather than a shared deterministic rule, so the field's reaction to a
neutralisation is a distribution the agent cannot memorise; the train/test band split then
ensures the evaluation opponents are drawn from a disjoint, harder region, so a good score
measures robustness rather than overfitting.**

**The deterministic twin (A-05, M3).** A twin is a full recording of every random thing a
race did — the grid, the driver pace offsets, and per lap the track status, weather,
wetness, tyre failures and the pit and mode choices the field actually applied. Replaying
that recording through the env freezes all of it while letting the ego car's strategy
vary. SENNA needs this because "same seed" is not "same race": the random-number stream is
consumed at a policy-dependent rate (a tyre only rolls for failure once it is past its
cliff; a pit stop only draws a service time when it happens), so two strategies on one seed
drift apart in their events the moment they first differ. Pinning the recorded events is
the honest fix, and it is what makes a paired comparison genuinely paired. Mental model:
instead of re-rolling the dice for each strategy and hoping they match, you write down one
sequence of rolls and replay it for everyone. The twin is the surface the oracle-regret
metric (M3) measures against, and the branch point the M5 afterstate metric (F14) forks
from.

**The dynamic-programming oracle and oracle regret (A-05, M3).** The oracle answers "what
was the best possible race on this twin?" It is a search over pit plans — which laps to
stop and onto which compound — evaluated on the frozen twin with the energy mode chosen
greedily each lap. Oracle regret is then how far the agent's race fell short of that
ceiling. SENNA builds it in two stages because the twin's structure allows it. On a
deterministic twin a single stint's cost is plan-independent (fuel burn is fixed, energy
is decided lap by lap), so stage 1 pre-computes exact per-compound stint-cost tables and
ranks every 1-to-3-stop plan by table lookup, which is cheap. The only things a table
misses are traffic and the pit-lane queue, so stage 2 takes the top finalists and re-runs
them as full twin rolls that put both back. The catch worth stating: an oracle that is too
easy flatters the agent by setting a low bar, so its assumptions (full information, rivals
do not react, greedy energy) are published verbatim in the docstring. Mental model: rank
every plan quickly on paper, then actually drive the shortlist to break ties.

**The throughput benchmark, and why one number prices the plan (5.6.2).** Throughput is
env steps per second across many parallel worker processes — the single measurement that
decides whether the whole F07 training schedule is cheap or a problem. The env is pure
Python and NumPy, so more CPU cores means more steps per second, and 8 million training
steps is only affordable if that rate is high. SENNA measures it before writing the
training plan because if it came in under about 300 steps/s, the guidance (5.6.2) is to
stop and profile the env — hunt for object churn or a stray pandas call in the hot loop —
before trusting any budget. It came in at 18,477 steps/s on Saad's Mac, which puts 8M
steps at about seven minutes, so training is cheap and the multi-seed and ablation plans
are safe as written.

**Stage A and Stage B competence gates (5.7).** These are the two bars F07's training run
has to clear before anyone trusts it. Stage A is a solo competence check: on an empty,
dry, all-green race with no rivals, can the agent get within a small margin of the best
1-to-3-stop plan? That best plan is `solo_reference`, computed here from the same stint
tables the oracle uses. Stage B is the competitive bar: does the agent beat the baselines
in a real field? F06 doesn't run the gates (that's F07), but it builds both reference
points now, because a gate is only as trustworthy as the ceiling it checks against.

## The code, guided

Everything new lives in `senna/env/rivals.py`, `senna/env/twin.py`, the new
`senna/strategy/` package, `senna/bench/throughput.py`, and the twin/rival hooks threaded
into `senna/env/race_env.py`. Reading order below follows the data: build a field, record
a race, replay it, score strategies against it, then time the whole thing.

### rivals.py — the three characters and their rules

The module header states the two deliberate simplifications, so read them first: rivals
hold BALANCED energy mode (energy is not an E-06 axis, and per-car pace scatter already
comes from `pace_sigma_mult`), and archetypes carry no mean pace offset (that would tie
strategy style to car speed and confound the paired-baseline metric M1). The one axis E-06
demands — the safety-car response — is the per-car coin flip.

`parse_book` (`rivals.py:49`) loads and validates `rivals.yaml`. Most of it is plumbing,
but the validation is load-bearing and worth line-by-line attention, because it enforces
E-06 at parse time (`rivals.py:64`):

```python
for param in _PARAMS:
    train, test = tables[param]["train"], tables[param]["test"]
    for i, name in enumerate(names):
        lo_a, hi_a = train[i]
        lo_b, hi_b = test[i]
        overlaps = not (hi_a < lo_b or hi_b < lo_a)
        if overlaps:
            raise ValueError(...)
```

Two intervals overlap unless one ends before the other begins — that is the whole
`not (hi_a < lo_b or hi_b < lo_a)` test. If a train band and its test band overlap for any
parameter, the split is meaningless (the agent could have seen an eval value in training),
so the config is rejected outright rather than quietly weakening the robustness claim. The
second check (`rivals.py:76`) refuses a `wet_crossover_jitter` large enough to push the
earliest slick-abandoner below the Intermediate tyre's legal band — a rival forced onto a
tyre the mask forbids would be a contradiction, so it fails loudly.

`draw_field` (`rivals.py:122`) assigns characters and draws each car's numbers. This is
core logic, so line by line:

```python
non_ego = np.array([c for c in range(n_cars) if c != ego])
labels = np.resize(np.arange(len(book.names)), non_ego.size)
archetype = np.full(n_cars, -1)
archetype[non_ego] = rng.permutation(labels)
```

`np.resize` tiles `[0, 1, 2]` across the 21 non-ego cars, giving a balanced 7/7/7 split of
the three archetypes, and the permutation shuffles which car gets which. Balanced by
construction, so every single race fields all three characters rather than gambling on a
near-uniform random draw. The ego (car 0) is marked `-1` — no archetype — so the field
logic never acts on the agent's car.

```python
def draw(param, ego_fill):
    table = getattr(book, param)[band]
    lo = np.where(archetype >= 0, table[archetype, 0], 0.0)
    hi = np.where(archetype >= 0, table[archetype, 1], 0.0)
    value = lo + rng.random(n_cars) * (hi - lo)
    value[ego] = ego_fill
    return value
```

For a parameter, look up each car's archetype's `[lo, hi]` band, draw one uniform in
`[0, 1)`, and map it linearly into that band. The subtlety is *when* the uniform is drawn:
one per car per parameter, before the band is applied. The docstring spells out why — the
same seed gives the same field and the same archetype mix under either band, and only the
values shift. That is what keeps train and test evaluation paired: you face the same 21
characters with the same relative luck, just calibrated to the harder band. The ego always
gets a sentinel (`np.inf` pit trigger so it never auto-boxes, `0.0` SC response, unit
sigma).

`pit_choices` (`rivals.py:159`) is the heart of the file: the compound each rival boxes to
this lap, or -1 to stay out. It is a priority ladder, checked top to bottom, and the order
*is* the strategy. Read the ladder body (`rivals.py:195`):

```python
if red_flag:
    choice[car] = legal_target(car)
    continue
```

A red flag lets everyone change tyres for free (E-04), so it sits at the top — nobody
passes up a free stop.

```python
cur_slick = cur in _SLICK_CODES
illegal_now = (... wetness pushed the current tyre out of its band ...)
wetting = cur_slick and wetness > slick_max - draw.wet_jitter[car]
if illegal_now or wetting:
    choice[car] = legal_target(car)
    continue
```

Weather comes next: a car on the wrong tyre for the track, or one about to be, boxes for
the right one. The `wet_jitter` term is the E-06 spirit applied to the wet crossover — each
car's slick-to-inter trigger is nudged by its own small offset, so the field staggers onto
wets instead of pitting in one memorable full-field wave.

```python
dry = wetness <= slick_max
if dry and not state.second_compound_used[car] and state.lap == total_laps - 1:
    choice[car] = legal_target(car)
    continue
```

The two-compound backstop (F-20): on the last lap a car could still serve the rule, if it
hasn't run a second compound, it is forced to box. Same rule the mask enforces for the
ego, expressed as a rival's own decision.

```python
if response_roll is not None:
    probability = draw.sc_response_prob[car] * scale
    old_enough = age >= book.sc_response_min_stint_frac * trigger_age
    if response_roll[car] < probability and old_enough:
        choice[car] = legal_target(car)
        continue
```

This is E-06 in code. `response_roll` was drawn once at the top of the function
(`rivals.py:188`) only on a neutralisation onset, so the RNG stream stays aligned across
laps that do and don't start a safety car. Each car boxes only if its own coin lands under
its own probability *and* its tyres are worn enough to justify binning them (`old_enough`)
— nobody throws away a nearly-new set for a cheap stop. A VSC scales the probability down
by `vsc_response_scale`, because a VSC stop saves less than a full SC stop (E-03).

```python
if age >= trigger_age and laps_left > book.green_stop_min_laps_left:
    choice[car] = legal_target(car)
```

Bottom of the ladder: the ordinary green-flag tyre-age stop. A car boxes once its tyres
pass its drawn threshold, unless the race is nearly over. `legal_target` (`rivals.py:173`)
picks *what* to fit — wets or inters if the track demands them, otherwise the archetype's
slick preference, swapping off the start compound if the two-compound rule still owes a
change. Every branch returns a tyre that is legal for the current wetness, so a rival can
never request a masked compound. The viva line: **the field's pit logic is a single
priority ladder — red flag, weather, two-compound backstop, safety-car coin flip, then the
green tyre-age trigger — and because `legal_target` only ever returns a weather-legal tyre,
rivals obey the same compound rules the ego's mask enforces, without a mask.**

### rivals.yaml — the bands, all stylised

Every number here is flagged `stylised`: a designed modelling choice, not a fit. The header
is honest about it — there is a tracked to-do to sanity-check these bands against the real
ingested pit-lap distributions before F14's M1 headline, and M1 is provisional until that
passes. Each archetype has a one-line `story` (the character in plain English), a
`slick_preference` ordering, and train/test bands for the three drawn parameters. The
`field` block up top holds the shared constants (the VSC scale, the minimum stint fraction
before answering a safety car, the no-late-green-stop cutoff, the wet jitter), each with a
comment naming its origin. The interpretability contract in action: you can read the entire
rival field's behaviour out of one commented YAML file.

### twin.py — the recording

`EventTrace` (`twin.py:23`) is a dataclass, one field per stream a race realised: the grid
and driver offsets set at reset, and per-lap arrays for status, red flags, weather,
wetness, failures, and the field's applied pit and mode choices. The comments name the
shape and role of each. One design note earns its place (`twin.py:11`): the trace records
what the env *applied*, not how the rivals *decided* it, so it survives any later change to
the archetype logic — you can rewrite `rivals.py` and old twins still replay identically.

`EventTrace.green` (`twin.py:40`) is the classmethod that builds a synthetic all-green,
bone-dry twin — no neutralisations, no weather, no failures, no rival stops. This is the
race with a computable near-optimal answer, so the Stage A solo reference and the oracle's
toy race both run on it. `save_npz` / `from_npz` (`twin.py:63`) are plain NumPy
serialisation so a recorded twin can be written to disk and reloaded; block-level
plumbing, nothing subtle.

### race_env.py — the twin and rival hooks

F05's env grew two optional keywords: `record=True` captures a trace as the race runs,
`twin=<trace>` replays one. The pattern throughout `step` is the same — a live race rolls
the dice, a twin reads them from the recording — and it appears in every place randomness
enters.

In `reset` (`race_env.py:130`), a live field draws its archetypes; a replayed one takes its
rivals from the trace, so no draw is made:

```python
self._rivals = (
    None if self._twin is not None
    else rivals.draw_field(self._book, self._band, n_cars=n, ego=0, rng=self._rng)
)
```

`_resolve_track_status` (`race_env.py:241`), `_resolve_weather` (`race_env.py:280`),
`_field_modes` (`race_env.py:289`) and `_field_pit_choices` (`race_env.py:356`) all branch
the same way: `if self._twin is not None`, read the frozen value from the trace; otherwise
compute it live. `_lap_noise` (`race_env.py:300`) is the clearest example of why the twin
matters for the oracle:

```python
if self._twin is not None:
    return np.zeros(self.n_cars)
return self._rng.normal(0.0, self.scenario.s_ref_s * self._rivals.sigma_mult)
```

A live race adds per-car pace noise, scaled by each rival's drawn `sigma_mult`. A twin roll
zeroes it — deterministic physics is exactly what makes oracle regret a clean ceiling
rather than a noisy one (M3).

`_resolve_failures` (`race_env.py:323`) has the one asymmetry worth understanding. On a
twin the field's tyre failures replay verbatim, but the *ego's* failure is recomputed from
its own tyre age:

```python
failed = self._twin.failed[lap_index].copy()
ego = state.ego
cliff = self._max_age_by_code[int(state.compound[ego])] + self._cliff_margin
failed[ego] = state.tyre_age[ego] > cliff
```

Why the ego is special: on a twin the ego may run a completely different strategy than the
race that was recorded, so it can push a stint far past where the recorded ego did. Its
failure has to follow its own tyre age, not the recording's. It is applied as a hard cap at
the cliff (a deterministic cutoff, not a random hazard), which keeps an oracle stint inside
the fitted data's support — the oracle can't win by banking on a lucky non-failure.
`_capture` (`race_env.py:308`) writes each lap's realised events into the trace, blanking
the ego's slot so the twin only ever prescribes the field. `recorded_trace`
(`race_env.py:160`) hands the finished trace back but refuses an incomplete one: a race that
retired before the flag would leave a green-tailed twin that lies about the events (M3).

### The strategy package — one interface, three baselines, the oracle

`policy.py` (`policy.py:13`) defines the contract everything shares. A `StrategyPolicy` has
`reset(obs, info, rng)` and `act(obs, info, mask)` — it sees exactly what the agent sees
(the observation, the info dict, the flat action mask) and returns a `MultiDiscrete([6, 4])`
action the mask permits. It never reaches into env internals; anything it needs to remember
(its stint age, the compounds it has run) it keeps itself, the way a real pit wall does.
One interface means the baselines, the oracle's plan runner and F07's agent all plug into
the same rollout harness.

`rollout.py` (`rollout.py:27`) is that harness — `run_episode(env, policy, seed)` — reused
by the baselines, the oracle's twin rolls, and F14's paired comparisons. It seeds the env
and the policy on *separate* streams (`rollout.py:11`): the env off the race seed, the
policy off a decoupled sub-stream `[seed, 91]`. So a random baseline is reproducible
without ever sharing draws with the race it runs inside — its dice and the race's dice are
independent by construction. It returns an `EpisodeResult` carrying the final position,
race time, points, pit laps, compounds, and `snapped` (how many times a policy's proposal
had to be altered to stay legal — the replay baseline's honesty counter).

`heuristic.py` (`heuristic.py:20`) is the engineer baseline: a readable pit wall. Its
`_decide_pit` (`heuristic.py:62`) is the same priority ladder as the rivals, written from
the ego's side — weather first, then the cheap safety-car stop, then the two-compound
backstop, then the degradation trigger. Every threshold is a named constant in
`baselines.yaml`; the wetness bands it reads straight from `env.yaml`, the same source the
action mask reads, so the heuristic and the mask can never disagree (E-08). Its
`_decide_mode` (`heuristic.py:123`) is a small SOC-aware energy rule: conserve if the
battery is low, defend if someone's close behind, attack if chasing a car ahead with charge
to spare, else balanced.

`replay.py` (`replay.py:24`) is the replayed-real baseline: a real race's recorded stops
run against 2026 physics. It runs BALANCED everywhere on purpose — a 2024 strategy carries
no 2026 energy decision, and inventing one would fabricate the very thing M2 measures. The
interesting part is `_resolve_stop` (`replay.py:40`): when the mask blocks a recorded stop
(a slick call on a wet track), it waits a few laps (`_defer_max`), then snaps to the
nearest legal compound and increments `snapped`. That counter is the honesty of the metric
made visible — it records exactly where 2024 reality and the 2026 simulator part ways.

`random_legal.py` (`random_legal.py:10`) is the floor: sample uniformly among the legal
actions per head. By construction it can never propose an illegal action — the F16
compliance guarantee seen from the policy side — which is why it also drives the throughput
benchmark. If even the monkey can't break a rule, the env's masking is airtight.

`plans.py` holds the shared vocabulary. `greedy_mode` (`plans.py:24`) is core logic — the
per-lap pace-optimal energy choice, priced straight from the env's own dynamics so the
oracle never drifts from the physics it optimises:

```python
delivered, derate, _ = dynamics.resolve_energy(np.full(4, soc_mj), harvest, request, scenario)
price = dynamics.mode_pace_s(modes, delivered, request, scenario) + derate
...
key = (price[mode], mode != dynamics.BALANCED, mode)  # price, then prefer balanced
```

For all four modes at once it asks the real `resolve_energy`/`mode_pace_s` what each costs
this lap, then picks the cheapest legal one, ties going to balanced (the do-no-harm
default). Because it calls the same functions `step` does, greedy energy is guaranteed
consistent with the environment. `PlanPolicy` (`plans.py:45`) then executes a fixed list
of stops through the ego interface, boxing on each planned out-lap unless the mask forbids
it.

`oracle.py` is the ceiling. Its docstring (`oracle.py:16`) publishes the seven assumptions
verbatim — full information, rivals don't react, deterministic physics, greedy energy, the
MEDIUM start, the stop cap, no mid-race replanning — because an oracle whose assumptions are
hidden can quietly flatter the agent. `stint_cost_table` (`oracle.py:48`) fills
`table[l1, l2]` = the exact deterministic cost of running one compound from lap `l1` fresh
to lap `l2`, one ghost car with no traffic and no FIFO, greedy energy each lap. On a green
twin that reduces to the joint lap-time model summed lap by lap — verifiable, and the
oracle test checks it against a hand computation. `enumerate_plans` (`oracle.py:84`)
generates every legal 1-to-`max_stops` plan by recursion, with three constraints baked in:
stop laps strictly increasing, no stint longer than its compound's cliff (so no plan banks
on a forced failure), and two distinct compounds run (F-20). `solve_oracle`
(`oracle.py:122`) is the two-stage search:

```python
ranked = sorted(plans, key=lambda plan: _plan_table_cost(plan, tables, scenario, trace.n_laps))
finalists = ranked[: cfg["top_k_rolls"]]
contenders = finalists + [plan for plan in baselines if plan not in finalists]
...
for plan in contenders:
    env = _twin_env(trace)
    result = run_episode(env, PlanPolicy(plan, mode="greedy", scenario=scenario), seed=0)
    if result.race_time_s < best_time:
        best_plan, best_time = plan, result.race_time_s
```

Rank every plan by table cost (cheap, ignores traffic and FIFO), take the top K finalists,
add any baseline plans handed in, then re-run each as a full twin roll that restores traffic
and the pit queue. The lowest rolled time wins. Because each baseline's own plan is
re-rolled here, the oracle can only tie or beat a baseline on the pit dimension — which is
the property the toy-race test asserts. `solo_reference` (`oracle.py:147`) is the Stage A
bar: the best 1-to-3-stop plan on a green solo trace, scored by the tables alone,
deterministic across calls because a gate needs a stable reference.

`extract.py` (`extract.py:21`) compiles a real race's strategy into a plain `PitPlan`.
`compile_plan` is pure pandas-in, plan-out with no database, so it unit-tests without I/O
and never touches the env hot loop. Run as a script it reads the ingested Postgres store,
takes the race winner's stints, rescales the stop laps to the sim's lap count, and writes
`configs/real_strategies.yaml` — checked in, so a rollout and CI never need the database.

### bench/throughput.py — the stopwatch

`run_benchmark` (`throughput.py:53`) spins up N `SubprocVecEnv` workers, warms them up, then
times a fixed number of steps driven by random-legal actions with the per-step action-mask
fetch on the clock — so the env is priced exactly as MaskablePPO will drive it, mask
transport included. Policy inference is deliberately excluded: this measures the env, not
the network. The report it returns is the reproducibility receipt — steps/s aggregate and
per worker, the projected 8M-step hours, the hardware, the Python version, the git commit,
and `config_hash` from `config.fingerprint(_CONFIG_FILES)` (`throughput.py:94`). That
fingerprint hashes the eight config files an env is built from, so a throughput reading is
tied to the exact constants that produced it — change a config and the hash changes, and you
know a stale number when you see one. `_print_summary` (`throughput.py:123`) prints the
warning if the rate falls below the 300 steps/s floor, naming the likely culprits and
telling you to flag it to Saad, because below that the F07 plan changes.

## How it connects

```
   F05 F1RaceEnv (reset/step, masks, 3-term reward)
        │
        ├── rivals.draw_field ─► 21 archetype cars (train | test band, E-06)
        │        drawn per race off the reset seed
        │
        ├── record=True ─► EventTrace  ──save_npz──►  a frozen twin on disk
        │                      │
        │                      ▼
        │              twin=<trace>  (events frozen, ego strategy varies)
        │                      │
        │        ┌─────────────┼─────────────────────────────┐
        │        ▼             ▼                             ▼
        │   baselines     oracle.solve_oracle          solo_reference
        │  (heuristic,    (stint tables ─► rank ─►      (Stage A bar, 5.7)
        │   replay,        top-K twin rolls)                 │
        │   random)            │                             │
        │        └──────┬──────┘                             │
        │               ▼                                    ▼
        │        run_episode ──► EpisodeResult ──► M1/M3/M5 (F14), Stage B gate (F07)
        │
        └── bench.throughput ─► 18,477 steps/s ─► prices the F07 training plan (5.6.2)
```

F06 sits between the environment and training. Nothing upstream depends on it; F07 trains
the agent against the rival field and checks it against the Stage A/B gates, and F14 quotes
the agent's result against the baselines and the oracle. The throughput number is the
green light that lets F07's plan stay as written.

## Try it yourself

The strategy and bench suites need no database or FastF1 cache. Run them with the venv
Python: `.venv/bin/python -m pytest tests/strategy tests/env/test_rivals.py -q`.

1. **Change a rival band and predict the effect.** The undercutter's `pit_age_frac` test
   band is `[0.38, 0.48]`. First widen its train band from `[0.50, 0.70]` to `[0.50, 0.72]`
   and predict: does this still parse? Run
   `.venv/bin/python -m pytest tests/env/test_rivals.py -q`. You'll know it worked when it
   still passes — 0.72 stays clear of the test band's ceiling of 0.48, so the split is still
   disjoint. Now set the train band to `[0.40, 0.70]` and rerun. Predict first: 0.40 now
   sits *inside* the test band's `[0.38, 0.48]`. You'll know it worked when nearly every
   test errors with the E-06 ValueError from `parse_book` — each one calls `load_book` on
   the real config and trips the overlap check, because a train value that could also be an
   eval value makes the robustness split meaningless. (The one test that builds its own
   config, `test_an_overlapping_band_is_rejected_at_parse`, keeps passing — it was already
   proving this rule.) Revert.

2. **Run the E-06 degeneracy test and read what it proves.** Run
   `.venv/bin/python -m pytest tests/env/test_rivals.py -k sc_responses -v`. Open
   `tests/env/test_rivals.py` around line 178 and read the comment: it ages the whole field
   past the safety-car floor but short of any green trigger, so the only thing that can make
   a car box is its own coin flip. You'll know you understand it when you can say why the
   test asserts the boxed-or-not pattern *varies* across seeds rather than asserting any
   particular car boxes.

3. **Watch the oracle beat the baselines on a green Bahrain twin.** Run this snippet with
   `.venv/bin/python`:

   ```python
   import numpy as np
   from senna import config
   from senna.env import F1RaceEnv
   from senna.env.twin import EventTrace
   from senna.strategy.heuristic import EngineerHeuristic
   from senna.strategy.random_legal import RandomLegal
   from senna.strategy.oracle import solve_oracle
   from senna.strategy.rollout import run_episode

   env = F1RaceEnv("bahrain_grand_prix", "2026")
   scn = env.scenario
   n = scn.grid_size
   trace = EventTrace.green(env.circuit, env.era, scn.total_laps, n, grid=np.arange(1, n + 1))

   for name, pol in [("heuristic", EngineerHeuristic(scn, config.load("baselines")["heuristic"])),
                     ("random", RandomLegal())]:
       r = run_episode(F1RaceEnv(env.circuit, env.era, twin=trace), pol, seed=704)
       print(f"{name:10s} {r.race_time_s:9.1f}s  finished P{r.final_position}")

   cfg = dict(config.load("baselines")["oracle"]); cfg["max_stops"] = 2; cfg["top_k_rolls"] = 5
   oracle = solve_oracle(scn, trace, cfg=cfg)
   print(f"oracle     {oracle.race_time_s:9.1f}s  plan={oracle.plan.stops}")
   ```

   You'll know it worked when the oracle's time is the lowest of the three and it prints a
   one- or two-stop plan (on the last run it chose a single stop to SOFT on lap 14 and came
   out about 100 s clear of the heuristic). Try nudging `max_stops` to 3 and watch the plan
   and time move.

4. **Break a config comment and feel the anti-black-box rule bite.** In
   `configs/baselines.yaml`, find `oracle.max_stops` and change it to a string like
   `"three"`. Run the snippet from exercise 3. You'll know it worked when it fails inside
   `enumerate_plans` with a type error, not a wrong answer — the constant is trusted, so a
   malformed one is caught at the point of use. Revert.

5. **Measure your own throughput.** Run `make bench WORKERS=4 STEPS=20000`. It prints
   steps/s aggregate and per worker, the projected 8M-step hours, and the config hash.
   You'll know it worked when the number is comfortably above 300 and the hours line reads a
   fraction of an hour. Compare your per-worker rate to the recorded 1,540/worker in
   `INDEX.md`; if yours is much lower, you're either on fewer cores or something in the hot
   loop regressed — which is exactly the signal 5.6.2 is watching for.

## Check yourself

1. Why can't you compare two strategies fairly by giving them the same random seed, and
   what does the deterministic twin do about it?

2. E-06 says the field's response to a safety car must not be one memorable pattern. Point
   to the exact mechanism in `rivals.pit_choices` that satisfies this, and explain why the
   coin is drawn once at the top of the function rather than per car in the loop.

3. The rival bands come in a `train` version and a disjoint, harder `test` version. What
   does the test-band evaluation measure that a same-band evaluation would not, and where is
   the disjointness enforced?

4. Defend this design choice: the oracle publishes its assumptions in its docstring, and it
   is a two-stage search (cheap table ranking, then full twin rolls) rather than one exact
   optimisation. Why both?

5. The throughput benchmark measured 18,477 steps/s. Suppose it had measured 200. What does
   5.6.2 tell you to do, and why does that number change the F07 plan rather than just being
   a slow run you wait out?

---

### Answers

1. Because a race consumes random numbers at a rate that depends on the strategy — a stop
   only draws a service time when it happens, a tyre only rolls for failure past its cliff —
   so two strategies on one seed diverge in their events the moment they first differ. The
   twin records every event a race applied (status, weather, failures, the field's stops)
   and replays them with noise zeroed and pit service at the mean, freezing the events while
   the ego's strategy varies, which is what makes the comparison genuinely paired (A-05,
   M3).

2. The mechanism is the per-car Bernoulli at `rivals.py:222`: each car boxes under a safety
   car only if its own `response_roll` lands under its own drawn `sc_response_prob` (and its
   tyres are old enough). The roll is drawn once at the top (`rivals.py:188`) because a
   neutralisation onset is a single event for the whole field, and drawing there keeps the
   RNG stream consuming a fixed number of variates whether or not a car ends up boxing —
   which is what keeps a SubprocVecEnv worker deterministic across seeds (5.5.5).

3. The test band is pushed further toward each archetype's extreme, so a test-band result
   measures robustness to harder, *unseen* opponents rather than in-distribution
   generalisation against the ones the agent trained on. Disjointness is enforced at parse
   time in `rivals.parse_book` (`rivals.py:64`), which rejects any parameter whose train and
   test intervals overlap, so a leaked value can never sit in both.

4. The assumptions are published because an oracle that quietly assumes too much (full
   information, non-reacting rivals, greedy energy) sets an easy ceiling and flatters the
   agent — stating them lets an examiner judge the ceiling's honesty (M3). The two-stage
   search exists because on a deterministic twin a stint's cost is plan-independent, so
   ranking thousands of plans by exact table lookup is cheap and correct except for traffic
   and the pit FIFO; restoring those on only the top finalists by full twin roll gives an
   exact winner without rolling every plan. Fast where it can be, exact where it must be.

5. At 200 steps/s, 5.6.2 says stop and profile the env — hunt for per-step object churn or a
   pandas call reachable from `step()` — before trusting any training schedule, and flag it
   to Saad. It changes the F07 plan rather than being a slow run to wait out because the plan
   assumes millions of cheap steps (multi-seed training, ablations): at 200 steps/s an 8M-step
   run would take days instead of minutes, so the multi-seed and ablation designs would have
   to be cut or the env fixed first. At 18,477 it is a non-issue and the plan stands.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| Rival archetypes and train/test split (E-06) | F06 | Three named rule sets (undercutter, tyre_saver, opportunist) whose thresholds are drawn per race from bands, with a disjoint harder `test` band held out for eval so a good score means robustness not memorisation. |
| Degeneracy avoidance / per-car Bernoulli response (E-06) | F06 | The safety-car response is an independent weighted coin flip per car against a per-race probability, so the field's answer to a neutralisation is a distribution the agent cannot memorise as one pattern. |
| Deterministic twin / EventTrace (A-05, M3) | F06 | A full recording of every random event a race applied, replayed with noise zeroed so events freeze while the ego strategy varies — the honest fix for "same seed is not same race" and the surface oracle regret measures against. |
| Strategy-policy interface and scripted baselines (A-07) | F06 | One `reset`/`act` contract (obs, info, mask in; MultiDiscrete action out) shared by the engineer heuristic, the replayed-real strategy, random-legal and the agent, so all are scored by one rollout harness. |
| DP oracle and oracle regret (A-05, M3) | F06 | A two-stage search — exact per-compound stint tables rank all 1-3 stop plans, top finalists get full twin rolls restoring traffic and the pit FIFO — giving the best-possible race ceiling; its assumptions are published so an easy oracle can't flatter the agent. |
| Throughput benchmark (5.6.2) | F06 | Env steps/s across N SubprocVecEnv workers with the mask fetch on the clock — the one number that prices the training plan; below ~300/s, profile the env before trusting any budget. |
| Stage A/B competence gates and solo reference (5.7) | F06 | Stage A checks the agent against the best 1-3 stop plan on an empty green race (`solo_reference`), Stage B against the baselines in a real field; F06 builds both reference points, F07 runs the gates. |
</content>
</invoke>
