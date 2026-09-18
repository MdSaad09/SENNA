# F11 — Frontend shell + Circuit Explorer + Race Replay

Depends on: F04, F10
Spec anchors: 5.10.2 rows 1–2, 5.10.3 (perf budget), E-18, F-28, F-29, R-07

## Goal
The dashboard skeleton done right — views are routes, one canvas mounted at a time —
plus the first two views: the annotated 3D circuit and a 22-car replay that holds the
frame budget.

## Deliverables
- React 18 + R3F 8 shell on the 5.9.1 pins: routing where navigation unmounts the canvas (F-28); zustand + react-query wiring; the WebGL context-loss overlay (E-18); a quality toggle with bloom off by default under the GPU heuristic
- View 1 Circuit Explorer: the GLTF ribbon with corner, braking-zone and X-mode annotations; stylised-elevation and inferred-sections caveats in the legend
- View 2 Race Replay: one InstancedMesh for 22 cars with per-instance colour; generic team-colour liveries and three-letter codes only (F-29); at most 4 Drei Html labels (selected car plus podium); mid-lap positions spline-interpolated and labelled illustrative; LOD beyond 500 m
- The dev overlay tracing every displayed number to its API response id — the frontend row of the interpretability contract

## Out of scope
Views 3–6 (F12, F13); demo polish (F15).

## Constants & configs
- The perf budget numbers (<= 150 draw calls, <= 4 Html labels, 60 fps target / 45 floor) — sourced 5.10.3 — asserted in code where measurable

## Tests first
- Route-mount test: exactly one canvas exists at any moment across navigation (F-28)
- Label cap: replay never renders more than 4 Html labels regardless of selection state
- Asset check: no sponsor marks, no team names beyond colour and three-letter codes (F-29)

## Done means
- Both views render every circuit in the library; a Chrome trace of a full 70-lap replay holds the 45 fps floor on the reference GPU
- The unofficial-project footer is present (R-07)
- Every stylised element is labelled in the UI

## Notes for the plan session
Note before planning — the React 18 / R3F 8 pairing and the
one-canvas rule are the two traps that cost weeks when missed.
