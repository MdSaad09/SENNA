# F12 — Energy view + Tyre Surface view

Approved by Saad, 23 Jul 2026. Both endpoints already exist from F10, so this feature is
mostly frontend work plus four additive API fields. The plan was fact-checked against
the repo (16 claims, all confirmed) and audited on seven spec lenses before approval.

## Decisions (Saad, 23 Jul 2026)

1. **Temperature axis: stylised response.** The T5 fit is age-only, so the surface's
   temperature dimension is a stylised illustration. The label must be unmissable and
   the relief understated, and every hover/readout number comes from the fitted 30 °C
   slice only — nothing numeric off that slice, ever.
2. **Energy view is 2D.** recharts SVG, no second canvas. `/energy` stays a
   zero-canvas route.
3. **Four additive API fields ship**, recorded as a 5.9.2 divergence the same way F10
   and F11 recorded theirs.

Process notes for /ship: `rm -rf .ruff_cache` before the final lint (the warm cache
hid I001 on earlier tests-first features), and check the Actions page after /land.

## Objective & spec anchors

Replace the `/energy` and `/tyres` stubs with the two physics views — the ones a
motorsport engineer probes first (5.13, the 75–90 s demo beat).

- 5.10.2 row 3 (p.27) — Energy view: SOC ribbon over laps + paired harvest/deploy bars
  against the per-circuit harvest cap line; the fictional 4 MJ deploy plane is gone
  (F-02); footer states "modelled, calibrated to 2026 aggregate behaviour" (F-13).
- 5.10.2 row 4 (p.28) — Tyre Surface: grip over age × temperature as a vertex-shader
  surface, cliff visible; renders the fitted model, not raw data; T5 transfer flag for
  compounds without 2026 fits.
- F-02 [CRITICAL] (p.6) + R-03 (p.15) — per-lap deployment routinely exceeds 4 MJ
  because the car harvests during the lap. The cap plane, its penalty and its metric
  were all removed from v3; the regression test below keeps them out.
- F-13 (p.8) — no public channel exposes SOC; energy series are simulator-internal and
  the footer says so, verbatim.
- T5 (p.20) — grip(age) = 1 − a·age^b per compound; circuits without 2026 data carry
  cluster-transferred coefficients flagged low-confidence.
- E-01, E-02, AR-04, AR-05 — SOC hard-bounded [0, 4] MJ; H_max is per-event config,
  never a literal.

## Flagged spec divergences

Recorded here the way F10 and F11 recorded theirs, since the extracted spec must not
be patched.

1. **The temperature axis cannot be fitted.** 5.10.2 row 4 (and 5.5.3's
   `deg(compound, age, track_temp)`) imply a temperature term, but the fit is age-only
   — `configs/env.yaml:81` documents this, and no earlier plan wrote it down. This is
   the first paper-trail entry for the age-only divergence; it cites 5.5.1 as well as
   5.10.2. Resolution per decision 1: stylised and labelled.
2. **The feature spec's Constants row says "Nothing new"**, but the stylised
   temperature response needs new stylised display constants. All are listed below
   with provenance, per the F11 precedent of frontend constants living in
   `frontend/src/config/constants.ts`.
3. **Four additive 5.9.2 shape changes** (decision 3): typed `EnergyLap`,
   `EnergyProfile.usable_soc_mj`, `DegradationCurve.source_circuit` and `.cliff_age`.
   All additive — no rename or removal, so existing consumers keep working. The
   `api/schemas.py` header docstring ("never in new top-level fields") gets reconciled
   in the same commit.

## Deliverables

Backend, small and spec-first:

- `api/schemas.py` — typed `EnergyLap {lap, harvest_mj, deploy_mj, soc_mj, mode, pit}`
  replacing the bare `laps: list`; `EnergyProfile += usable_soc_mj`;
  `DegradationCurve += source_circuit, cliff_age`. Old stored runs already carry
  mode/pit in every frame, so no migration.
- `api/routes/energy.py` — fill `mode` (0–3) and `pit` (0 = stay out, 1–5 = compound
  code + 1) from `frame['agent']`; serve `usable_soc_mj` from
  `configs/physics_2026.yaml` `energy_store.usable_capacity_mj` (sourced AR-04).
- `api/routes/tyres.py` — fill `source_circuit` and `cliff_age` via a helper extracted
  from `senna/env/scenario.py:91`'s existing rule (`max_age_seen`, falling back to
  `obs.tyre_age_norm_laps`, plus `tyre_failure.cliff_age_margin_laps`). One rule, two
  callers: the view draws the same cliff the sim enforces.
- `tests/api/test_tyres_energy.py` — extended for the new fields; the existing two
  tests stay green.

Frontend:

- `src/api/types.ts` + `queries.ts` — TS mirrors of the three models;
  `useEnergyProfile(runId)` with staleTime Infinity once the run is complete (E-16),
  `useDegradationCurves(slug)`.
- `src/views/energy/` — `EnergyView.tsx` + `SocPanel` + `EnergyBarsPanel`, built on
  recharts (pinned since F00, imported nowhere yet, so no new dependency). Two stacked
  panels sharing the lap axis: a SOC area-ribbon bounded by the served
  `usable_soc_mj`, and paired harvest/deploy bars with the served `h_max_mj` as a
  labelled "harvest cap" reference line. Separate panels so H_max can never read as a
  deploy or SOC cap. Pit laps are marked from the recorded pit action. In-flight runs
  (`laps: []`) show run status, never an empty chart. F-13 footer verbatim.
- `src/views/tyres/` — `TyreSurfaceView.tsx` + `GripSurface.tsx`: one CanvasHost, one
  grid mesh, vertex shader displacing z = grip from the served (a, b). Age axis runs
  to the served `cliff_age`, with the zone beyond `max_age_seen` visually distinct —
  the cliff shown honestly, as the fitted-support boundary plus the sim's hazard
  margin. Compound and era selectors; a fit panel showing served
  a/b/n_laps/max_age_seen. Flags key on mechanism: `source_circuit` present means
  "cluster transfer (T5)" naming the donors; `low_confidence` without it means "thin
  fit" (2024 thin fits carry the flag too, so presence of `source_circuit` is the
  discriminator). Honest empty state on 404 — `french_grand_prix` has no fits, and
  `/circuits` `coverage.deg_fit` gates the picker.
- `src/lib/gripSurface.ts` — pure TS twin of the GLSL (the ribbonStrips pattern):
  grip evaluation, vertex grid, cliff attribute. At the reference temperature the
  surface equals the served fitted curve exactly, pinned by test. Hover and readout
  numbers come only from this fitted slice.
- `src/components/` — RunPicker generalised out of `views/replay/` (its
  `coverage.ribbon` filter and "new replay" heading become props; it POSTs
  `/v1/simulations` and writes `?run=`). `PerfProbe.tsx` publishes a cleared snapshot
  on unmount so DevOverlay never shows a dead canvas's draw calls on the chart-only
  Energy route.
- `src/routes.tsx` — swap the two `StubView` entries (lines 25–26); nav already
  exists.
- `src/test/apiFixtures.ts` — energy fixture with per-lap variation and several laps
  of deploy above 4 MJ (SOC ledger self-consistent inside [0, 4]); tyre fixtures for a
  direct fit, a cluster transfer, and a 404; new stub routes. `src/vitest.setup.ts`
  gains a ResizeObserver stub (jsdom lacks it; recharts needs it).

## Constants & configs

No new physics numbers. The backend additions serve values that already live in
configs (`usable_capacity_mj` 4.0 sourced AR-04; the cliff ingredients in
`env.yaml`). New display constants, all in `frontend/src/config/constants.ts` with
provenance tags and `constants.test.ts` pins:

| Name | Value | Origin |
|---|---|---|
| `TYRE_TEMP_AXIS_MIN_C` / `MAX_C` | 15 / 60 | sourced — spec 5.5.1 obs #32 normaliser (T−15)/45 |
| `TYRE_TEMP_REF_C` | 30 | stylised — mirrors `configs/env.yaml` `track_temp_dry_c` |
| `TYRE_TEMP_GRIP_PENALTY` | 0.08 | stylised — understated visual relief; the on-view label owns the honesty |
| `GRIP_AGE_SAMPLES` / `GRIP_TEMP_SAMPLES` | 64 / 33 | operational — tessellation; one draw call either way |
| SOC / deploy / cliff / compound tints | hex values | stylised — exported beside the components that draw them (Legend-swatch pattern); harvest bars reuse `HARVEST_TINT` #0d9488 so harvest is teal everywhere |

The SOC axis maximum is deliberately not a frontend constant — it is the served
`usable_soc_mj`.

The tyre view's label reads: "temperature response — stylised illustration, not
fitted, not a prediction; the T5 fit is age-only". It sits on the view itself, not in
a tooltip.

## Tests first

Backend: `test_energy_profile_serves_usable_soc_and_modes`;
`test_tyres_serve_cliff_age_and_transfer_donors` (the cliff rule asserted against
config values, no literals).

Frontend:

- `EnergyView.test.tsx` — "renders a deploy-heavy run with no 4 MJ cap marker": the
  F-02 trap. findBy data first so the absence check cannot pass vacuously, then
  queryBy absence scoped to the bars panel (the SOC panel legitimately shows the
  served 4 MJ store bound in its axis), plus a positive assertion that the bars
  panel's only reference line equals the served h_max. Also: "states the
  modelled-calibrated footer", "soc axis tops out at served usable_soc_mj", "handles
  an in-flight run honestly", "marks pit laps".
- `TyreSurfaceView.test.tsx` — "renders fitted params, not laps": fixtures route only
  `/v1/tyres` and `/v1/circuits`, the provenance log is asserted to contain no
  lap/frame fetches, and the fit panel's values match the fixture. Also: "flags
  cluster transfers with donors and thin fits distinctly", "states the stylised
  temperature label", "honest empty state on 404".
- `lib/gripSurface.test.ts` — the surface at `TYRE_TEMP_REF_C` equals 1 − a·age^b
  exactly; a property test (seeded mulberry32, seed printed) that grip is
  non-increasing in age and stays within [0, 1] across a ∈ [0, 5] × b ∈ [0.3, 3], the
  `fits.yaml` curve_bounds; the cliff attribute lands at the served `cliff_age`.
- `routeMount.test.tsx` — hops updated to `[/replay 1, /energy 0, /tyres 1,
  /circuit 1]`, MutationObserver peak ≤ 1. This is the spec's one-canvas test.
- `constants.test.ts` — pins the new constants.

## Edge cases handled

- E-01 — the SOC axis bound is served; the ledger comes straight from stored frames;
  the view cannot invent refills.
- E-02 — H_max is drawn from the response (originating in `circuits.yaml`), labelled
  as the per-event harvest cap; no 8.5 literal in the frontend.
- E-09 — the surface renders fit parameters only; the data-source test proves no lap
  data is fetched.
- E-15 / E-16 — both GETs trace through the provenance ring with X-Model-Version;
  energy data is cached indefinitely only once the run is complete; in-flight runs
  are status-gated.
- E-18 — the tyre canvas inherits CanvasHost's context-loss overlay; the Energy view
  has no canvas at all.
- F-28 / T5 / F-02 — covered by the three spec'd tests above.

## Acceptance checklist

- [ ] Both views live against real simulation runs; footers and flags present
- [ ] Axes read in MJ with SOC bounded [0, 4] everywhere (bound served, not hardcoded)
- [ ] Perf budget still holds with either view mounted (runtime checklist via
      `__SENNA_PERF`, as F11)
- [ ] All three spec'd tests exist and were shown failing first

## Out of scope

Live streaming and counterfactuals (F13); any tyre-temperature refit (notebooks work,
not frontend); redis caching for the two GETs; M4/M9 metrics (F14); the full ribbon
library `make circuits` run (a separate pre-video task, already in INDEX).
