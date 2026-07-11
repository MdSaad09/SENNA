# F04 — Circuit ribbon pipeline

Depends on: F01
Spec anchors: 5.10.1, E-13, E-17, F-08, F-12

## Goal
A GLTF track ribbon per circuit with validated geometry — fastest-clean-lap centreline,
rotation-minimising frames, zero self-intersection anywhere — the 3D foundation every
frontend view stands on.

## Deliverables
- senna/circuits/: pos_data -> metres -> 2 m arc-length resample -> Savitzky-Golay smoothing (Z harder) -> closed loop -> rotation-minimising frames -> 12 m ribbon with half-width clamped to local curve radius
- Stylised elevation (smoothed Z x1.5) with a flat-plus-camber fallback where Z is missing; both flagged stylised in the metadata (F-12)
- Corner annotations from get_circuit_info(); braking zones from speed-drop detection (drop above 50 km/h within 100 m); X-mode sections as the longest full-throttle stretches, stylised until official section data exists
- GLTF + metadata JSON export per circuit; circuits.yaml generated from ingested data, never hand-listed (F-08, E-13)

## Out of scope
Rendering (F11). Energy-zone values (F03 owns H_max).

## Constants & configs
- Resample spacing 2 m, ribbon width 12 m, elevation x1.5 — all stylised, in configs/circuits.yaml
- Lap-length tolerance 5% — sourced, spec 5.10.1 item 7

## Tests first
- Property: no ribbon self-intersects, asserted across every ingested circuit (E-17)
- Frames: no twist flip across a synthetic hairpin (parallel-transport check)
- Lap length within 5% of the official figure, per circuit
- Loop closure: first and last centreline points coincide after resampling

## Done means
- One GLTF + JSON per circuit with data; Madrid absent until its first session is ingested
- All geometry tests green across the whole library
- Every stylised choice labelled in metadata the UI can surface

## Notes for the plan session
Monaco and Hungary are the stress cases — write the self-intersection test before the
extruder exists. Z is noisy and sometimes absent: elevation is decoration, never data.
