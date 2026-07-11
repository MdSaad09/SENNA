# F07 — Training: MaskablePPO + curriculum

Depends on: F05, F06
Spec anchors: 5.6.1, 5.6.2, 5.7 (gates), F-21, F-23, R-12

## Goal
The agent, trained honestly: MaskablePPO with the 5.6.1 hyperparameters, three
curriculum stages that advance on competence gates evaluated on frozen seed sets, and
checkpoints that ship as complete triplets.

## Deliverables
- Training script: MaskablePPO (sb3-contrib), MLP pi=[256,256] vf=[256,256], 12 SubprocVecEnv workers, VecNormalize(obs=True, reward=False), W&B logging, budget ceilings A 1.5M / B 2.5M / C 4M (R-12 — ceilings, never schedules)
- Competence gates per 5.7: Stage A exits on plateau AND mean race time within 1.5% of the scripted solo reference; Stage B on >= 55% finish-ahead over 200 paired seeds vs the rule-based baseline; Stage C stops on 1M-step stagnation with validation-seed checkpoint selection. All gate values logged to curriculum_gates.json (F-21)
- Checkpoint discipline: weights + vecnormalize.pkl saved together, hash recorded in the model version (F-23); statistics carried across stages as a documented choice
- Frozen seed sets committed; the terminal-vs-shaping dominance ratio logged per run (5.5.4)

## Out of scope
Ablations and the multi-seed headline (F08); serving (F10).

## Constants & configs
- Every hyperparameter in configs/training.yaml with the 5.6.1 reasoning carried as comments; gates in configs/curriculum.yaml

## Tests first
- The gate evaluator: hand-built eval histories trigger and hold transitions exactly per 5.7
- Checkpoint round-trip: save, load with training=False, same observation gives the same action (the F-23 integration test)
- Smoke train: 5k steps on Stage A runs end to end and logs every expected series

## Done means
- Stage A trains to its gate within budget; gates logged; every checkpoint is a triplet
- A W&B run is reproducible from seeds.yaml plus the config hash
- No stage ever advances on step count alone (F-21)

## Notes for the plan session
Training runs on Saad's compute, never in serving (F-26). Confirm the real OQ-2 hardware
in INDEX before promising wall-clock times.
