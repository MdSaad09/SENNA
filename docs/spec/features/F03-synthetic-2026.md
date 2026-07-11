# F03 — Synthetic 2026 generator (T1–T8)

Depends on: F02
Spec anchors: 5.4 (all eight transformations + the 5.4.1 targets), E-02, E-13, E-14, the F-01 to F-06 corrections, AR-01 to AR-08, AR-17, AR-18

## Goal
2026-era race dynamics for every circuit — including ones the season has not visited —
built by transforming fitted 2024 behaviour with sourced physics deltas, calibrated on
real 2026 rounds 1–6, validated on rounds 7+ (A-02, the credibility upgrade).

## Deliverables
- T1 powertrain reprofile: point-mass longitudinal model with the 350 kW taper, producing per-circuit full-throttle time, terminal speeds and the deployable-energy integral E_dep
- T2 aero scaling: drag x0.45 in X-mode sections; corner-speed exponent fitted, not assumed
- T3 mass shift via fitted k_m; T4 energy accounting: H_max from config, lift-and-coast cost c_lc, clipping term
- T5 tyre transfer clusters; T6 fuel/energy budget (blocks on AR-10 verification); T7 overtaking model refit on 2026 rounds 1–6; T8 residual recalibration c_circuit
- transforms.yaml provenance file; per-event H_max values in circuits.yaml with source note and date (E-02)
- The 5.4.1 validation suite: lap-time KS < 0.15 per held-out circuit, stint-length EMD, pit loss within 1.0 s, event-rate bands, derate plausibility — figures for Chapter 6

## Out of scope
The env consuming these numbers (F05); rival behaviour (F06).

## Constants & configs
- Sourced deltas read from physics_2026.yaml (AR-01 to AR-09); every T-output written back with fitted provenance

## Tests first
- T1 on a synthetic flat-out circuit reproduces the closed-form taper integral
- Calibration code refuses rounds 7+ as input (split guard, E-14)
- T8 never reads held-out rounds (leakage test)

## Done means
- Every 5.4.1 target computed and reported per held-out circuit — met, or the miss documented with cause
- No transformation reads a hard-coded physics literal; configs only
- The Chapter 6 figures regenerate from a make target

## Notes for the plan session
AR-10 (fuel ~70 kg, grade C) must be surfaced to Saad before T6 output is trusted.
Madrid has no data until September — the circuit library simply does not list it yet
(E-13); no special-casing.
