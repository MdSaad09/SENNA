# Results — three circuit archetypes, four categories

The proposal promises an agent evaluated across three circuit archetypes and scored on
four things: strategy performance, generalisation, explainability and constraint
validity. This is that chapter. The full eleven-metric framework it draws on is in
`F14-evaluation.md`, unchanged; nothing here re-runs anything.

Model `senna-ppo-5e3ddb15d584-C-01769472`, frozen. Every figure is a slice of the stored
480-pair evaluation — same races, same seeds, same model — so the numbers here and in the
full table agree by construction. Regenerate with `python -m senna.eval.archetypes`.

## Why these three circuits

They were chosen on the fits, not on reputation.

Only a handful of circuits have a 2026 degradation curve fitted from real 2026 running.
The season is partial, and E-14 freezes rounds 1–6 as the calibration set and holds
everything from round 7 out, so every other circuit's tyre model is supplied by the T5
transform from 2022–25 data. Of the circuits that do have native fits, two cannot carry a
strategy: **Miami**'s soft and hard curves are flagged low-confidence, and **Canada**'s
three compounds decay identically — a spread of exactly zero, meaning the model cannot
tell a soft from a hard there.

That leaves three, and they are genuinely different circuits:

| Archetype | Circuit | Race laps | Character |
|---|---|---|---|
| Balanced | Chinese Grand Prix | 56 | highest compound spread of the three |
| Flowing | Australian Grand Prix | 58 | low degradation, track position |
| Street | Monaco Grand Prix | 78 | pit loss dominates, overtaking scarce |

## 1. Strategy performance

| Metric | Chinese | Australian | Monaco |
|---|---|---|---|
| Paired position delta vs the scripted baseline (M1) | −0.45 | +0.30 | +0.35 |
| 95% CI | [−1.50, 0.50] | [−0.40, 1.15] | [−0.30, 1.00] |
| Finished ahead of the baseline | 30% | 30% | 50% |
| Oracle regret, median (M3) | 70.5 s | 39.8 s | 48.8 s |
| Pit window accuracy (M6) | 0.000 | 0.130 | 0.083 |

Twenty paired seeds per circuit. **Across these three the agent is at parity with the
scripted baseline** — mean +0.07 places, and every interval spans zero.

That is not the published headline, which is **+2.279 places over all 24 circuits**, CI
[1.913, 2.663]. The difference between those two numbers is the most important result in
this chapter and it has its own section below.

Two whole-bank figures belong here and cannot be sliced, because their stored payloads
carry no per-race breakdown: **tyre failures 37.92 per 100 races** (M9) and **energy
utilisation 0.704** against a 0.912 ceiling (M4). They are reported whole and read with
the rest.

## 2. Generalisation

One policy, trained once, races all three archetypes with no per-circuit retraining, and
the strategies it produces differ by circuit:

| Metric | Chinese | Australian | Monaco |
|---|---|---|---|
| Strategy diversity, entropy over stint plans (M7) | 0.858 nats | 0.665 | 0.897 |
| Luck share of finishing-position variance (M11) | 0.641 | 0.988 | 0.916 |

The diversity figures are above the 24-circuit mean of 0.653 nats: the agent is not
running one memorised plan everywhere.

The luck share is the honest counterweight. At Australia **0.988 of the variance in where
the agent finishes is attributable to the event draws rather than to its decisions** —
safety cars, weather, tyre failures. On a low-degradation circuit with little overtaking
there is very little for a strategist to decide, and the metric says so. Read the parity
result above in that light: at Australia and Monaco there was not much on the table for
anyone to win.

**Generalisation to reality is not claimed.** M8, the sim-to-real check, failed on all
five circuits tested, worst KS 0.931, against a split frozen before any fitting. The
agent generalises across circuits *within* the simulator; whether the simulator
generalises to a real 2026 season is measured, reported and not established.

## 3. Explainability

| Method | Status | Evidence |
|---|---|---|
| Reward decomposition | primary | three served terms per lap: pace shaping, potential-based position, terminal points |
| Counterfactual comparison | secondary | agent vs the driver's real strategy on the same event trace, era-matched |
| SHAP feature attribution | exploratory | surrogate agreement 99.76% pit / 98.19% energy mode |

The hierarchy is the proposal's own and the interface enforces it: reward decomposition
first, alternatives second, SHAP behind a collapsed panel.

The reason SHAP is third is not modesty. It is computed against a surrogate model fitted
to the agent's decisions, not against the policy network, because SHAP does not transfer
cleanly to a policy network. The surrogate's agreement with the policy is measured rather
than assumed, and that measurement bounds how far the attribution can be trusted. An
explanation of a 99.76%-faithful stand-in is a useful thing; an explanation of the policy
is not what it is.

The counterfactual comparison against real 2024 strategies (M2) is **1 win, 8 losses,
1 tie, p = 0.039** — the agent is measurably worse than the real drivers' real strategies
over those ten races. That is reported in full in `F14-evaluation.md` and read alongside
M8: it is an in-simulator comparison, and the simulator's fidelity to reality is the
thing that failed its own test.

## 4. Constraint validity

| Metric | Result |
|---|---|
| Coerced or illegal actions over 480 races (M10) | **0** |
| Strategies the mask had to alter | 0 |
| Two-compound rule violations | 0 |

Compliance is 100% **by construction, not by observation**. Legality is enforced by the
action mask before the policy chooses, so an illegal action is not something the agent
learned to avoid — it is something the action space does not contain. Nothing here can be
gamed by a well-shaped reward, because legality is not in the reward at all. A standing
property test fires 100,000 random actions at the mask; this row is the other half of the
claim, that no evaluation log contains an illegal executed action either.

This is the strongest result in the project and the cheapest to verify.

## The advantage is conditional on the tyre model

Slicing M1 to the three archetypes made the headline disappear. The reason turned out to
matter more than the slice.

Group the 24 circuits by where their 2026 degradation model came from:

| Circuits | n pairs | M1 delta | Median regret | Agent stops | Oracle stops |
|---|---|---|---|---|---|
| **Calibrated** — fitted from real 2026 data | 60 | **+0.07** | 49.3 s | 1.18 | 1.62 |
| **Synthesised** — T5 transform supplied the curve | 360 | **+3.31** | 25.9 s | 1.14 | 1.36 |
| Unusable — Miami low-confidence, Canada zero spread | 40 | −2.30 | 512.4 s | 1.63 | 2.53 |

**The published +2.279 is carried by the circuits whose tyre model was invented.** Where
the model is anchored to real 2026 running, the agent is at parity.

The mechanism is already in the metric table. **The agent under-stops.** The oracle wants
1.62 stops on calibrated circuits and the agent makes 1.18; on synthesised circuits the
optimum is 1.36 and the agent makes 1.14 — much closer. This is M9 seen from a second
angle: 37.92 tyre failures per 100 races, an agent that buys track position by
over-running its tyres. Where the T5 transform smooths degradation, over-running is cheap
and the habit pays three places. Where degradation is fitted from real running, it bites,
and the habit gives back everything it gained. No race in the bank ends in a retirement —
the cost is pure time.

Three explanations remain live and this evaluation does not separate them: the transform
may leave exploitable regularity the scripted baseline does not chase; the rival pace
models are fitted from the same data, so the field may simply be tighter where that data
exists; or five circuits is too few to rule out character effects. Degradation magnitude
alone does not explain it — it correlates with the advantage at r = +0.53 across the 24,
but Chinese and Bahrain have near-identical degradation and differ by eight places.

**The defensible claim** is therefore narrower than the headline: SENNA beats scripted
strategies inside its own simulator by a margin that depends on the tyre model, and the
tyre model's fidelity to a real 2026 season has not been established. That is a smaller
result than +2.279 places. It is the one the evidence supports.

## What this chapter does not show

- **Any claim about a real 2026 race.** M8 failed; the simulator is not calibrated to
  reality and the write-up says so wherever a number could be mistaken for a prediction.
- **A per-archetype figure for M4, M5, M9 or M10.** Those payloads store bank-level
  aggregates only. Producing per-circuit versions means re-running the suite, which is a
  different experiment from the one these numbers came from.
- **Human-strategist comparison beyond M2's ten races.** Ten is what the counterfactual
  bank holds.

## Strategy robustness — does the agent read the physics, or this physics?

An agent that memorised one parameter set would make the same call whatever you did to
the world. One that learned the structure of the problem should move its stop the way a
strategist would predict when you change what a stop is worth.

Six perturbations on the three archetypes, raced on the **published test bank's own
seeds** — the same races the reported metrics came from, so a shifted stop is the
perturbation talking rather than a different draw. Each arm is a copy of the config tree
with one field changed and nothing else. 60 races per arm.

The arms are not all the same kind of experiment, and the difference decides what
movement means:

- **controlled** — the physics moves and the race is otherwise intact, so a shifted stop
  can only be the policy responding.
- **confounded** — the perturbation changes the event distribution itself. Raise the
  safety-car rate and a different safety car happens on a different lap, so the stop
  moves whether or not the policy noticed anything.
- **scenario** — the world model is untouched and the agent simply starts somewhere else.

| Arm | Kind | Predicted | Earlier | Later | Unchanged | Agreed |
|---|---|---|---|---|---|---|
| Tyre degradation +10% | controlled | earlier | 6 | 0 | 54 | **6 of 6** |
| Tyre degradation −10% | controlled | later | 2 | 8 | 50 | **8 of 10** |
| Pit loss +2 s | controlled | later | 0 | 0 | **60** | — |
| Pit loss −2 s | controlled | earlier | 0 | 0 | **60** | — |
| Energy coefficients +20% | controlled | none | 0 | 0 | **60** | — |
| Energy coefficients −20% | controlled | none | 0 | 0 | **60** | — |
| Safety-car rate +50% | confounded | none | 4 | 0 | 56 | — |
| Safety-car rate −50% | confounded | none | 1 | 2 | 57 | — |
| Rain probability +50% | confounded | none | 0 | 0 | **60** | — |
| Rain probability −50% | confounded | none | 2 | 0 | 58 | — |

Grid sweep, physics untouched, mean lap of the first stop: **P2 → 4.42, P8 → 4.55,
P16 → 4.80**.

Reproduce with `python -m senna.eval.robustness --seeds 20`, about twenty seconds.

### What the arms say

**Degradation: the right direction, rarely.** When the stop moves under a degradation
change it moves the way it should — 14 of the 16 moves across both arms — which is
evidence the agent reads tyre state rather than replaying a plan. It does not move in
roughly 85% of races.

**Pit loss: no response, and the reason is architectural.** Two seconds on a
twenty-four-second stop, about 8%, moved nothing in either direction. **Pit loss is not
in the observation.** The 32 dimensions carry `pit_count_norm` and `pit_lane_open` and
nothing about what a stop costs; the environment applies a per-circuit pit loss to the
lap time and the policy never sees the number. An agent asked to decide when a stop is
worth taking was never told the price.

**Energy: cleanly decoupled, which is the answer we wanted.** No prediction was made
here — the question was whether pit timing bleeds into the energy model — and a 20% swing
in what a megajoule is worth moved no stop at all. The two decisions are independent in
the policy as they are in the design.

**Grid position: the information is there and unused.** Starting P2 rather than P16
moves the first stop by four tenths of a lap. Unlike pit loss this is not a missing
input: `position_frac` and `places_gained_frac` are both observed. The agent can see
where it started and does not change its plan because of it.

### The finding underneath all of them

The arms keep returning "unchanged" because there is very little to change. The agent
has close to one strategy:

| | Agent | Oracle |
|---|---|---|
| First stop, median lap | **3** | 17 |
| First stop, mean lap | 5.0 | 18.8 |
| Stops per race | 1.18 | 1.62 |
| Laps run on the final set | **52.9 mean, 75 max** | — |

It boxes almost immediately and then runs to the flag. On circuits whose tyre cliff sits
at 31–34 laps, a mean final stint of 52.9 laps is not a strategy that occasionally fails —
it is one that must.

That single behaviour explains four results that were being read as four problems. M6's
pit-window accuracy of 0.21 is a stop nowhere near the post-hoc optimum. M9's 37.92 tyre
failures per 100 races are those final stints arriving at the cliff. The under-stopping
against the oracle is the same fact counted differently. And the advantage vanishing where
degradation is real (above) is what happens when a forgiving tyre model stops forgiving.

So the honest summary of this study is not "the agent is robust". Of six perturbations,
one produces a directionally correct response in about 15% of races and five produce
almost nothing. **The policy is close to open-loop**: it has learned an opening move and
carries it out largely regardless of the world it is placed in. That it is the *right*
opening move often enough to beat a scripted baseline on eighteen circuits is a real
result, and a much narrower one than the headline suggests.

The obvious next step is the one the pit-loss arm points at — put pit loss in the
observation and retrain — and it is out of scope here, because the frozen triplet is what
every reported number in this document is measured on.
