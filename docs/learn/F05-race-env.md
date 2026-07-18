# F05 — F1RaceEnv, the environment the agent trains in

## What we built and why

Every feature so far has been scaffolding for this one. F01 got the data in, F02 fitted
the physics, F03 turned those fits into a simulator that races 22 cars for byte-identical
validation figures, F04 drew the track. F05 wraps all of it in the shape a reinforcement
learning agent can actually learn from.

Here is the picture in race terms. The agent is a strategist on the pit wall. Once per
lap the race pauses and asks it one question: do you want to pit — and if so, onto which
tyre — and which energy mode do you want the driver to run this lap? The agent answers,
the lap plays out under the physics, and the race hands back a new situation and a score
for how that lap went. That loop repeats for all 70-odd laps, and at the flag the agent
gets the points it scored. Do that a few million times and the agent learns which answers
win races.

The software shape for that loop is a Gymnasium environment, and it has a strict
interface: `reset()` starts a fresh race, `step(action)` plays one lap, and each step
returns an observation, a reward, and a flag saying whether the race is over. Stable
Baselines3 (F07, next feature) knows how to train against exactly this interface, which
is the whole reason we conform to it rather than inventing our own.

Two ideas do the heavy lifting and are worth stating up front. First, legality is
structural, not a penalty. The agent physically cannot pit into a closed lane or deploy
energy it does not have, because masks remove illegal choices before the agent picks and
physics clips whatever slips through — 100% compliance by construction (F-16), not a
reward term that hopes the agent learns the rules. Second, the reward has exactly three
terms and one of them is designed to sum to zero over any loop of positions, which sounds
pointless until you see the exploit it kills (F-15). Both get their own section below.

## New ideas in this feature

**A Gymnasium environment — the reset/step loop.** An RL environment is an object with
two methods that matter: `reset()` returns the starting observation, and `step(action)`
takes the agent's decision, advances the world one tick, and returns four things — the
next observation, a scalar reward, a `terminated` flag, and an info dict. The agent never
sees inside; it only sees observations and rewards, picks actions, and learns the mapping
between them. SENNA needs this shape because the whole 5.5 spec is written as a Gymnasium
env and F07's MaskablePPO trains against that contract. Mental model: it is the
video-game API. Press a button (action), the game draws the next frame (observation) and
updates your score (reward), and eventually shows GAME OVER (terminated). Here one lap is
one frame and the score is race points.

**MultiDiscrete action space.** The agent's action is not one number but two, chosen
together: a pit head with 6 options (stay out, or box onto Soft / Medium / Hard / Inter /
Wet) and a mode head with 4 (conserve / balanced / attack / defend). `MultiDiscrete([6,
4])` is Gymnasium's name for "two independent discrete choices at once" (spec 5.5). It
matters because a pit stop and an energy mode are genuinely separate decisions — you can
attack without pitting, or pit while conserving — so folding them into one flat list of 24
combinations would hide that structure from the agent. Smallest example: the action
`[2, 3]` means "pit onto Medium (head 0 = 2), run defend this lap (head 1 = 3)".

**Action masking, and why masks beat penalties (F-16).** A mask is a boolean vector, one
flag per action, saying which options are legal right now. Before the agent picks,
MaskablePPO reads the mask and zeroes the probability of every forbidden action, so it can
only ever sample a legal one. SENNA masks the discrete rules (pit lane closed, wrong tyre
for the weather, the two-compound rule) in `masks.py`, and clips the continuous ones (SOC
can't go negative, you can't deploy energy you don't have) inside `dynamics.py`. Together
that is the F-16 guarantee: the policy is legal by construction, every lap, with zero
training required to get there. The alternative — let the agent do anything and dock its
reward when it breaks a rule — is strictly worse, and here is the two-sentence viva
answer: **a penalty only discourages an illegal action in expectation after training, so
early in learning and on rare states the agent still executes illegal moves, and you can
never claim 100% compliance. A mask makes the illegal action unpickable, so compliance is
a property of the architecture rather than a hope about convergence.** The reason codes
matter too — each masked action carries a string like `two_compound_rule`, so the F09 SHAP
cards can tell a viewer *why* an option was off the table, not just that it was.

**The 32-dim observation as the agent's dashboard.** The observation is a fixed length-32
vector of floats, every slot named and defined in the 5.5.1 table: normalised lap number,
position, tyre compound one-hot, tyre age, grip, SOC, fuel, gaps to the cars ahead and
behind, track status, weather, and so on. It is the only thing the agent sees — its entire
view of the race is these 32 numbers. Every slot is scale-bounded to roughly [-1, 1] at
the point of encoding (a gap of 30 s or more reads as 1.0, position maps 1..22 onto 0..1).
That bounding matters for a subtle served-model reason: F07 wraps the env in VecNormalize
to standardise inputs, but if those running statistics ever drift between training and the
frozen deployed model, a pre-bounded observation degrades gracefully instead of exploding.
Mental model: it is the strategist's pit-wall monitor, and we deliberately fit every gauge
onto the same 0-to-1 dial so no single reading can dominate the others by accident.

**Potential-based reward shaping, and why it telescopes to zero (F-15).** This is the
subtlest idea in the feature, so slowly. The agent's real objective is championship
points at the flag, but points only arrive on the very last lap — that is a terrible
learning signal, because for 69 laps the agent gets nothing and cannot tell a good move
from a bad one. So we add *shaping*: a small per-lap nudge that says "you just gained a
place, warm; you just lost one, cold". The danger is that a naive position bonus is
farmable. In SENNA's v2 the agent found it: weave into a rival's dirty air, drop a place,
pull back out, retake it, and collect the "gained a place" bonus every single lap without
ever improving its actual race. It oscillated forever because each up-move paid and the
down-move that set it up was cheaper.

Potential-based shaping (Ng et al., 1999) fixes this by construction. You define a
potential `Phi(s)` on states — here `Phi(s) = -0.1 x position`, so a better place is a
higher potential — and the per-step shaping reward is `F = gamma x Phi(s') - Phi(s)`. The
theorem is that adding this term never changes which policy is optimal, and the reason is
that over any path returning to its starting state the `F` terms telescope to exactly
zero. Worked example, positions over five laps 5 -> 4 -> 5 -> 4 -> 5, gamma = 1:

    lap 1->2  F = 0.1x(5) - 0.1x(4) ... = -0.1x4 - (-0.1x5) = +0.1
    lap 2->3  F = -0.1x5 - (-0.1x4)                          = -0.1
    lap 3->4  F                                              = +0.1
    lap 4->5  F                                              = -0.1
    ------------------------------------------------------ sum = 0.0

Every place gained is worth +0.1; regaining it is worth exactly what losing it cost. The
weaving exploit now nets zero, so there is nothing to farm, and the only way to actually
raise your cumulative shaping is to finish in a better place than you started — which is
the real objective anyway. The viva answer: **potential-based shaping is the one form of
reward shaping proven not to change the optimal policy, because it is the difference of a
potential and so cancels over any cycle; we use it with gamma = 1 and Phi = -0.1 x
position precisely so the position bonus cannot be gamed by oscillating, which is the
exploit that broke v2 (F-15).** One catch to remember: gamma here must match F07's PPO
discount, or the telescoping is only approximate — the config comment flags that, and both
are 1.0 because a race is a finite horizon.

**Struct of arrays and the hot-loop rule.** The race state is not a list of 22 car
objects; it is a `RaceState` dataclass where each field is a numpy array of length 22 —
one array for all compounds, one for all tyre ages, one for all SOCs. So advancing the
whole field is vectorised numpy with no Python per-car loop, and nothing pandas-shaped is
ever reachable from `step()`. That is not a style preference, it is the 5.6.2 throughput
gate: F07 needs millions of steps, and a DataFrame in the hot loop would make that
untenably slow. Mental model: a spreadsheet stored as columns, not rows, so you operate on
a whole column at once.

**Seed discipline.** Everything random in a race — the starting grid, driver pace offsets,
the safety-car rolls, weather, per-lap noise, pit-stop draws — is drawn from a single
generator created in `reset(seed)`. No module-level RNG exists anywhere in the package. We
covered the deeper version of this in F03 (seeded Monte Carlo with `SeedSequence` stream
spawning); here the one-line reminder is that it is what makes a `SubprocVecEnv` worker
stateless — F07 runs many env copies in parallel processes, and each is fully determined by
the seed it was reset with, so the same seed reproduces the same race byte for byte (5.5.5).

## The code, guided

Everything lives under `senna/env/`. Reading order: the state container, then the pieces
`step()` orchestrates — events, dynamics, masks, pitlane, reward, observation — then
`race_env.py` itself, which strings them together, and finally `scenario.py`, which builds
the constants.

### state.py — the struct of arrays

`RaceState` (`state.py:13`) is the whole race in one frozen-shape dataclass, each field a
length-22 numpy array or a scalar. The comments name each field's role; the one method
that earns its keep is `positions` (`state.py:37`):

```python
keys = np.where(self.retired, np.inf, self.cumulative_time_s)
order = np.argsort(keys, kind="stable")
rank = np.empty(self.n_cars, dtype=int)
rank[order] = np.arange(1, self.n_cars + 1)
return rank
```

Classification is derived, never stored. A car's position is just its rank by cumulative
race time, computed fresh whenever asked. Retired cars get an `inf` key so they sink to the
back regardless of how far they got. This single choice is why the whole env never "swaps
positions" — overtakes, pit stops, everything, are just changes to `cumulative_time_s`, and
order falls out of the sort. The `stable` sort keeps the tiny grid offsets (set at reset)
breaking ties in grid order.

### events.py — track status, weather, tyre failure

Three pure helpers, each taking an explicit `rng` so nothing hangs off a global (5.5.5).
`advance_track_status` (`events.py:17`) rolls the per-lap safety-car hazards from green:
one uniform draw, compared against the cumulative SC / VSC / red thresholds. A VSC is kept
distinct from an SC and both from a red flag (E-03), because their strategic opportunities
are different and collapsing them would erase a real decision. `advance_weather`
(`events.py:35`) steps a dry/damp/wet Markov chain and then integrates a continuous
`wetness` scalar toward the new regime's target over three sub-sectors — the sub-lap
resolution the compound crossover needs (E-08). `tyre_failure` (`events.py:51`) is the
cliff:

```python
if age <= max_age + cliff_margin:
    return False
return bool(rng.random() < hazard_per_lap)
```

A set is safe up to and including the oldest age that compound was ever seen to run, plus a
margin. Only past that does a small per-lap failure hazard bite, and when it does the car is
forced to pit rather than the race ending — a mechanical failure of the tyre, not a DNF.

### dynamics.py — the physics the agent requests but does not control

This is core domain logic, so line by line where it counts. The module's job: the agent
asks for a pace mode, and physics decides what actually happens, clipping energy to what is
real (F-16 continuous half). All 22 cars at once, numpy in and out.

`per_lap_harvest_mj` (`dynamics.py:49`) is how much energy the car recovers this lap:

```python
harvest = min(scenario.h_max_mj, scenario.harvest_braking_mj + scenario.harvest_clipping_mj)
if track_status in (SC, VSC):
    harvest *= scenario.env["harvest"]["neutralized_scale"]
```

Braking plus super-clipping recovery, capped at the circuit's FIA per-lap recoverable
limit (`h_max_mj`, 8.5 MJ baseline per circuit, never a hard-coded literal). In 2026 that
cap almost always binds, so harvest is nearly constant and the 4 MJ store buffers the
difference — the lever the agent actually pulls is how much a *mode deploys*, not how much
it harvests. Under a neutralisation the field brakes less, harvest drops, and observation
slot #16 moves (E-03).

`resolve_energy` (`dynamics.py:68`) is the continuous clip that makes energy legal by
construction:

```python
available = soc_mj + intra * harvest_mj
delivered = np.minimum(request_mj, np.minimum(scenario.e_dep_mj, available))
derate = derate_penalty_s(request_mj, delivered, scenario.derate_penalty_s_per_mj)
soc_next = np.clip(soc_mj + harvest_mj - delivered, 0.0, scenario.usable_soc_mj)
```

Line one: what the store can supply this lap is its current charge plus the slice of
harvest usable within the lap. Line two: delivered energy is the request clipped to both
the circuit's deployable integral `e_dep_mj` and that available charge — you cannot deploy
what you do not have. Line three: any shortfall between what the mode asked for and what
was delivered is priced as a straight-line time loss, the derate (E-01) — the agent is not
forbidden from asking for too much, it just goes slower when the battery cannot back the
request. Line four: SOC updates and is hard-clipped to [0, 4] MJ, the store's real usable
window — never 8. This clip is why the property test can throw 100k random actions and SOC
never once leaves [0, 4].

`lap_time_s` (`dynamics.py:110`) assembles the joint lap-time model of 5.5.3, one term at a
time (`dynamics.py:127`):

```python
green = (
    scenario.t0_s + offset + deg + fuel_term + pace + derate_s + traffic + wet
    + driver_s + noise_s
)
mult = np.ones_like(green)
mult[track_status == SC] = scenario.status_mult["sc"]
mult[track_status == VSC] = scenario.status_mult["vsc"]
return green * mult
```

Base lap time, plus a compound offset, plus tyre degradation (`tyre_deg_s`, the T5 fit
`a x t0 x age**b`), plus the fuel-weight term, plus the pace the mode buys or pays, plus
any derate, plus a traffic penalty, plus a wet-mismatch penalty, plus the car's fixed
driver offset and this lap's random noise. Then a neutralisation *multiplies* the green
time — the spec pseudocode writes "+ status", but those SC/VSC constants are lap-time
multipliers, not additive seconds, so the code makes it a `x`. The `traffic` term
(`dynamics.py:122`) is where one of the honest simplifications lives, covered below.

### masks.py — the discrete legality, with reasons

`build_mask` (`masks.py:38`) returns two boolean vectors (pit head, mode head) and a dict
of reason codes. It starts everything legal and switches options off. The pit-lane and
weather rules are block-level: a closed lane masks every compound but leaves stay-out; a
too-wet track masks the slicks; the inter and wet tyres are masked outside their wetness
bands (E-08). The one rule to read line by line is the two-compound rule (`masks.py:65`):

```python
dry = weather == DRY and wetness <= validity["slick_max_wetness"]
if pit_open and dry and not second_compound_used and lap == total_laps - 1:
    pit[0] = False
    reasons["pit:0"] = TWO_COMPOUND_RULE
```

The FIA requires a dry race to use two different slick compounds. If it is the last lap on
which a car could still serve that requirement, the pit lane is open, the race is dry, and
the car has *not* yet run a second compound, then staying out (`pit[0]`) is masked — the
car is forced to box. This is F-20, and it is the sharpest example of the whole masking
philosophy: the rule is enforced by removing the illegal choice, not by penalising a car
that finishes non-compliant. The final invariant (`masks.py`, checked by
`test_no_head_is_ever_left_all_false`) is that no head is ever entirely False, because
MaskablePPO cannot sample from an all-forbidden head — there is always at least stay-out
and at least balanced.

### pitlane.py — the FIFO lane (E-05)

`resolve_pit_lane` (`pitlane.py:11`) is why double-stacking hurts:

```python
order = np.argsort(arrival_s, kind="stable")
prev_exit = -np.inf
for car in order:
    start = max(arrival_s[car], prev_exit + lane_gap_s)
    exit_s[car] = start + service_s[car]
    prev_exit = exit_s[car]
```

Cars are served in arrival order, and a car cannot start its stop until the one ahead of it
has cleared the lane plus a minimum gap. Two teammates boxing on the same lap therefore
stack: the second waits for the first, and loses real time doing it. FIFO here because of
E-05 — the queue is the mechanism behind stacking losses, and it is the reason positions
are recomputed from cumulative time rather than swapped in place.

### reward.py — three terms, one that telescopes

The whole module is the three terms of 5.5.4 and nothing else, which is the point (F-16
means legality never leaks in as a fourth term). `pace_shaping` (`reward.py:24`) divides by
the circuit's clean-lap sigma so the term is scale-free across circuits.
`shaping_step` (`reward.py:35`) is the potential-based position term:

```python
return gamma * position_potential(position, coef) - position_potential(prev_position, coef)
```

That is `F = gamma x Phi(s') - Phi(s)` with `Phi(s) = -0.1 x position`. At gamma = 1 it
telescopes, which is the F-15 property worked through above and pinned by
`test_position_shaping_nets_exactly_zero_over_a_closed_loop`. `terminal_points`
(`reward.py:41`) is the real objective:

```python
if dnf or final_position > len(points_table):
    return 0.0
return points_table[final_position - 1] / divisor
```

The 2026 points table scaled so P1 = 10 (divide by 2.5). A DNF pays zero, not a negative —
retirement already forfeits everything, and stacking a penalty on top double-counts the
risk, a documented choice in 5.5.4. There is no fastest-lap term anywhere; that point was
abolished from 2025 and its absence is deliberate (AR-11, F-07).

### observation.py — encoding the dashboard

`encode` (`observation.py:21`) fills the 32-slot vector. It is a flat assembly of scalars,
each line one slot from the 5.5.1 table: `obs[0]` normalised lap, `obs[1]` normalised
position, `obs[3+compound]` the one-hot tyre, `obs[14]` SOC over its 4 MJ capacity, and so
on. Two things worth noticing. The `_unit` helper (`observation.py:69`) clips signed
deltas to [-1, 1] so a gauge can never overshoot its dial. And the rival context
(`obs[19..21]`) is the actual neighbour's continuous tyre age and compound gap, not v2's
binary "is this an aggressive archetype" flag — the agent sees real relative tyre state,
which is what lets it reason about undercuts. The header notes the graceful-degradation
reason for bounding everything at source.

### race_env.py — the orchestrator

`F1RaceEnv` (`race_env.py:27`) is the Gymnasium class. `__init__` (`race_env.py:30`) builds
the scenario, declares `action_space = MultiDiscrete([6, 4])` and a Box observation space,
and unpacks every constant it will need from the config so `step()` never touches yaml.
`reset` (`race_env.py:69`) is the fresh race:

```python
super().reset(seed=seed)
self._rng = np.random.default_rng(seed)
...
grid = self._rng.permutation(n) + 1  # a seeded starting order, ego is car 0
```

One generator, seeded once, owns every random draw for the episode — the grid permutation,
the driver offsets, the rival pit laps, later the weather and noise. That is the whole of
seed discipline: reset the seed, and the race is reproducible (5.5.5). The ego car is index
0; the other 21 are the F05 placeholder field, each on a scripted one-stop, replaced by
real archetypes in F06.

`step` (`race_env.py:115`) is one lap, and its order is the model. Read it top to bottom:
capture the ego's position *before* the lap (for the shaping term), coerce the raw action
against the mask, advance the track status and weather, assemble each car's mode and pit
choice, roll tyre failures, compute gaps, resolve energy, compute lap times, apply the
pits, add the lap times to cumulative time, age the tyres, burn fuel, advance the lap
counter, then score the reward and rebuild the mask for the next decision. The reward call
(`race_env.py:169`) passes the *pre-lap* position so `shaping_step` compares old to new.

`_coerce` (`race_env.py:340`) is the continuous half of F-16 made explicit:

```python
if not mask.mode[mode]:
    mode = _BALANCED
if mask.pit[pit]:
    return pit, mode
if mask.pit[0] and pit != 0:
    return 0, mode  # asked for an unavailable compound; stay out
```

If the agent somehow requests a masked mode, it is snapped to balanced; if it requests a
masked pit, it is snapped to stay-out, or if even stay-out is masked (the two-compound
last lap), to a legal fresh compound. Under MaskablePPO this rarely fires, but it is the
belt-and-braces guarantee that a raw action can never execute something illegal — masks
propose, physics disposes.

`action_masks` (`race_env.py:173`) is the method MaskablePPO calls to read the current
mask; `_info` (`race_env.py:363`) packs the reward decomposition, the mask with its
reasons, and the energy state into the info dict every step, which is where F09's decision
cards get their raw material.

### scenario.py — the era switch (A-10)

`build_scenario` (`scenario.py:65`) is the one place constants are assembled, at
construction, so the hot loop never reads yaml or calls a fitter. Its interesting job is
the era switch (A-10): one recipe over two constant files. The `if era == "2026"` branch
(`scenario.py:97`) reads the synthetic 2026 layer — the T4 energy integrals, the T8 pace
residual, the per-circuit harvest cap — while the else branch reads the 2024 MGU-K numbers,
where `e_dep_mj` is bounded by the old per-lap MGU-K budget instead of a deployable
integral. The fine energy-mode coefficients (attack gain, derate, dirty-air, SOC floor) are
the 2026 fit, and the 2024 counterfactual borrows them pending its own fit — a documented
coarseness that F14 refines. A circuit with fewer than two fitted slicks raises rather than
silently breaking the two-compound rule (`scenario.py:85`).

## Two honest simplifications worth knowing

These are deliberate and plan-approved, and an examiner may ask about them, so know them
cold.

**On-track passing is ordered by time, not a stochastic pass gate (E-07).** SENNA does not
roll an explicit probability that car A passes car B. Instead every car's `cumulative_time_s`
advances by its own lap time, position is the rank of that time (`state.positions`), and a
faster car naturally moves up the order. Traffic enters as a pace term: a car within the
dirty-air threshold of the one ahead takes the `dirty_air_penalty_s` hit in `lap_time_s`
(`dynamics.py:122`), which slows it just as following in disturbed air really does. So E-07
is handled through the traffic term rather than a `P(pass)` coin flip. The viva answer:
**overtaking emerges from lap-time differences plus a dirty-air penalty rather than an
explicit stochastic pass model, which keeps the dynamics deterministic given the seed and
avoids a second unfitted probability; the cost is that we do not model a driver holding
position against a genuinely faster car, which F06's archetypes can add.**

**Several "fitted" constants are landed as `stylised` (F06/F08 supersede).** The master
spec calls the SC/VSC pit-loss multipliers, the tyre-failure hazard, the weather Markov
rows, the mode-request fractions and a few others "fitted". No fit exists yet — the notebooks
that would produce them are F06 and F08 work. Rather than block F05 or invent a fake
provenance, `configs/env.yaml` marks each one `stylised` and names the future feature and
data source that could replace it with a real fit (read the comments; every stylised line
says which). This is the interpretability contract working as intended: an honest
`stylised` flag with a named successor beats a `fitted` label with no notebook behind it.
It is a plan-approved divergence, not an oversight, and F08's ablations will test how much
any of these actually move the policy.

## How it connects

```
   F02 fits + F03 synthetic layer            configs/*.yaml (env, physics_2026/2024,
   (transforms.yaml, physics_params)          transforms, circuits) with provenance
            │                                        │
            └──────────────┬─────────────────────────┘
                           ▼
                   scenario.build_scenario   (era switch A-10, one recipe two files)
                           │  CircuitScenario: every constant the hot loop needs
                           ▼
   reset(seed) ──► RaceState (struct of arrays, 22 cars)
        │
        ▼
   step(action):  mask ─► coerce ─► events ─► dynamics (harvest/deploy/derate, lap time)
                    ─► pitlane FIFO ─► classify by cumulative time ─► reward (3 terms)
        │
        ├──► observation (32-dim, [-1,1])  ─────►  MaskablePPO agent (F07)
        ├──► reward.total                  ─────►  the training signal
        └──► info{reward_terms, mask+reasons, energy}  ─────►  SHAP cards (F09)
```

F05 is the environment box of the spec 5.1 pipeline: fitted physics and config in, a
trainable Gymnasium env out. F07 trains against it, F06 replaces the placeholder field with
real rival archetypes, and F09 reads the per-step info to explain each call. Nothing
upstream depends on it; everything the agent ever learns flows through it.

## Try it yourself

The fast env tests need no database or FastF1 cache:
`.venv/bin/python -m pytest tests/env -q`.

1. Change a reward constant and predict the effect. In `configs/env.yaml` set
   `reward.position_potential_coef` to 0.0. Before running anything, predict what happens
   to `shaping_step` and to the telescoping test. Then run
   `.venv/bin/python -m pytest tests/env/test_reward.py -q`. You'll know it worked when you
   can say why zeroing the coefficient makes every shaping reward exactly 0 while the
   telescoping test still passes (0 sums to 0) but
   `test_a_single_place_gained_is_worth_the_coefficient` fails. Revert.

2. Break the SOC clip and read the failure. In `dynamics.resolve_energy`, change the
   `soc_next` clip upper bound from `scenario.usable_soc_mj` to `8.0`, then run the
   property suite `.venv/bin/python -m pytest tests/env/test_properties.py -q`. You'll know
   it worked when the "SOC never leaves [0, 4]" property fails — and you'll have felt why 8
   MJ is on the "never write" list. Revert.

3. Break the two-compound mask. In `masks.build_mask`, delete the `pit[0] = False` line in
   the F-20 block and run
   `.venv/bin/python -m pytest tests/env/test_masks.py::test_stay_out_is_masked_on_the_last_dry_pit_lap_without_a_second_compound -q`.
   You'll know it worked when it fails — stay-out is no longer masked, so a car could finish
   a dry race on one compound. Revert.

4. Prove seed determinism, then break it. Run
   `.venv/bin/python -m pytest tests/env/test_determinism.py -q` and watch it pass. Now in
   `race_env.reset`, add a stray `np.random.random()` call after the `_rng` line and rerun.
   Predict first: does `test_the_same_seed_and_actions_reproduce_the_episode` still pass?
   You'll know it worked when it does — because that global draw does not touch `self._rng`,
   so it happens to be harmless here, which is exactly why the rule bans globals rather than
   trusting luck. (Try instead replacing one `self._rng.normal(...)` with
   `np.random.normal(...)` to actually break reproducibility across processes.) Revert.

5. Add one small thing. In `_terminal_info` (`race_env.py:397`), add a `"laps_led"` field —
   you'll need to track it in `step` by incrementing a counter whenever the ego's position
   is 1 after classification. Write a test in `tests/env/test_race_smoke.py` asserting a
   dominant ego (give it a big negative `driver_s`) leads at least one lap. You'll know it
   worked when your test passes and the existing smoke tests still do.

## Check yourself

1. Why does SENNA enforce legality with action masks and physics clipping rather than
   reward penalties? What can you claim about compliance under masking that you cannot claim
   under penalties?

2. Walk the reward for a car that loses a place on lap 10 and regains it on lap 11
   (gamma = 1, coef = 0.1). What is the net position-shaping reward over those two laps, and
   what design goal does that number serve?

3. Defend this design choice: the position term is potential-based rather than a flat
   "+0.1 per place gained" bonus. Name the exploit the flat version enabled and the theorem
   that rules it out.

4. The energy store is clipped to [0, 4] MJ and deployment is clipped to what the store can
   supply. Where in the code does each clip live, and why is a derate penalty applied on a
   shortfall instead of forbidding the over-request outright?

5. SENNA has no explicit `P(pass)` overtaking model. How does a faster car get ahead of a
   slower one, and how is the cost of following in traffic represented? Name the edge case
   this handles.

---

### Answers

1. Masks remove illegal actions before the agent samples and physics clips the continuous
   ones, so an illegal action can never execute — compliance is a property of the
   architecture (F-16), true on every lap from the first step of training. A penalty only
   discourages illegality in expectation after the agent has learned, so early in training
   and on rare states it still breaks rules, and you can never truthfully claim 100%
   compliance by construction.

2. Losing the place (say 4 -> 5) pays `0.1x4 - 0.1x5 = -0.1`; regaining it (5 -> 4) pays
   `0.1x5 - 0.1x4 = +0.1`; net exactly 0. That zero is the goal: the agent gains nothing
   from oscillating, so the only way to raise cumulative shaping is to actually finish
   better than it started, which is the real objective (F-15).

3. A flat per-place bonus is farmable: in v2 the agent weaved to drop a place and retook it
   every lap, collecting the bonus without improving its race. Potential-based shaping,
   `F = gamma x Phi(s') - Phi(s)`, is the difference of a potential, so it telescopes to
   zero over any cycle and, by the Ng et al. (1999) theorem, cannot change which policy is
   optimal — the exploit nets zero and disappears.

4. The SOC clip is `np.clip(..., 0.0, usable_soc_mj)` in `dynamics.resolve_energy`; the
   deployment clip is the `np.minimum(request, min(e_dep, available))` on the line above.
   The shortfall is priced as a derate (a straight-line time loss, E-01) rather than
   forbidden because the agent is free to *ask* for aggressive deployment — physics simply
   makes it slower when the battery cannot back the request, which is a truer model than an
   illegal-action rejection.

5. Every car's `cumulative_time_s` advances by its own lap time and position is the rank of
   that time (`state.positions`), so a faster car naturally climbs the order — no coin flip.
   Following in dirty air is priced by the `dirty_air_penalty_s` term in `lap_time_s` when a
   car is within the threshold gap of the one ahead. This is how E-07 (backmarker traffic /
   overtaking) is handled without a separate stochastic pass model.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| Gymnasium environment (reset/step loop) | F05 | An RL env exposing `reset()` and `step(action)` that returns observation, reward, terminated and info; the agent sees only observations and rewards and learns the mapping — SB3 trains against this contract (5.5). |
| MultiDiscrete action space | F05 | Two independent discrete choices picked together, `MultiDiscrete([6, 4])` — a pit head and a mode head — so the structure of "pit and mode are separate decisions" is visible to the agent (5.5). |
| Action masking (legal by construction, F-16) | F05 | A boolean vector per head zeroing illegal actions before sampling, plus physics clipping of continuous limits; together 100% compliance by architecture, with reason codes, not a reward penalty. |
| Scale-bounded observation | F05 | The 32-dim ego vector (5.5.1), every slot named and pre-clipped to about [-1, 1] at encode time, so a served model degrades gracefully if VecNormalize statistics drift. |
| Potential-based reward shaping (telescoping, F-15) | F05 | Shaping `F = gamma x Phi(s') - Phi(s)` with `Phi = -0.1 x position`; provably policy-invariant and sums to zero over any position cycle, killing the oscillation exploit that broke v2. |
| Struct of arrays / hot-loop rule | F05 | Race state as one numpy array per attribute across all 22 cars, not per-car objects, so the field advances in vectorised numpy with nothing pandas-shaped reachable from `step()` (5.6.2). |
| Era switch (A-10) | F05 | One `build_scenario` recipe reading either physics_2026 (synthetic energy integrals) or physics_2024 (MGU-K budget), so the same env code runs both the 2026 race and the 2024 counterfactual. |
