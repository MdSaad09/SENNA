# F02 — Physics model fits

Depends on: F01
Spec anchors: 5.4 groundwork for T5/T6, 5.5.3 constants, E-09, E-10, F-06, F-13, AR-10, AR-16

## Goal
Every fitted constant the simulator needs, produced from clean data, each with a
residual plot, all written to configs/physics_params.yaml — the interpretability
contract for the physics layer, satisfied.

## Deliverables
- Joint per-race regression: lap_time ~ tyre(age, compound) + a*fuel_mass + b*lap_number with compound fixed effects (E-10 — never fit fuel and track evolution separately); collinearity reported
- Tyre degradation grip(age) = 1 - a*age^b per compound per circuit, in/out and inaccurate laps excluded (E-09); 2026 rounds 1–6 where available, cluster transfer elsewhere with low-confidence flags (T5 groundwork)
- Event hazards per circuit (SC, VSC, red) with binomial bands; pit-loss mean and sigma per circuit from OpenF1 (feeds the E-05 FIFO model)
- Braking-energy and full-throttle integrals from telemetry, cadence-aware at 4–5 Hz (AR-16), for T1/T4
- One calibration notebook per fitted module with residual plots; physics_params.yaml populated with `fitted: <notebook>` provenance

## Out of scope
The eight T-transformations themselves (F03); anything the env consumes beyond the yaml.

## Constants & configs
- All outputs land in physics_params.yaml as fitted, notebook named; AR-10 fuel mass stays grade C until Saad verifies it

## Tests first
- The joint fit recovers known coefficients from a synthetic race with injected a and b
- The degradation fitter refuses datasets containing in/out laps (guard test)
- The fitting entrypoint raises if a season's quality report is missing (F-14 gate)

## Done means
- physics_params.yaml has no nulls among the constants F05 lists, each with provenance
- Residual plots exist per module; collinearity numbers reported
- Grade C rows are still marked C — nothing silently promoted

## Notes for the plan session
Half notebooks, half library code. Keep fitting logic importable (senna/physics/fits/)
and the notebooks thin, so tests hit the real code.
