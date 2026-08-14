# F23 — Dashboard restructure and visual language

Depends on: F11, F12, F13
Spec anchors: 5.10.2 (all six rows), 5.10.3, 5.13, F-28, F-29, R-07, R-08, E-18, A-03

## Goal
The dashboard currently looks like six unstyled routes behind stock Tailwind greys. After
F23 it reads as one instrument: three tabs, a design language held in tokens rather than
sprinkled utility classes, and a Strategy page that finally answers "what did the agent
actually do" in one screen. The six spec views survive intact as sections — this changes
the shell and the skin, not the science.

Saad supplied three reference screenshots (`docs/reference_images/`, 11 Aug 2026) as a
hard visual baseline: match or beat, never fall short. They are an aesthetic reference
only. Their content model is wrong for this project in four ways and the plan session must
not copy them — see "Where the reference is wrong" below.

## Deliverables
- Design tokens in `frontend/tailwind.config.js` — surface ramp, mint accent, mono type scale, hairline borders, compound colours — every token carrying its provenance comment
- `frontend/src/index.css` base layer: page ground, tabular numerals on all figures, focus ring, scrollbar
- `frontend/src/components/ui/` primitives: Panel, PanelHeader (accent tick), MicroLabel, Stat, Meter, Segmented, StatusChip, DataTable — the whole reskin flows from these
- Shell rebuild in `App.tsx`: three-tab top nav, live status strip (model version, circuit, weather profile, grid slot), R-07 footer unchanged on every tab
- `routes.tsx` nested under the three tabs, with permanent redirects from the six existing paths so F15's demo deep links and every doc URL keep working
- New Strategy page: the existing RunPicker restyled into the left configuration rail, plus a stint timeline and pit-stop table read from the completed run
- Circuit page: canvas full-bleed and camera reframed so the ribbon fills the viewport — Saad's explicit note is that the reference renders the model too small
- Circuit right rail rebuilt on data that exists: corner count, braking zones, X-mode share, elevation range, per-circuit H_max, coverage flags
- Analysis page: reward decomposition driven by `AgentState.reward_terms` (three terms, whatever the payload names them), plus an alternatives panel built from the decision card's `probs` and `flip`

## Where the reference is wrong
Copying any of these is a defect, not a design choice.
- **DRS.** Shot 1's parameter card reads "DRS 1 zones" and shot 2's legend carries a DRS line. There is no DRS in 2026. The feature is Manual Override, and the circuit annotation is X-mode sections (5.10.2 row 1). A grep test in this feature makes the regression impossible.
- **A 20-car grid.** Shot 1's starting-position slider runs P1–P20. The grid is 22, and `SimulationCreate.grid_position` is already bounded `ge=1, le=22`.
- **A six-term reward.** Shot 3 decomposes reward into Tire Degradation Management, Time Loss Minimisation, Fuel Load Optimisation, Track Position Value, Weather Adaptation and an Overtaking Opportunity Index. The reward has exactly three terms. The mockup's own footer admits the panel is a placeholder. The real three, summed over the run, are a better panel and an honest one.
- **A planner.** Shot 1 offers an "Optimal Strategy" scored 89.0/100 before anything runs, and shot 3 ranks beam-search candidates. SENNA has no planner, no beam search and no strategy score; the agent decides lap by lap. Saad's decision (14 Aug 2026): the Strategy page is post-hoc — run it, then show what it did, headlined by the real finish position and points.

Two further reference panels are dropped for want of an endpoint, not for want of honesty: the lap-record card (no served lap record) and the invented track-characteristic scores (downforce 95, braking 88…). The replacements above come from F04 artifacts already in `CircuitDetail`.

## Tab mapping
Saad's decision, 14 Aug 2026: three tabs with a second-level rail where a tab holds more
than one section. Flattening further is not available — 5.10.3 allows one mounted canvas,
and a scrolling page would co-mount two mid-scroll.

| Tab | Sections | Spec view |
|---|---|---|
| 01 · STRATEGY | setup · replay · live | 5.10.2 rows 2, 5 + the new page |
| 02 · CIRCUIT | — | row 1 |
| 03 · ANALYSIS | energy · tyres · decisions · counterfactual | rows 3, 4, 6 |

Each section keeps the honesty statement 5.10.2 assigns it. A section that loses its
statement in the restyle is a failed review, not a tidy-up.

## Constants & configs
All of these are frontend-owned and live in `frontend/src/config/constants.ts` or
`tailwind.config.js` under the F11 divergence-6 arrangement (the browser cannot read yaml).
- Surface ramp, accent mint, text ramp, hairline border — stylised; one palette, no source, chosen to match the reference
- Compound colours soft / medium / hard / intermediate / wet — stylised; the conventional visual ranking with invented hues. Flag for the auditor: no supplier is named anywhere, which is the F-29 line these must clear
- Type scale and panel metrics — stylised
- Circuit camera reframe (replaces `CAMERA.position`) — stylised, and the new value must state the ribbon-fill fraction it was chosen for
- Nothing here is fitted or sourced. If the plan session finds itself writing a number that governs behaviour rather than appearance, it is in the wrong file.

## Tests first
- Every one of the six existing paths redirects to its new nested path — F15's demo deep links must not break
- The one-canvas invariant holds across the new nested routes: `routeMount.test.tsx` extended to walk tabs and sections, not just six flat paths
- The reward panel renders exactly the terms present in `reward_terms` and invents no label for a term the payload lacks
- No occurrence of "DRS" in `frontend/src` — a sibling to the `liveries.f29` walk
- The grid control offers 22 slots and refuses 23
- The stint timeline derived from frames agrees with the pit laps in the same run's energy ledger — an off-by-one here would be invisible by eye
- Every new colour token carries a provenance comment (extend `constants.test.ts`)

## Done means
- The three tabs read at the reference's density or better, side by side in `docs/` as evidence
- The circuit ribbon fills materially more of the viewport than the reference does, with the fill fraction stated
- 5.10.3 holds unchanged: 150 draw calls, 4 Html labels, the 45 fps floor
- The dev overlay still traces every figure on every tab to an API response id — the reskin adds no number the API did not send
- The F-29 and no-DRS walks pass, and the R-07 footer is on all three tabs

## Notes for the plan session
Build the tokens and the eight primitives first and restyle one section end to end before
touching the rest; if the language is wrong, it is wrong once rather than seven times.
The shell and the routing change are the risky half. Two files outside the app hardcode
the old paths and will pass their own tests while the demo breaks: `scripts/warm_demo.sh`
prints `/live?...` and `/counterfactual?...` as the deep links the video opens on, and
`frontend/e2e/demo.spec.ts` navigates `/live?circuit=...`. Redirects keep both alive; the
plan should decide whether to also update them to the new paths, which is tidier and is a
second chance to get the redirect test wrong. The Strategy page is the only
genuinely new surface and it depends on nothing new server-side: stints come from
`cars[EGO_CAR_ID].compound` across frames, pit laps from the energy ledger's `pit` field,
the headline from the run summary.
