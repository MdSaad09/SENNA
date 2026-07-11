# F08 — Ablations & headline runs

Depends on: F07
Spec anchors: 5.6.3, F-16, F-18, F-22, R-06

## Goal
The evidence base: four targeted ablations at 4M steps x 2 seeds each, and the 3-seed
headline run, with model selection performed on validation seeds only.

## Deliverables
- Ablation harness plus configs for: (1) no curriculum — Stage C from scratch; (2) penalty-based constraints instead of masks — the direct F-16 test, counting violations during learning; (3) v2's 12-term reward vs the 3-term reward — the likely publishable negative result; (4) terminal-only reward, both shaping terms off. Optional (5) A2C at matched budget if compute allows. DQN excluded, with the MultiDiscrete reason documented (F-18, R-06)
- Headline: 3 seeds, checkpoint selection on validation seeds, reporting reserved for held-out test seeds and the held-out rival band
- Run manifest: every run row carries seed, config hash, budget and W&B id

## Out of scope
The full metric suite (F14) — this feature produces models and curves, not the headline table.

## Constants & configs
- Ablation budgets (4M x 2 seeds) — sourced 5.6.3 — configs/ablations.yaml

## Tests first
- The penalty-ablation env variant actually permits and counts violations — otherwise ablation 2 measures nothing
- The 12-term reward reimplementation matches v2's published formulas against fixtures
- Selection code can never read test seeds (guard test)

## Done means
- All four ablations plus the headline complete within ceilings; curves in W&B
- A one-paragraph written readout per ablation, feeding the dissertation
- The chosen headline checkpoint is recorded as the model version F09 and F10 consume

## Notes for the plan session
Mostly compute babysitting — plan for resumable runs and cheap dry-run configs so the
harness is proven before real hours burn.
