# Results — three circuit archetypes, four categories

The proposal promises an agent evaluated across three circuit archetypes and scored on
four things: strategy performance, generalisation, explainability and constraint
validity. This is that chapter. The full eleven-metric framework it draws on is in
`F14-evaluation.md`, unchanged; nothing here re-runs anything.

Model `senna-ppo-405658360cd8-C-02211840`, frozen — the F24 retrain, after the
tyre-model repair. The pre-repair version of this chapter, with every number it
reported, is preserved at `F14-pre-repair/`. Every figure here is a slice of the stored
480-pair evaluation — same races, same seeds, same model — so the numbers here and in
the full table agree by construction. Regenerate with `python -m senna.eval.archetypes`.

## Why these three circuits

They were chosen on the fits, not on reputation.

Only a handful of circuits have a 2026 degradation curve carrying their own real 2026
running. The season is partial, and E-14 freezes rounds 1–6 as the calibration set and
holds everything from round 7 out, so every other circuit's tyre model is supplied by
the T5 transform from 2022–25 data. Since F24 the honest label for the calibration
circuits is **repaired** rather than calibrated: their soft compound's wear was
unidentifiable even when every circuit's residuals were pooled, so its curve comes from
the repair ladder's cross-era prior, stated on the fit. Of the circuits with their own
data, Miami still cannot carry a strategy — its own medium and hard stay flagged
low-confidence — and Canada, whose identical-decay compounds were exactly the
bound-clips F24 repaired, now classes as repaired alongside the three below.

| Archetype | Circuit | Race laps | Character |
|---|---|---|---|
| Balanced | Chinese Grand Prix | 56 | highest compound spread of the three |
| Flowing | Australian Grand Prix | 58 | low degradation, track position |
| Street | Monaco Grand Prix | 78 | pit loss dominates, overtaking scarce |

## 1. Strategy performance

| Metric | Chinese | Australian | Monaco |
|---|---|---|---|
| Paired position delta vs the scripted baseline (M1) | −0.10 | −0.75 | −0.65 |
| 95% CI | [−1.00, 0.70] | [−1.35, −0.20] | [−1.60, 0.10] |
| Finished ahead of the baseline | 35% | 10% | 25% |
| Oracle regret, median (M3) | 85.9 s | 56.7 s | 80.3 s |
| Pit window accuracy (M6) | 0.431 | 0.553 | 0.333 |

Twenty paired seeds per circuit. **Across these three the agent is slightly behind the
scripted baseline** — mean −0.50 places — where the pre-repair agent was at parity.

That is not the published headline, which is **+2.288 places over all 24 circuits**, CI
[1.946, 2.648]. The difference between those two numbers is the most important result
in this chapter and it has its own section below.

Two whole-bank figures belong here and cannot be sliced, because their stored payloads
carry no per-race breakdown: **tyre failures 0.42 per 100 races** (M9, met — 37.92
before the repair) and **energy utilisation 0.648** against a 0.916 ceiling (M4,
missed, with the derate share now under its 5% cap). They are reported whole and read
with the rest.

## 2. Generalisation

One policy, trained once, races all three archetypes with no per-circuit retraining,
and the strategies it produces differ by circuit:

| Metric | Chinese | Australian | Monaco |
|---|---|---|---|
| Strategy diversity, entropy over stint plans (M7) | 1.877 nats | 2.009 | 2.290 |
| Luck share of finishing-position variance (M11) | 0.730 | 0.881 | 0.749 |

Diversity roughly tripled with the repair (the bank mean is 1.728 nats against 0.653
before): when tyres wear, one memorised plan stops being viable and the policy behaves
like it.

The luck share is the honest counterweight, and it moved the way the physics says it
should: the bank mean fell from 0.786 to 0.630. At Australia 0.881 of finishing-position
variance is still the event draw — on a low-degradation circuit with little overtaking
there is only so much for a strategist to decide — but strategy now carries more of the
outcome everywhere, which is the repair visible in the analytics.

**Generalisation to reality is not claimed.** M8, the sim-to-real check, failed on all
five circuits tested against a split frozen before any fitting. The agent generalises
across circuits *within* the simulator; whether the simulator generalises to a real
2026 season is measured, reported and not established.

## 3. Explainability

| Method | Status | Evidence |
|---|---|---|
| Reward decomposition | primary | three served terms per lap: pace shaping, potential-based position, terminal points |
| Counterfactual comparison | secondary | agent vs the driver's real strategy on the same event trace, era-matched |
| SHAP feature attribution | exploratory | surrogate agreement 98.57% pit / 98.10% energy mode |

The hierarchy is the proposal's own and the interface enforces it: reward decomposition
first, alternatives second, SHAP behind a collapsed panel.

The reason SHAP is third is not modesty. It is computed against a surrogate model
fitted to the agent's decisions, not against the policy network, because SHAP does not
transfer cleanly to a policy network. The surrogate's agreement with the policy is
measured rather than assumed, and that measurement bounds how far the attribution can
be trusted. An explanation of a 98.57%-faithful stand-in is a useful thing; an
explanation of the policy is not what it is.

The counterfactual comparison against real 2024 strategies (M2) is **3 wins, 3 losses,
4 ties, mean +0.40, p = 1.0** — a wash, where the pre-repair agent lost 8 of 10
significantly. Still short of the +1.0 target, and read alongside M8: it is an
in-simulator comparison, and the simulator's fidelity to reality is the thing that
failed its own test.

## 4. Constraint validity

| Metric | Result |
|---|---|
| Coerced or illegal actions over 480 races (M10) | **0** |
| Strategies the mask had to alter | 0 |
| Two-compound rule violations | 0 |

Compliance is 100% **by construction, not by observation**. Legality is enforced by the
action mask before the policy chooses, so an illegal action is not something the agent
learned to avoid — it is something the action space does not contain. Nothing here can
be gamed by a well-shaped reward, because legality is not in the reward at all. A
standing property test fires 100,000 random actions at the mask; this row is the other
half of the claim, that no evaluation log contains an illegal executed action either.
F24 added a second structural fence one layer down: a compound whose fitted wear is
zero never enters the action space at all.

This is the strongest result in the project and the cheapest to verify.

## The advantage is conditional on the tyre model

Slicing M1 to the three archetypes made the headline disappear before the repair, and
it still does after it. The split survived a full retrain, which makes it a property of
the evidence, not of one policy.

Group the 24 circuits by where their 2026 degradation model came from:

| Circuits | n pairs | M1 delta | Median regret | Agent stops | Oracle stops |
|---|---|---|---|---|---|
| **Repaired** — own data, soft's curve from the F24 ladder | 80 | **−0.81** | 81.6 s | 2.83 | 1.69 |
| **Synthesised** — T5 transform supplied the curve | 360 | **+3.19** | 27.3 s | 2.42 | 1.96 |
| Unusable — Miami's own thin fits | 20 | −0.10 | 604.9 s | 6.15 | 3.00 |
| Incomplete — no 2026 soft fit exists | 20 | +0.85 | 18.1 s | 1.35 | 1.10 |

**The published +2.288 is still carried by the circuits whose tyre model was
synthesised.** Where the model is anchored to the era's own running, the agent is
slightly behind the baseline.

The mechanism inverted with the repair, and that matters. The pre-repair agent
under-stopped everywhere — a 55-lap soft stint was free, and M9's 37.92 failures per
100 races were the bill. The retrained agent **over-stops**: 2.83 stops on repaired
circuits against an oracle preference of 1.69. It learned that worn tyres bite and now
pays the pit-loss premium to avoid them, further than the optimum wants. Same split,
opposite habit — which points the explanation at the transform rather than the policy:
where T5 smooths degradation, whatever habit the agent has is cheap; where wear is
anchored to data, every deviation from the optimum is priced.

Three explanations remain live and this evaluation does not separate them: the
transform may leave exploitable regularity the scripted baseline does not chase; the
rival pace models are fitted from the same data, so the field may simply be tighter
where that data exists; or four circuits is too few to rule out character effects.

**The defensible claim** is therefore narrower than the headline: SENNA beats scripted
strategies inside its own simulator by a margin that depends on the tyre model, and the
tyre model's fidelity to a real 2026 season has not been established. That is a smaller
result than +2.288 places. It is the one the evidence supports.

## What this chapter does not show

- **Any claim about a real 2026 race.** M8 failed; the simulator is not calibrated to
  reality and the write-up says so wherever a number could be mistaken for a
  prediction.
- **A per-archetype figure for M4, M5, M9 or M10.** Those payloads store bank-level
  aggregates only. Producing per-circuit versions means re-running the suite, which is
  a different experiment from the one these numbers came from.
- **Human-strategist comparison beyond M2's ten races.** Ten is what the counterfactual
  bank holds.

## Strategy robustness — does the agent read the physics, or this physics?

An agent that memorised one parameter set would make the same call whatever you did to
the world. One that learned the structure of the problem should move its stop the way a
strategist would predict when you change what a stop is worth.

Six perturbations on the three archetypes, raced on the **published test bank's own
seeds** — the same races the reported metrics came from, so a shifted stop is the
perturbation talking rather than a different draw. Each arm is a copy of the config
tree with one field changed and nothing else. 60 races per arm.

The arms are not all the same kind of experiment, and the difference decides what
movement means:

- **controlled** — the physics moves and the race is otherwise intact, so a shifted
  stop can only be the policy responding.
- **confounded** — the perturbation changes the event distribution itself. Raise the
  safety-car rate and a different safety car happens on a different lap, so the stop
  moves whether or not the policy noticed anything.
- **scenario** — the world model is untouched and the agent simply starts somewhere
  else.

| Arm | Kind | Predicted | Earlier | Later | Unchanged | Agreed |
|---|---|---|---|---|---|---|
| Tyre degradation +10% | controlled | earlier | 12 | 0 | 48 | **12 of 12** |
| Tyre degradation −10% | controlled | later | 0 | 11 | 49 | **11 of 11** |
| Pit loss +2 s | controlled | later | 2 | 3 | 55 | 3 of 5 |
| Pit loss −2 s | controlled | earlier | 2 | 4 | 54 | 2 of 6 |
| Energy coefficients +20% | controlled | none | 0 | 0 | **60** | — |
| Energy coefficients −20% | controlled | none | 0 | 0 | **60** | — |
| Safety-car rate +50% | confounded | none | 13 | 3 | 44 | — |
| Safety-car rate −50% | confounded | none | 7 | 15 | 38 | — |
| Rain probability +50% | confounded | none | 1 | 1 | 58 | — |
| Rain probability −50% | confounded | none | 1 | 6 | 53 | — |

Grid sweep, physics untouched, mean lap of the first stop: **P2 → 20.05, P8 → 19.72,
P16 → 19.65**.

Reproduce with `python -m senna.eval.robustness --seeds 20`.

### What the arms say

**Degradation: the right direction, every time it moves.** Twenty-three stop movements
across both arms, twenty-three in the predicted direction. Roughly one race in five
responds; the rest hold a stop that was already placed mid-window. The pre-repair agent
moved 16 stops at 87% agreement from a lap-3 anchor; this one moves from a lap-18
anchor and never moves the wrong way. This is the strongest evidence in the study that
the agent reads tyre state rather than replaying a plan.

**Pit loss: a weak, noisy response where there was none.** Two seconds on a stop moved
eleven races across both arms at barely-better-than-coin agreement. Pit loss is still
not in the observation — the 32 dimensions carry `pit_count_norm` and `pit_lane_open`
and nothing about what a stop costs — so any response is indirect, through the lap-time
consequences the agent can see. An agent asked to decide when a stop is worth taking
has still never been told the price; that remains the obvious next observation feature,
and it remains out of scope while the frozen triplet is what every number here is
measured on.

**Energy: cleanly decoupled, which is the answer we wanted.** No prediction was made
here — the question was whether pit timing bleeds into the energy model — and a 20%
swing in what a megajoule is worth moved no stop at all, exactly as before the repair.
The two decisions are independent in the policy as they are in the design.

**Safety cars: the confound now confounds.** A third of races move under the rate
arms, in both directions. Before the repair almost nothing moved — under free tyres a
neutralisation changed nothing worth reacting to. Now a safety car is a cheap stop the
agent actually takes, so redrawing the safety cars redraws the stops. M5 agrees from
its own angle: SC precision 0.900 at recall 0.741, where the pre-repair agent's recall
was 0.401.

**Grid position: still unused, now defensibly.** Four tenths of a lap separated P2
from P16 before the repair; now the spread is 0.4 laps around lap 20 — effectively
nothing, from inputs (`position_frac`, `places_gained_frac`) the agent can see. With
stops anchored mid-window rather than at lap 3, a grid-independent first stint is much
closer to what the oracle itself does.

### The finding underneath all of them

The pre-repair version of this section ended in an indictment: first stop at median
lap 3, 52.9-lap final stints on tyres with a 31–34-lap cliff, one opening move carried
out regardless of the world — **the policy is close to open-loop**, it said, and the
evidence said so too.

The repair changed the verdict:

| | Agent (pre-repair) | Agent (F24) | Oracle |
|---|---|---|---|
| First stop, median lap | 3 | **18** | — |
| First stop, mean lap | 5.0 | 19.7 | — |
| Stops per race (repaired circuits) | 1.18 | 2.83 | 1.69 |

The opening move is gone. Stops sit mid-window where the optimum sits, degradation
perturbations move them in the right direction every time, and safety cars are taken
as the opportunities they are. What replaced the open-loop indictment is a smaller,
ordinary criticism: the agent over-stops relative to the oracle, spending pit loss to
protect tyres it could stretch further. An agent that over-respects a hazard it was
punished by is a familiar shape of conservatism, and a cheaper defect than one that
must fail.

So the honest summary of this study is no longer "the policy is close to open-loop".
It is: **the policy responds to the physics it can observe, in the right direction,
and its remaining errors are calibration, not blindness** — too many stops where the
tyre model is real, and an advantage that still concentrates where the tyre model is
synthesised. Both are stated with their evidence above.
