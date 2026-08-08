# F16 — the race engine, pulled out of the agent

## What we built and why

Until this feature, a lap of a Formula 1 race could only be advanced by something holding
a Gymnasium action and willing to be handed a reward. `F1RaceEnv.step()` *was* the race:
seventy-five inline lines plus eight private resolvers, one hard-coded ego seat, and a
reward computed on every call whether the caller wanted a score or not. If you wanted to
run a race for any other reason — to serve it, to search over it, to sanity-check the
physics — you had to pretend to be a learning agent first.

That is backwards, and the repo already had the bruise to prove it. Look at
`senna/serve/frames.py:34`:

```python
state = env._state
```

The serving layer reaches through a private attribute of a training object to get at the
race, because there was no other door. Nobody chose that. It is what a customer does when
the thing it needs is locked inside something else.

F16 turns it round. `senna/env/engine.py` now advances a `RaceState` given twenty-two
decisions and imports nothing from Gymnasium or stable-baselines3. `F1RaceEnv` became the
adapter: it fills twenty-one seats from `rivals.py`, one from the learner, and converts
what came back into the reward-observation-mask shape SB3 expects. The race is the object.
The agent is one of its customers.

And nothing about the simulation changed. That is the odd part of this feature: it is
judged by producing exactly zero difference. A recorded race replays byte-identical
through the new seam, at two circuits, for all twenty-two cars, every lap. That identity
is the deliverable, not a side condition.

## New ideas in this feature

**Refactoring under a behaviour-identity contract.** When you move code, "the tests still
pass" is a weak claim. The tests were written against the behaviour you happened to think
about; a refactor can preserve every one of them and still quietly change the simulation.
So F16's acceptance test was not the suite — it was equality against a photograph. Record
the exact output of a full race *at the commit before the change*, commit that recording,
and afterwards assert `np.array_equal` against it. Not `allclose`. Equality, because a
drift of one ulp means a random draw moved, and a moved draw is a different championship.

The technique has three parts and all three matter. The fixture
(`tests/env/fixtures/F16_golden_bahrain_grand_prix.npz`) is a photograph. The generator
that produced it (`tests/env/fixtures/generate_f16_golden.py`) is committed *beside* it,
with the commit it ran at written in the docstring at line 8, so anyone can see what the
photograph is of. And the test imports the seed, circuits, field list and ego strategy
from that generator (`tests/env/test_engine_identity.py:29`) rather than restating them,
so the replay physically cannot drift from the thing it is compared against. Restate the
seed in the test and someone will eventually "fix" one of the two.

This is what let both reviewers say the refactor was *proven* rather than *trusted*. The
answer to say out loud: **a refactor's acceptance test cannot be its own test suite, because
the suite only covers behaviour someone thought to write down, and the risk in this
particular move — the order in which one seeded generator is consumed — is invisible to
every test that does not compare against a recorded race. So the contract was exact
equality against traces recorded at the previous commit, with the generator committed
beside the fixtures and the test importing its seed so the two cannot drift apart.**

**RNG draw order is part of the seed.** A seeded generator is a deterministic sequence of
numbers. `np.random.default_rng(512)` does not hand out "the safety-car roll" and "the pit
noise"; it hands out variate 1, variate 2, variate 3. Which physical quantity each one
becomes depends entirely on the order your code asks. Move one call earlier and every
number after it lands somewhere else, so every seeded race changes — silently, because
nothing is broken, the races are just different races.

SENNA's tick consumes six draws per lap, in this order: track status, weather, rival pit
choices, tyre failure (per car), pace noise, pit service. That order is now written down
in `senna/env/CLAUDE.md` as a rule, and pinned by
`test_rng_draw_order_preserved` (`tests/env/test_engine_identity.py:155`).

The sharp edge here is the tyre-failure loop, `events_io.py:105`. It is a Python
`for car in range(state.n_cars)` in a codebase whose whole hot-loop rule is "vectorise
everything" (F05). Vectorising it is the obvious optimisation and it is explicitly
forbidden. The reason is `events.tyre_failure` (`events.py:51`): a car inside its cliff
returns `False` without drawing at all, and only a car past the cliff rolls. So the number
of variates consumed per lap depends on how many cars are on old tyres — usually zero,
occasionally three. Replace it with one `rng.random(22)` and you consume twenty-two
variates every lap forever, which shifts the entire remaining stream of the race. The
comment at `events_io.py:101-103` says the loop is load-bearing rather than an oversight,
and the draw-order test asserts the shapes are `()` rather than `(n_cars,)` precisely so
that mistake shows up as a test failure and not as a mysteriously different season.

**Two phases: observe, commit, run.** The tick is not one call. It is:

```python
context = begin_lap(state, rng, source=..., lap_index=...)
decisions = <every seat commits>
outcome  = advance_lap(state, context, decisions, scenario, rng, source=..., sink=...)
```

`begin_lap` resolves what the track is doing — status, whether a neutralisation just
began, weather — and mutates the state so that whoever decides next reads *this* lap's
conditions. Then everyone commits. Then the lap runs.

The forcing reason is E-06: the rival archetypes need the neutralisation onset before they
can choose, because "the safety car just came out, do I box?" is the single most important
decision they make. If the track resolved inside the same call that ran the lap, rivals
would be deciding on last lap's information. So the seam has to open between the two.

It is also, pleasingly, how a real race works. The lights change, the field sees the track,
everyone commits to their lap, the lap happens. Nobody gets to re-decide halfway.

**Dependency inversion, in plain terms.** The jargon means: the important thing should not
depend on the less important thing. Concretely, "policy-centric" was the old shape — the
race lived inside the agent's environment, so every other consumer had to impersonate an
agent or reach through a private (`frames.py:34`). "Race-centric" is the new shape — the
race is a module with a plain function signature, and the agent is one caller that wraps
it. The test that states the inversion is `test_advance_without_reward`
(`tests/env/test_engine.py:207`): a full race to the flag with a classified field, never
constructing `F1RaceEnv`. The whole file constructs no env at all, and says so at line 9:
if a test in there needs the Gymnasium adapter, the inversion did not happen.

**One seam for events instead of seven branches.** Before F16, `self._twin is not None`
was tested in seven separate places inside the tick. The physics could not be read without
reading the replay logic threaded through it. Now there is one seam: an *event source*
answers the four questions the physics cannot answer from itself (what is the track doing,
is it raining, whose tyre let go, how long did the crew take), and an *event sink* writes
those answers down. `LiveSource` rolls them; `TraceSource` reads them off a recorded trace;
`TraceSink` records them. The engine calls `source.failures(...)` and does not know or care
which one it got. Python needs no interface declaration for this — same method names, same
signatures, done.

**Mutation testing.** F14 taught you that a green test is evidence only if it would go red
without the code (the vacuous-test row in the ledger). F16 is the procedural version: to
check whether a passing test is actually holding something, break the code on purpose and
see whether it goes red. If everything still passes, the test was decoration.

The code reviewer did this and found two. The good one: in `_v2_lap_facts`, the outgoing
tyre's compound and age are sampled *before* the engine runs (`race_env.py:255`, the
`outgoing` variable) and passed in, because the engine applies the pit swap before the
adapter scores the lap — v2's stint-end bonus is meant to reward the grip that came off,
not the fresh set going on. Replacing that snapshot with a read of the post-advance state
passed all 267 tests. Nothing in the suite could tell the two apart. That is how we learned
the compensation the refactor introduced was completely untested; the fix is
`test_stint_end_grip_is_the_set_that_came_off` (`tests/env/test_reward_v2.py:119`), which
sets the state to a fresh HARD, passes a worn MEDIUM as `outgoing`, and asserts the scored
grip is the worn one. It uses MEDIUM rather than SOFT on purpose — Bahrain's fitted soft
has `deg_a = 0.0`, so a worn soft scores identical grip to a fresh one and the test could
not distinguish them.

## The code, guided

Reading order: the engine, then where its events come from, then the adapter that lost
half its body, then the tests that proved it.

### senna/env/engine.py — the tick, with nobody driving

`begin_lap` (`engine.py:60`) is four lines and two of them are calls:

```python
red_flag, onset = source.track_status(state, lap_index, rng)
source.weather(state, lap_index, rng)
return LapContext(lap_index=lap_index, red_flag=red_flag, onset=onset)
```

Both mutate the state (status, wetness, red-flag count) so the decisions collected next
see the conditions they are actually deciding in. It takes no `scenario` at all: what the
track does is entirely the source's business, whether it is rolling hazards or reading a
trace. That was a review finding — the first version took a `scenario` it never used.

`advance_lap` (`engine.py:72`) is the transition model of 5.5.3 read top to bottom, and
every line earns its place:

```python
failed = source.failures(state, context.lap_index, rng)      # who lost a tyre this lap
gap_ahead_s = gaps_ahead(state, scenario)                    # traffic, before anything moves
harvest_mj = np.full(state.n_cars, dynamics.per_lap_harvest_mj(scenario, state.track_status))
request_mj = dynamics.deploy_request_mj(decisions.mode, scenario)
delivered_mj, derate_s, soc_next_mj = dynamics.resolve_energy(
    state.soc_mj, harvest_mj, request_mj, scenario)
```

Failures first, because a failed car's stop is not a chosen stop and the pit-time branch
below needs to know. Gaps second, computed from the *current* classification, because
dirty air is a function of where you are at the start of the lap. Then energy: harvest,
the mode's request, and `resolve_energy`, which is E-01 exactly as F05 taught it — the
request is clipped to what the store can supply and the shortfall becomes a derate in
seconds. Physics clips; nothing in here masks.

```python
noise_s = source.lap_noise(state, rng)
racing_time_s = dynamics.lap_time_s(...)
pit_time_s = _pit_times(state, decisions.pit, failed, context, scenario, source, rng)
lap_time_s = racing_time_s + pit_time_s
```

Pace noise comes from the source rather than the engine, because its scale depends on
which rival archetypes were drawn (`events_io.py:117` multiplies the circuit sigma by the
per-car `sigma_mult` the F06 field draw produced). That coupling used to sit inside the
tick with no declared home; now it rides the source, which is the honest place for it.
Racing time and pit time stay separate all the way into the `LapOutcome`, because the pace
term is scored on the racing lap alone — otherwise a stop reads as a catastrophically slow
lap and the agent learns never to box (5.5.4).

```python
if sink is not None:
    sink.capture(state, context, decisions, failed)
_apply_pits(state, decisions.pit, failed, context.red_flag)
state.cumulative_time_s = state.cumulative_time_s + lap_time_s
state.tyre_age = np.where(
    (decisions.pit != STAY_OUT) | failed | context.red_flag, 0, state.tyre_age + 1)
```

The capture happens *before* the pit swap, because the trace records the race as it was
decided, not as it ended up. Then the swap, then time, then tyre age, which resets to zero
on three grounds: you boxed, your tyre let go, or a red flag gave everyone a free change
(E-04). State is mutated in place — the race is one object moving forward, not a value
rebuilt each lap.

`_pit_times` (`engine.py:145`) is the E-05 pit lane you met in F05, moved wholesale: only
cars that chose to stop and did not fail get a service draw, scaled by the SC/VSC discount
and queued FIFO so teammates stack. One known defect rode across with it, and you should
be able to name it — the full net pit loss (~22.8 s) is passed where
`pitlane.resolve_pit_lane`'s own docstring wants a stationary service time, so two
teammates 0.5 s apart pay about +23 s. It is real, it is wrong, and F16 deliberately left
it, because fixing it moves F14's published numbers. "Do not fix what you find" was in the
plan.

`_burn_fuel` (`engine.py:182`) has one line worth reading closely:

```python
state.retired |= state.fuel_kg < base - 1e-9
```

A car that cannot cover the lap retires. The `1e-9` is not superstition: a car landing on
exactly zero at the line has *finished*, and floating-point arithmetic would otherwise
occasionally score the winner of a green race as a DNF.

### senna/env/events_io.py — where the randomness comes from

`LiveSource` (`events_io.py:36`) caches its constants at construction so the tick never
touches yaml. Its five methods are the five questions. `track_status` (`:63`) counts a
running neutralisation down before rolling for a new one, and returns `GREEN` as the onset
on a countdown lap, because only an *onset* offers a fresh decision — a rival on lap three
of a safety car should not keep re-deciding. Line 68 is worth a look too: under
`hazards="none"` it returns without rolling, which keeps the RNG stream untouched. That is
a deliberate property, not an optimisation. `failures` (`:100`) is the loop discussed above.

`TraceSource` (`:126`) is the twin. Every method reads instead of drawing, and `lap_noise`
returns zeros, because deterministic physics is what makes oracle regret a clean ceiling
(M3). It is also the one deliberately ego-aware thing in the race half of the package
(`:159-164`):

```python
failed = self.trace.failed[lap_index].copy()
ego = state.ego
cliff = self._max_age_by_code[int(state.compound[ego])] + self._cliff_margin
failed[ego] = state.tyre_age[ego] > cliff
```

The ego's failure is recomputed from its own tyre age because a replayed strategy can run
a stint the recording never ran. `TraceSink.capture` (`:186`) is the mirror: it blanks the
ego's pit and mode out of the recording, so a replay drives them from its action instead of
inheriting the recorded strategy. Freeze the field, vary the ego. That is A-05's entire
purpose, and it is why `test_seat_symmetry` is asserted on the live path only.

The shape check at `:136-142` is the old `_check_twin` guarantee, kept: a trace of the
wrong length raises at construction rather than misreplaying quietly from lap forty.

### senna/env/race_env.py — what the adapter kept

`step` (`race_env.py:243`) is now this, in order: read the pre-lap position for the
shaping term, coerce the action against the mask, `begin_lap`, collect twenty-two
decisions, snapshot v2's outgoing tyre if that arm is running, `advance_lap`, log the ego's
lap, score, rebuild the mask, return. Everything ego-shaped stayed: `_coerce`, `_snap_pit`,
`_ego_mask`, `_observe`, `_info`, the ego counters.

Legality stayed here too, and an examiner will push on that: masks and physics clipping are
still what makes SENNA compliant by construction (F-16, taught in F05), but the engine does
none of it. Hand `advance_lap` a slick in the wet and it will run that race faithfully. The
two-sentence answer: **the engine is a physics kernel and legality is a policy question, so
compliance is asserted where decisions are made — the learner goes through `_coerce` and
`_snap_pit`, the rivals through `rivals.pit_choices`, and both shop only compounds the
wetness allows. The seam cannot enforce that for a caller, so `senna/env/CLAUDE.md` writes
it down as a contract every new caller of the engine owes, along with a test that says so.**

`_field_decisions` (`:297`) is where twenty-one seats plus one become twenty-two:

```python
if pit_ego >= 1:
    pit[state.ego] = pit_ego - 1  # pit head 1..5 -> compound code 0..4
mode[state.ego] = mode_ego
return LapDecisions(pit=pit, mode=mode)
```

The rivals decide by archetype (or replay the trace), and the ego's heads are laid over the
top. From the engine's side no seat looks different. Notice the asymmetry in the pit line:
the ego slot is only overwritten when it asks to box, which is exactly why `TraceSink`
blanking the ego's recorded pit matters — a replayed ego that stays out would otherwise
silently serve the recording's stop.

`_v2_before_lap` (`:273`) and `_log_ego_lap` (`:282`) exist because the engine advances the
lap before the adapter scores it. One samples what must be read before the lap runs, the
other reads the finished `LapOutcome` for one seat. Both are the adapter's business by
definition: the engine reported the whole field and has no view on which of the twenty-two
anyone is watching.

### The tests

`RecordingRng` (`test_engine_identity.py:44`) is nine lines of `__getattr__` that forwards
every call to the real generator and writes down `(method, shape)`. The stream is
unchanged, so a race driven through it is the race the bare generator would have run. The
test drives the two phases itself, so every draw is attributed to the phase that made it
and no site can hide behind another with the same shape.

The part worth stealing is lines 204-211:

```python
assert any(len(lap["begin_lap"]) == 2 for lap in per_lap)
assert any(lap["decide"] for lap in per_lap)
assert any(name == "random" for lap in per_lap for name, _ in lap["advance_lap"])
```

A race that never neutralised, never failed a tyre and never pitted anybody would sail
through the per-lap loop without exercising three of the six draw sites. These four
assertions say "and we actually saw each of them happen". That is the canary pattern F14
introduced, applied here.

## What did not come out clean

Three things, recorded because the ship report says the same.

**`step()` came out at 31 lines against a spec criterion of "under 30".** It is 29 now, and
the way it got there is slightly uncomfortable: the review found `begin_lap` taking a
`scenario` argument it never used, and removing it folded a three-line call onto one line.
The criterion is met on a technicality. The honest version is that the ego bookkeeping a
Gymnasium adapter owes its caller costs about thirty lines, and a line count was always a
proxy for "contains no physics", which it genuinely does not.

**The committed throughput test asserts a ratio, not the 5% bar the plan wrote.**
`test_an_engine_lap_costs_less_than_an_env_step` (`test_engine_identity.py:266`) asserts
that an engine lap is not more expensive than the whole env step wrapping it, which is a
smoke alarm for a catastrophic regression and nothing more. The 5.6.2 reading (18,477
steps/s) is stamped with hardware, commit and config hash exactly so it is never read out
of context, so no portable test can assert "within 5% of 18,477". The real before/after
comparison was `make bench` run by hand on both commits: 0.9% down. That number is a
measurement, not a test, and it should be described that way in the viva.

**A mechanical edit ate a function.** During the extraction a line-range deletion took out
`_neighbours`'s `def` line and left its body orphaned inside the previous method. The
suite caught it within seconds, because `_observe` calls it on every step. The lesson is
boring and worth internalising anyway: line-range edits are blind, and the check for them
is not re-reading the diff, it is running the tests. Mechanical edit, then suite, every
time.

## How it connects

```
 configs/*.yaml ──► scenario.build_scenario ──► CircuitScenario (constants)
                                                      │
   ┌──────────────────────── the race ────────────────┼───────────────────┐
   │                                                  ▼                   │
   │  events_io: LiveSource | TraceSource ──►  engine.begin_lap           │
   │        (rolls or replays events)                 │  LapContext       │
   │                                        <decisions from every seat>   │
   │                                                  ▼                   │
   │  events_io: TraceSink ◄───────────────  engine.advance_lap ──► LapOutcome
   │        (records the twin)              (dynamics + pitlane, in place)│
   └──────────────────────────────────────────────────┬───────────────────┘
                                                      │
   ┌────────────────── the adapter (race_env) ────────┼───────────────────┐
   │  rivals.pit_choices ──► 21 seats                 │                   │
   │  agent action ──► _coerce/_snap_pit ──► 1 seat   │                   │
   │  LapOutcome ──► reward (3 terms) ──► obs ──► mask ──► info           │
   └──────────────────────────────────────────────────────────────────────┘
                              │
        MaskablePPO (F07) ────┘         serve/frames.py, eval, oracle: future customers
```

Same box in the 5.1 diagram as F05, cut in half. Everything below the line still trains
F07's agent exactly as before; everything above it is now callable by anything. F17 onward
sits on this seam.

## Try it yourself

Activate the venv first: `source .venv/bin/activate`.

1. **Read the seam.** Run `python -m pytest tests/env/test_engine.py -q` and then
   `python -m pytest tests/env/test_engine_identity.py -q -m "not slow"`. Open
   `tests/env/test_engine.py` and search for `F1RaceEnv`. You'll know it worked when you
   find zero hits and can say why that is the point of the file.

2. **Break the draw order the obvious way.** In `senna/env/events_io.py`, draw the
   failure rolls once instead of per car: add `rolls = rng.random(state.n_cars)` above the
   loop in `LiveSource.failures`, and replace the `events.tyre_failure(...)` call in the
   else branch with `state.tyre_age[car] > max_age + self._cliff_margin and rolls[car] <
   self._tyre_hazard` — same physics, one draw. Predict which test fails first. Then run
   `python -m pytest tests/env/test_engine_identity.py -q -m "not slow"`. You'll know it
   worked when `test_rng_draw_order_preserved` fails on a shape of `(22,)` where it wanted
   `()`, and `test_golden_trace_identical` fails on `cumulative_time_s` — one test names
   the cause, the other names the damage. Revert.

3. **Do a mutation test yourself.** In `race_env._v2_lap_facts`, ignore the `outgoing`
   argument and read the state instead: replace `outgoing_compound, outgoing_age =
   outgoing` with `outgoing_compound, outgoing_age = int(self._state.compound[ego]),
   int(self._state.tyre_age[ego])`. Run `python -m pytest tests/env/test_reward_v2.py -q`.
   You'll know it worked when exactly one test fails — the one written in response to this
   exact mutation. Now delete that test, keep the mutation, and run the file again: it goes
   green. That green is what the reviewer was looking at. Restore both.

4. **Try to close the mask lag, and learn two things instead of one.** The deferred defect:
   the ego's mask is built at the end of `step` from that lap's weather, but it is used to
   coerce the action on the *next* lap, while the twenty-one rivals read the current lap's
   conditions inside `_field_decisions`. The agent is structurally a lap behind its
   opponents on rain. Move `self._mask = self._ego_mask()` from the end of `step` to
   immediately after the `begin_lap` call and predict what breaks. Then run
   `python -m pytest tests/env/test_engine_identity.py -q -m "not slow"` and
   `python -m pytest tests/env/test_variants.py -q`.

   You'll know it worked when the golden traces *pass* and
   `test_penalty_env_permits_and_fines_a_two_compound_breach` *fails*, and you can explain
   both. The fixture is silent because neither recorded race ever rained, so a lagged
   weather mask and a current one are identical on every one of those laps — a photograph
   only covers what was in frame, which is the honest limit of the technique. The variants
   test fails because the naive move makes the mask stale on the *lap counter* too (it is
   now built before the lap it will be consumed on has run), so the two-compound "last
   chance to box" rule fires a lap late. The repo calls this fix "a one-line change"; that
   is the seam being open, not the whole job. Revert.

5. **Add something.** Write a new test in `tests/env/test_engine.py` that drives a solo
   race (`SOLO`) where every car requests `ATTACK` every lap, and asserts that the store
   stays inside `[0, usable_soc_mj]` and that at least one lap returned a non-zero
   `derate_penalty_s`. Use `_drive_to_flag` and a decision function shaped like
   `_everyone_stays_out`; you will need to collect the `LapOutcome`, which `_drive_to_flag`
   currently discards, so extend it or write your own loop. You'll know it worked when it
   passes and you can explain why no mask was involved anywhere in it (E-01: physics
   clips, the adapter masks).

For the throughput picture, `make bench WORKERS=4 STEPS=40000` gives you a local number in
about a minute. It is not comparable to the 18,477 figure in the spec, which was measured
on different hardware with twelve workers — compare it only to itself, across two commits.

## Check yourself

1. Why was the acceptance test for F16 byte-identical replay rather than "the existing
   test suite still passes"? What class of error does the suite structurally miss?

2. `LiveSource.failures` runs a Python loop over twenty-two cars in a codebase whose rule
   is "vectorise everything". Explain precisely what breaks if you vectorise it, and why
   the ordinary env tests would not notice.

3. Defend this design choice: the tick is two calls (`begin_lap`, then `advance_lap`) with
   decisions collected in between, rather than one `run_lap(state, decisions)`.

4. Defend this design choice: `test_seat_symmetry` is asserted on the live event path only,
   and the twin is documented as deliberately ego-aware rather than being fixed.

5. A reviewer replaced the `outgoing` snapshot in `_v2_lap_facts` with a read of the
   post-advance state and all 267 tests passed. What does that tell you, what is the
   technique called, and what did it produce?

---

### Answers

1. The suite tests the behaviours somebody thought to write down; a refactor can preserve
   every one of them and still change the simulation, because the thing most at risk here
   (the order in which the seeded generator is consumed) is invisible to any test that does
   not compare against a previously recorded race. The golden fixture is a photograph taken
   at the pre-change commit, with its generator committed beside it and the test importing
   the generator's seed and strategy, so the comparison cannot drift; equality rather than
   `allclose` because one ulp of difference means a draw moved.

2. `events.tyre_failure` only draws when a car is past its cliff, so the number of variates
   consumed per lap is data-dependent — usually zero. A single `rng.random(22)` consumes
   twenty-two every lap, which shifts every subsequent draw in the race and changes every
   seeded outcome. Nothing is *broken*, so determinism tests still pass (same seed, same
   race as itself), property tests still pass, and only a comparison against a recording
   made before the change can see it — which is what `test_rng_draw_order_preserved` and
   the golden fixtures are for.

3. The rival archetypes need to know whether a neutralisation just began before they can
   choose whether to box (E-06), so the track has to resolve before decisions are
   collected; a single call would force every decider to read last lap's track status.
   It also mirrors the real thing — the field observes the track, everyone commits, the lap
   runs — and it leaves the seam open at exactly the point where the deferred mask-lag fix
   has to be made: the ego's mask rebuild has somewhere sensible to move to now, which it
   did not before.

4. The live path can be genuinely symmetric because the asymmetry lives in field
   *construction*: `rivals.draw_field` fills the ego's slot with unit pace sigma and an
   infinite pit age, which is where it belongs, so the tick itself branches on nothing. The
   twin cannot be symmetric and should not be — recomputing the ego's tyre failure from its
   own age and blanking the ego's strategy out of the recording is exactly what A-05 is
   for, freezing the field while the ego varies, so weakening the property to cover both
   paths would prove less than testing the live path honestly and writing the twin's
   asymmetry down.

5. It tells you the behaviour was untested: the snapshot is a compensation the refactor
   introduced (the engine applies the pit swap before the adapter scores the lap), and
   nothing in the suite could distinguish it from a post-swap read. The technique is
   mutation testing — deliberately break working code and check whether the tests go red —
   and it produced `test_stint_end_grip_is_the_set_that_came_off`, which pins a worn MEDIUM
   as the outgoing set against a fresh HARD on the state, and uses MEDIUM rather than SOFT
   because Bahrain's fitted soft has `deg_a = 0.0` and would score identical grip either
   way.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| Behaviour-identity refactor (golden fixture) | F16 | Prove a refactor changed nothing by recording the output at the pre-change commit, committing the fixture with its generator beside it, and having the test import the generator's seed and strategy so the two cannot drift — exact equality, not `allclose`. |
| RNG draw order is part of the seed (5.5.5) | F16 | A seeded generator hands out variate 1, 2, 3 in call order, so moving one draw site silently changes every seeded race; SENNA's six sites are documented in `senna/env/CLAUDE.md` and the per-car tyre-failure loop must stay a loop because its draw count is data-dependent. |
| Two-phase tick (observe, commit, run) | F16 | `begin_lap` resolves the track, every seat then commits, `advance_lap` runs the lap — forced by E-06 (rivals need the neutralisation onset before they can decide), and the seam the deferred mask-lag fix will need. |
| Race-centric vs policy-centric (dependency inversion) | F16 | The race is a module the agent calls, not a method inside the agent's env; the evidence the old shape had failed was `serve/frames.py:34` reaching through `env._state` because there was no other door. |
| Event source/sink seam | F16 | Seven scattered `if self._twin is not None` branches replaced by one injected object — `LiveSource` rolls events, `TraceSource` replays them, `TraceSink` records them — so the physics stops knowing replay exists (A-05). |
| Mutation testing | F16 | Break working code on purpose and check the suite goes red; replacing the `outgoing` tyre snapshot with a post-advance read passed all 267 tests, which is how the missing assertion was found (the procedural form of F14's break-it-on-purpose rule). |
