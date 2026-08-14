# F23 plan — Dashboard restructure and visual language

Approved by Saad, 14 August 2026. Both open questions answered: the Strategy headline is
position only, and this stays one feature with a declared cut line.
Spec: `docs/spec/features/F23-ui-revamp.md`.

> F23 extends master spec v3.0 rather than implementing a row of it. Its spec anchors are
> contracts it must not break, not rows it delivers. The visual baseline is three
> screenshots Saad supplied on 11 August (`docs/reference_images/`) — match or beat, never
> fall short. They are an aesthetic reference only; four things in them are wrong for this
> project and are recorded as defects in the feature spec.

## Objective & spec anchors

The dashboard is six unstyled routes behind stock Tailwind greys: 19 distinct colour
utilities over ~174 call sites, all on the `neutral` ramp, plus a second and larger colour
surface of inline chart hexes that no token system currently owns. F23 turns it into one
instrument — three tabs, a palette held in tokens, and a Strategy page that answers what
the agent actually did. The six spec views survive as sections. This changes the shell and
the skin, not the science.

- **5.10.2** — the six views and, critically, the honesty statement each one owns. The
  restyle's main risk is losing one silently, and nothing currently fails if that happens.
- **5.10.3 / F-28** — one canvas mounted at a time. This is why the tabs carry a sub-rail
  rather than a scrolling page: a scroll layout would co-mount two canvases mid-scroll.
- **5.13** — the recruiter beats and the one-click nav path between them. See the conflict
  below.
- **R-07** the unofficial-project footer, **F-29** generic liveries, **E-15 / E-16 / E-18**
  the three edge cases the views already handle, **A-03** the decision-card contract.

### The one master-spec conflict, and its resolution

5.13 specifies "One click: Counterfactual in the nav" at 0:45 and "One click: Energy in the
nav" at 1:15. `docs/demo/script.md:27` explains the demo URL's query string is a union of
every view's params precisely so nav clicks land configured, and `App.test.tsx:39` already
pins that behaviour. Under three tabs, Live sits in STRATEGY and both targets sit in
ANALYSIS, so each of those beats becomes two clicks.

The master spec wins, so F23 preserves the property rather than the mechanism: contextual
one-click jumps carrying the current query — a "compare with the real race" link on the
decision card, and an energy link from the counterfactual. `docs/demo/script.md` is updated
to name the new click. Recorded as a divergence resolution, not a quiet drop.

## Deliverables

### Design language
- `frontend/src/config/palette.ts` — single source for every colour, UI and chart alike,
  each carrying its provenance comment. Deliberately wider than a reskin: chart and scene
  hexes currently live as inline literals across `SocPanel`, `EnergyBarsPanel`,
  `CircuitRibbon`, `DecisionCardPanel`, `DeltaChartPanel` and `constants.ts`, and
  `SocBar.tsx:6` imports `SOC_TINT` from another view's file to keep two blues in step.
  One palette or none.
- `frontend/tailwind.config.js` — the same literals under a `senna` namespace, guarded by a
  drift test. Importing `palette.ts` into the config directly needs `allowJs` gymnastics
  across the Tailwind/Vite/TS boundary; a test that pins equality is this repo's idiom.
- `frontend/src/index.css` — base layer: ground, `tabular-nums` on figures, focus ring,
  scrollbar.

### Primitives — `frontend/src/components/ui/`
`Panel`, `PanelHeader` (accent tick), `ViewHeader`, `MicroLabel`, `Stat`, `Meter`,
`Segmented`, `StatusChip`, `DataTable`, `RunStatusOverlay`, `HonestyNote`.

Three are pure de-duplication of what already exists: the header-bar classString is
copy-pasted across five sites (`RaceReplayView.tsx:60`, `EnergyView.tsx:29`,
`LiveSimulationView.tsx:165`, `CounterfactualView.tsx:206` and `:234`, with
`TyreSurfaceView.tsx:60` a near-variant), the panel card across four (`Legend.tsx:31`,
`FitPanel.tsx:26`, `SocPanel.tsx:35`, `EnergyBarsPanel.tsx:35`), and the centred status
overlay across eight. `HonestyNote` exists so a statement has one obvious home and cannot
be restyled away by accident.

### Shell & routing
- `App.tsx` — wordmark and strapline, live status strip, three tabs, sub-rail, R-07 footer
  unchanged and verbatim.
- `routes.tsx` — nested paths plus a redirect for each of the six legacy paths.
- The five files that hardcode `/live?...` are updated as well as redirected:
  `README.md:15`, `docs/demo/script.md:25`, `scripts/warm_demo.sh:47-48`,
  `frontend/e2e/demo.spec.ts:16`. Redirects keep them working; a stale URL in the README is
  still a bad look.
- `lib/queryParams.ts` — `runIdFromLocation` is duplicated byte-identically in
  `RaceReplayView.tsx:20-25` and `EnergyView.tsx:14-19`, and reimplemented in
  `LiveSimulationView.tsx:26-39` and `CounterfactualView.tsx:28-41`.

### Tab mapping

| Tab | Sections | Spec view |
|---|---|---|
| 01 · STRATEGY | setup · replay · live | 5.10.2 rows 2, 5 + the new page |
| 02 · CIRCUIT | — | row 1 |
| 03 · ANALYSIS | energy · tyres · decisions · counterfactual | rows 3, 4, 6 |

### Pages
- New `views/strategy/` — `StrategyView`, `stints.ts`, `StintTimeline`, `PitSchedule`.
  Stints derive from `cars[EGO_CAR_ID].compound` across frames; `CarState.compound` is a
  string from `COMPOUNDS = ("SOFT","MEDIUM","HARD","INTERMEDIATE","WET")`
  (`senna/env/scenario.py:21`, served at `senna/serve/frames.py:61`). Pit laps cross-check
  against the energy ledger's `pit` field. Frames are paginated, so the page uses the
  existing `fetchAllFrames` loop rather than page one.
- `CircuitExplorerView` — canvas full-bleed, ribbon framed to fill the viewport, new
  `TrackCharacteristics` rail from the `meta.json` fields.
- New `views/analysis/RewardPanel` and `AlternativesPanel`.

### The Strategy headline — Saad's decision, 14 August 2026
**Position only.** "P5 → P2", grid read from `SimulationResult.config.grid_position`, finish
from `summary.final_position`, alongside the real `race_time_s`. No points anywhere on the
page.

The reason this needed deciding: `summary.points` is real but RL-scaled. `terminal_points`
(`senna/env/reward.py:41-47`) divides the FIA table by `points_divisor: 2.5`
(`configs/env.yaml:22-23`), so a P2 finish serves as `7.2`, not `18`. Quoting it verbatim
reads as wrong to anyone who knows the sport; deriving the FIA figure client-side would put
a computed number on screen in a codebase whose rule is that numbers come from the API.
Position sidesteps both and is the thing a strategy page is actually about.

## Constants & configs

All stylised, all frontend-owned under the F11 divergence-6 arrangement (the browser cannot
read yaml). The palette is **sampled from the reference screenshots**, not invented — the
PNGs were decoded and their dominant colours counted.

| Token | Value | Evidence |
|---|---|---|
| `ground` | `#0b1014` | 41.3% of shot 3 |
| `surface` | `#121a1f` | 85.1% of shot 1 |
| `raised` | `#1a242b` | 62.0% of shot 2 |
| `line` | `#26333c` | the hairline, all three shots |
| `text` | `#e6edf1` | |
| `muted` | `#c9d0d7` | |
| `faint` | `#637481` | |
| `ghost` | `#515c63` | |
| `accent` | `#6bd6c3` | the mint |
| compound soft | `#b13f4d` | sampled from the stint bar |
| compound medium | `#b29337` | sampled from the stint bar |
| compound hard | `#c9d0d7` | sampled from the stint bar |
| compound intermediate | `#3f9e58` | chosen to match, not sampled |
| compound wet | `#3b74c4` | chosen to match, not sampled |

Compound colours carry an F-29 note for the auditor: the soft/medium/hard ranking reads by
convention as red/amber/white, the hues here are invented rather than lifted, and no
supplier is named anywhere in the codebase.

Also stylised: the type scale and panel metrics; and `RIBBON_VIEWPORT_FILL = 0.82`,
replacing the fixed `CAMERA.position = [0, 900, 900]`. Saad's note is that the reference
renders the circuit model too small. The fix is to fit the camera to the loaded GLB's
bounds rather than pick a new fixed distance — circuits run 3–7 km, so one hardcoded
distance can only be correct for one of them. This beats the reference rather than matching
it.

No sourced or fitted numbers. Nothing in this feature governs behaviour.

## Tests first

- `routeMount.test.tsx` — the hop table extended across all eight nested paths; the existing
  `MutationObserver` peak check still proves no transient double-mount (F-28).
- `routeMount.test.tsx` — each of the six legacy paths redirects to its canonical section
  **and the query survives**.
- `App.test.tsx` — the three tabs carry the current query, replacing the six-href test at
  `:39-46`; the footer disclaimer stays verbatim.
- **`honesty.test.tsx` (new)** — every section still renders its 5.10.2 statement. The
  strings to pin: "modelled, calibrated to 2026 aggregate behaviour" (`EnergyView.tsx:74`),
  "in-simulator comparison under stated assumptions" (`CounterfactualView.tsx:213`), "live
  simulation — the trained agent racing in the simulator, not live timing"
  (`LiveSimulationView.tsx:166`), `ILLUSTRATIVE_MOTION_CAPTION`
  (`TransportControls.tsx:96-98`), the tyre temperature-axis disclaimer
  (`TyreSurfaceView.tsx:139-142`), and the Legend's five caveats (`Legend.tsx:21-52`). This
  is the feature's most valuable test: today a restyle can drop any of them and nothing
  fails.
- `noDrs.test.ts` (new) — `\bDRS\b` absent from shipped `frontend/src` and `index.html`.
  Clones the `liveries.f29.test.ts` fs-walk and its `shipsToTheBrowser` filter. Passes on
  day one; it is a pure regression guard against the reference's two DRS mentions.
- `provenance.test.ts` (new) — walks `config/*.ts` and requires every `export const` to
  carry a `sourced | fitted | stylised | operational` tag. **The feature spec said "extend
  `constants.test.ts`" and that was wrong**: that file pins values only, and no provenance
  walk exists anywhere. This is new machinery modelled on the F-29 walk, and it
  retroactively enforces a convention that has been hand-followed until now.
- `palette.tailwind.test.ts` (new) — `tailwind.config.js` and `palette.ts` agree.
- **`stints.test.ts` — property test**: for any frame sequence, derived stints partition
  laps 1..N with no gap or overlap, and every boundary coincides with an `in_pit` lap.
- `stints.test.ts` — cross-check: boundaries derived from frames equal the non-zero `pit`
  laps in the same run's energy ledger. An off-by-one here is invisible by eye.
- `RewardPanel.test.tsx` — renders exactly the keys present in `reward_terms`, excludes the
  derived `total` from the term list, and invents no label for an absent key. The served
  keys are `pace`, `position`, `terminal` plus `total`
  (`senna/env/race_env.py:357-363`) — three terms as the spec requires.
- `StrategyView.test.tsx` — the pit table's column set, pinned. Guards against anyone
  re-adding the fabricated service-time column.
- The grid control offers 22 slots and rejects 23.

## Edge cases handled

- **E-18** — the context-loss overlay stays mounted per canvas section through the shell
  rebuild.
- **E-16** — playback clock, scrub and reconnect untouched; no view internals change.
- **E-15** — the new decisions section shows the same "no stored explanations for model
  version X" message rather than explaining a ghost.
- **Six circuits have no `meta.json`.** `abu_dhabi_grand_prix`, `azerbaijan_grand_prix`,
  `dutch_grand_prix`, `french_grand_prix`, `japanese_grand_prix` and `qatar_grand_prix` are
  listed in `configs/circuits.yaml` but serve `corners: null`, `braking_zones: null`,
  `xmode_sections: null`, `lap_length_m: null`. The characteristics rail states the coverage
  gap and must never render a zero as if it were a measurement.
- **DNF** — `summary.dnf` is real; the headline says DNF rather than a finishing position.
- **A run still queued or running** — status, not an empty stint bar.

## Acceptance checklist

- [ ] Three tabs at the reference's density or better, screenshots committed as evidence
- [ ] The ribbon fills materially more of the viewport than the reference, fill fraction
      stated on the view
- [ ] 5.10.3 holds unchanged: 150 draw calls, 4 Html labels, the 45 fps floor
- [ ] The dev overlay still traces every figure on every tab to an API response id
- [ ] The F-29 walk, the new DRS walk and the honesty test all pass
- [ ] The R-07 footer is on all three tabs
- [ ] The 5.13 beats stay one click, and `docs/demo/script.md` says how
- [ ] `npx vitest run` green — baseline before this feature was 30 files, 155 tests

## Out of scope

The planner, beam search and any strategy score. The pit service-time column — verified
unavailable: `senna/env/engine.py:100` computes `pit_time_s`, folds it into `lap_time_s`
and never copies it into `info`, so it never reaches the API. The lap-record panel, and the
reference's invented track-characteristic scores. Mobile 3D and broadcast cameras (R-08).
Any backend change at all: every number this feature displays is already served.

## The declared cut line — Saad's decision, 14 August 2026

This stays **one feature**, because a half-restructured dashboard is worse than either
endpoint. If the session runs long, what gets deferred is the Analysis tab's two new panels
— `RewardPanel` and `AlternativesPanel` — and that tab ships with energy, tyres and
counterfactual restyled only. The language, the shell, the routing, the Strategy page and
the circuit rail are not cuttable; they are the feature.

## Notes for the ship session

Build `palette.ts` and the eleven primitives first, then restyle one section end to end
before touching the rest. If the language is wrong it is wrong once rather than seven times.

The shell and the routing change are the risky half. Two tests are structurally invalidated
rather than merely edited — `App.test.tsx` encodes "six views = six top-level links with
these exact hrefs", which is the thing being removed, and `routeMount.test.tsx` hardcodes
all six flat paths in its hop table. Four more files carry stale-but-unasserted path
literals (`TyreSurfaceView.test.tsx:18`, `CounterfactualView.test.tsx:23,31,49,107`); they
will not fail, and should be corrected anyway.

`frontend/e2e/demo.spec.ts` does not run under vitest or CI — only under `make demo-check`
— so a broken demo URL will not show up in the ship's test gate. Run `make demo-check`
explicitly before the ship report.
