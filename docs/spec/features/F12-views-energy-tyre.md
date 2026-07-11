# F12 — Energy view + Tyre Surface view

Depends on: F11
Spec anchors: 5.10.2 rows 3–4, F-02, F-13, T5

## Goal
The two physics views: the corrected energy story — SOC trajectory against the
per-circuit harvest cap, no fictional deploy plane — and the fitted tyre surface with
its cliff visible.

## Deliverables
- View 3 Energy: SOC ribbon over laps plus paired harvest/deploy bars against the per-circuit H_max line, fed by GET /energy/{run_id}; footer states "modelled, calibrated to 2026 aggregate behaviour" (F-13)
- View 4 Tyre Surface: grip over age x temperature as a vertex-shader surface from GET /tyres/{circuit_id}, cliff visible; the transfer-cluster flag shown for compounds without 2026 fits (T5)

## Out of scope
Live streaming and counterfactuals (F13).

## Constants & configs
- Nothing new — both views render fitted or config data; any axis or colour choice is stylised and noted

## Tests first
- The energy view renders a fixture run where per-lap deploy exceeds 4 MJ without any cap marker appearing — the F-02 regression trap
- The tyre surface renders the fitted model's output, not raw laps (data-source assertion)
- Both views respect the one-canvas rule when navigated to and from

## Done means
- Both views live against real simulation runs; footers and flags present
- Axes read in MJ with SOC bounded [0, 4] everywhere
- The perf budget still holds with either view mounted

## Notes for the plan session
This is the view a motorsport engineer probes first (5.13, the 75–90 s beat). The
correctness of the energy picture matters more than its beauty.
