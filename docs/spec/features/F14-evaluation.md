# F14 — Evaluation suite & counterfactual studies

Depends on: F08, F09
Spec anchors: 5.12 (every metric with its gaming note), E-03, E-14, F-24, A-05 to A-08, OQ-9

## Goal
The honest core of Chapter 7: M1–M11 computed with paired seeds and bootstrap
confidence intervals, ten era-matched counterfactual races, the sim-to-real numbers,
and a make target that regenerates the whole headline table.

## Deliverables
- Metric implementations M1–M11 exactly per 5.12 — each with its definition, its denominator, and its written "how this metric lies" note carried into the report
- Paired-seed harness (identical event draws, agent vs baseline) with bootstrap CIs (A-06); evaluation restricted to the held-out rival band and test seeds
- Era-matched counterfactuals: a Stage-C fine-tune on the 2024 constants file, the ten spec races replayed, agent strategy vs the team's actual strategy in the same simulator (F-24, OQ-9 default)
- The luck-share variance decomposition (M11 / A-08) and the oracle-regret distribution (M3 / A-05)
- make report: regenerates the Chapter 7 tables and figures from stored runs, deterministically

## Out of scope
Dissertation prose; demo assets (F15).

## Constants & configs
- The 5.12 metric targets — sourced — configs/eval.yaml, each carrying its gaming note as a comment

## Tests first
- The M1 harness reproduces known deltas and CI coverage on hand-built races
- M5 precision and recall computed per neutralisation window, VSC and SC separated (E-03)
- Split guards: any metric that touches 2026 rounds 1–6 as "validation" fails loudly (E-14)

## Done means
- Every M1–M11 number exists with a CI; targets met, or the miss documented with cause
- make report is deterministic given the run store
- The counterfactual numbers are final, era-matched, assumptions stated

## Notes for the plan session
The 2024 fine-tune costs roughly 2–3 days of compute (OQ-9) — schedule it first inside
this feature so the analysis code develops while it runs.
