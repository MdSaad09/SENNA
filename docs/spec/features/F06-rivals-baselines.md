# F06 — Rivals, baselines, oracle & throughput

Depends on: F05
Spec anchors: 5.7 gate definitions, 5.6.2, groundwork for 5.12 M3/M5, E-06, A-05, A-07

## Goal
Everything the agent will be measured against: three readable rival archetypes with a
train/test parameter split, three scripted baselines, the dynamic-programming oracle,
and the measured steps/s number that prices the whole training plan.

## Deliverables
- rivals.yaml: three archetypes as readable rule sets with published parameter distributions (pit thresholds, SC response probability, pace sigma); parameters drawn per race; a held-out evaluation band reserved (E-06)
- Baselines (A-07): engineer-heuristic strategy, replayed-real strategy, random-legal
- Oracle strategist (A-05): full-information DP over pit-lap x compound plans x greedy energy schedule on the deterministic twin; the search space documented verbatim
- Throughput benchmark per 5.6.2: steps/s across 12 workers for 100k steps, recorded in the INDEX decisions log; profile before touching budgets if below ~300/s

## Out of scope
Training (F07); the metric suite proper (F14).

## Constants & configs
- Archetype parameter distributions — stylised, published in rivals.yaml with the train/test band boundary marked

## Tests first
- Same seed and band produce identical rival draws; train and test bands never overlap
- The oracle beats or ties every baseline on a deterministic toy race
- The random-legal baseline never proposes a masked action (reuses F05 mask machinery)
- SC responses vary across archetype draws — the E-06 degeneracy test

## Done means
- All three baselines and the oracle complete a full race; rivals draw per the documented distributions
- The throughput number is measured and written down, hardware noted
- E-06 avoided: field response to a safety car is not a single memorable pattern

## Notes for the plan session
If throughput lands under ~300 steps/s, the F07 plan changes — flag it to Saad
immediately instead of proceeding.
