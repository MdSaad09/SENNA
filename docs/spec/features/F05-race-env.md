# F05 — F1RaceEnv: observation, masks, dynamics, reward

Depends on: F02, F03
Spec anchors: 5.5 — the entire section is this feature's contract — plus E-01, E-03 to E-08, F-15 to F-20, A-01, A-10

## Goal
The Gymnasium environment: 22 cars, one decision per lap, MultiDiscrete([6, 4]) with
action masking, physics clipping inside the dynamics, the 3-term reward, and an era
switch — 100% regulatory legality by construction.

## Deliverables
- F1RaceEnv per 5.5: the 32-dimension observation exactly as the 5.5.1 table (names, ranges, encodings); per-head mask functions with logged reason codes (5.5.2), including the two-compound rule (F-20)
- Transition dynamics per 5.5.3: the joint lap-time model; harvest/deploy/derate with SOC hard-clipped to [0, 4] MJ; FIFO pit lane with per-car service draws (E-05); green/VSC/SC/red state machine with the red-flag free tyre change (E-04); sub-lap wetness over three sectors (E-08); backmarker traffic (E-07)
- Reward per 5.5.4 exactly: pace shaping w_p = 0.02 with per-circuit s_ref; potential-based position shaping Phi(s) = -0.1 x position; terminal 2026 points / 2.5; DNF pays 0; per-lap decomposition logged
- Termination and info per 5.5.5; reset(seed) fully seeds every stochastic stream; the era switch reads physics_2024 / physics_2026 yaml (A-10)

## Out of scope
Rival archetypes beyond a placeholder equal-pace field (F06); training (F07).

## Constants & configs
- Everything from physics_params.yaml and physics_2026.yaml; derate penalty p_der, dirty-air threshold, attack SOC floor — each sourced or fitted, none inline

## Tests first
- Property: 100k random action sequences — no illegal action ever executes, SOC never leaves [0, 4], energy conserved to 1e-9 MJ (E-01)
- Mask unit tests per rule, including stay-out masked on the last feasible dry pit lap when second_compound_used == 0 (F-20)
- 22 simultaneous pit stops resolve by FIFO cumulative time, never in-place position swaps (E-05)
- VSC and SC produce different pit-loss multipliers (E-03); red flag grants a compound choice to all cars (E-04)
- Reward telescoping: an oscillating position sequence nets exactly zero shaping (F-15)
- Same seed produces an identical episode (SubprocVecEnv statelessness, 5.5.5)

## Done means
- The full 5.5 contract implemented; every test above green; a 70-lap 22-car race runs to completion
- Mask reasons and the reward decomposition appear in info every step
- No pandas import reachable from step()

## Notes for the plan session
This is the heart of SENNA. Plan it as sub-slices — observation, masks, dynamics,
events, reward — each with its tests, and expect the plan itself to be long. That is
correct, not scope creep.
