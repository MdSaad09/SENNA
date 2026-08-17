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

Two knobs, each moved up and down, on the three archetypes. Each arm is a copy of the
config tree with one field changed and nothing else, raced on the **published test bank's
own seeds** — the same races the reported metrics came from, so a shifted stop is the
perturbation talking rather than a different draw. 60 races per arm.

| Arm | Predicted | Moved earlier | Moved later | Unchanged | Agreed with prediction |
|---|---|---|---|---|---|
| Tyre degradation +10% | earlier | 6 | 0 | 54 | **6 of 6** |
| Tyre degradation −10% | later | 2 | 8 | 50 | **8 of 10** |
| Pit loss +2 s | later | 0 | 0 | **60** | — |
| Pit loss −2 s | earlier | 0 | 0 | **60** | — |

Reproduce with `python -m senna.eval.robustness --seeds 20`.

**Degradation: the right direction, rarely.** When the agent's stop moves under a
degradation change it moves the way it should — 14 of 16 moves across the two arms — which
is evidence it is reading tyre state rather than replaying a fixed plan. But the stop is
unchanged in roughly 85% of races. A 10% change in wear rate is mostly invisible in its
behaviour.

**Pit loss: no response at all, and the reason is architectural.** Two seconds on a
roughly 24-second stop — about 8%, and the difference between a clean stop and a fumbled
one — did not move the first stop in a single race out of 60, in either direction.

That is not the agent ignoring evidence. **Pit loss is not in the observation.** The
32-dimensional observation (`senna/explain/features.py`) carries `pit_count_norm`, how
many stops have been made, and `pit_lane_open`, whether the lane is available. It carries
nothing about what a stop *costs*. The environment applies a per-circuit pit loss to the
lap time, and the policy never sees the number, so it cannot condition on it. Whatever
circuit-specific pit behaviour the agent has, it learned through features that correlate
with pit loss rather than from pit loss itself.

This is the most useful thing the study found, and it is a limitation of the design rather
than of the training: **an agent asked to decide when a stop is worth taking was never
told what a stop costs.** The obvious next step is to add pit loss to the observation and
retrain, which would test whether the insensitivity is the missing input or something
deeper. That is out of scope here — the frozen triplet is what every reported number is
measured on, and changing the observation invalidates all of them.

Read this beside the conditional-advantage result above. Both point the same way: the
agent's competence is narrower than the headline suggests. It reads tyre state, in the
right direction, some of the time. It cannot read the cost of acting on it.
