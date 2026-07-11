# F13 — Live Simulation view + Counterfactual view

Depends on: F11
Spec anchors: 5.10.2 rows 5–6, E-15, E-16, E-18, F-24, A-03

## Goal
The two persuasion views: the agent racing live — explicitly in-simulator — with
decision cards streaming in, and the split-screen era-matched counterfactual.

## Deliverables
- View 5 Live Simulation: WS client with speed control (1x/5x/10x/30x), pause and scrub replaying from stored frames (E-16), a per-lap decision-card panel carrying the fidelity badge, reconnect logic, and the context-loss overlay (E-18)
- View 6 Counterfactual: split viewport, synced lap clocks, divergence flash at the pit lap, position-delta chart; the header states the era config and "in-simulator comparison under stated assumptions" (F-24)
- Deep-link support: seed and circuit in the query string (feeds the F15 demo)

## Out of scope
Recruiter-script polish; mobile 3D and broadcast cameras stay cut (R-08).

## Constants & configs
- Playback speeds — sourced 5.9.3; divergence-flash styling — stylised

## Tests first
- Scrubbing back mid-stream shows frames identical to the original stream — single source of truth (E-16)
- The card panel shows nothing when a run's model_version has no stored explanations — never explain a ghost (E-15)
- The split view keeps both lap clocks synced across speed changes

## Done means
- A cold deep link opens mid-race with cars moving and cards arriving — the 5.13 opening beat
- The counterfactual view runs an era-matched pair end to end with the honesty header
- The perf budget holds with the split viewport

## Notes for the plan session
The demo lives or dies on reconnect and scrub — build those before any visual flourish.
