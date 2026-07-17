# F04 — Circuit ribbon pipeline · approved plan

Depends on: F01 (Done). Spec anchors: 5.10.1, E-13, E-17, F-08, F-12.
Approved by Saad, 17 Jul 2026, with three changes folded in (see the change log at the end).

## Objective & spec anchors
Build a validated GLTF track ribbon per circuit: fastest-clean-lap centreline, resampled
by arc length at 2 m, Savitzky-Golay smoothed (Z harder than X/Y), closed into a loop,
carried by rotation-minimising frames, extruded into a 12 m ribbon whose half-width is
clamped to the local curve radius. Add corner, braking-zone and X-mode annotations,
treat elevation as decoration, and emit a data-driven circuit index. This is the 3D
foundation F11-F13 stand on.

- **5.10.1** — the seven-step ribbon algorithm is the contract, implemented step for step.
- **E-17** — a 12 m ribbon on a sub-6 m-radius hairpin self-intersects, and Frenet frames
  flip at inflection points. Handled by rotation-minimising frames plus a half-width clamp,
  and asserted by a no-self-intersection test across every ingested circuit. Monaco and
  Hungary are the stress cases.
- **F-12** — elevation and banking are a visual treatment, not data. Smoothed Z is
  exaggerated x1.5, a flat-plus-camber fallback covers circuits with no Z, and both are
  flagged `stylised` in the metadata.
- **E-13 / F-08 / AR-13** — the circuit library is generated from ingested data, never
  hand-listed. Madrid appears on its own once its first 2026 session is ingested; all
  counts are computed at build time.

**Master-spec conflict, resolved (master wins).** The F04 feature spec says
"circuits.yaml generated from ingested data, never hand-listed." Master **E-02** makes
`configs/circuits.yaml` the hand-maintained per-event H_max registry, which F03 owns and
which must never be generated. Those are two different artifacts sharing a name. The
generated library (F-08 / E-13) becomes `data/circuits/index.json`; `configs/circuits.yaml`
is left exactly as F03 owns it. F04's own constants live in a new `configs/ribbon.yaml`
(Saad's call — keeps circuits.yaml purely the sourced H_max registry, and matches the
`fits.yaml` / `synth.yaml` one-file-per-concern convention).

## Deliverables
New package `senna/circuits/`, with pure geometry kept separate from I/O so the geometry
core is testable without FastF1 or a database.

- `senna/circuits/geometry.py` — pure numpy: arc-length resample at 2 m, loop closure,
  Savitzky-Golay smoothing (X/Y and Z separately, Z harder), rotation-minimising frames
  by double reflection, local curve radius, the 12 m extrusion with half-width clamped to
  local radius, and a segment-vs-segment self-intersection test. No pandas, no I/O.
- `senna/circuits/annotations.py` — corners from `get_circuit_info()`; braking zones from
  speed-drop detection (a drop over 50 km/h within 100 m); X-mode sections as the longest
  full-throttle stretches; pit lane as an offset spline.
- `senna/circuits/elevation.py` — smoothed Z x1.5, or a flat-plus-corner-camber fallback
  where Z is absent; returns the `stylised` provenance flags either way (F-12).
- `senna/circuits/export.py` — GLB (binary GLTF, via `pygltflib`) writer plus a metadata
  JSON writer carrying lap length, corners, braking zones, X-mode sections, and every
  stylised flag the UI can surface.
- `senna/circuits/sources.py` — picks the most recent dry session per event from Postgres
  (`Session.is_dry`) and returns the plan the builder loads telemetry for.
- `senna/circuits/build.py` — CLI (`python -m senna.circuits.build`): for every ingested
  event with data, load the fastest-clean-lap telemetry and circuit info, build the ribbon,
  annotate it, export `data/circuits/<slug>/{ribbon.glb,meta.json}`, and emit the generated
  `data/circuits/index.json` (coverage flags, build-time counts).
- `senna/circuits/__init__.py` — the public surface.
- `senna/data/fastf1_loader.py` (edit) — add `load_fastest_lap_telemetry(...)` returning the
  fastest clean lap's merged X/Y/Z/Speed/Throttle/Distance as numpy, and `load_circuit_info(...)`.
  Only this module imports fastf1 (senna/CLAUDE.md); reuses `clean_pos_data` for the
  decimetre-to-metre conversion, the OnTrack filter and the z-score gate.
- `configs/ribbon.yaml` (new) — the ribbon/braking/X-mode constants, each with a provenance
  comment. Header states it is F04's stylised-geometry config, distinct from the sourced
  `circuits.yaml` H_max registry.
- `requirements.in` (edit) + `make lock` — add `pygltflib` (pure-Python GLB writer).
- `Makefile` (edit) — add a `circuits:` target (`python -m senna.circuits.build`), local
  only like `fit` and `synth`.
- `tests/circuits/` — the suite below.
- `docs/learn/F04-circuit-ribbons.md` — Saad's lesson (written during /ship, not now).

## Constants & configs
All in the new `configs/ribbon.yaml`.

| Name | Value | Origin | Note |
|---|---|---|---|
| `ribbon.resample_spacing_m` | 2.0 | stylised | spec 5.10.1 item 2 |
| `ribbon.width_m` | 12.0 | stylised | item 4 |
| `ribbon.elevation_exaggeration` | 1.5 | stylised | item 5 (F-12) |
| `ribbon.savgol_window_xy` | 11 | stylised | odd, greater than polyorder; 11 x 2 m ~ 22 m |
| `ribbon.savgol_polyorder_xy` | 3 | stylised | |
| `ribbon.savgol_window_z` | 31 | stylised | Z smoothed harder (item 2) |
| `ribbon.savgol_polyorder_z` | 3 | stylised | |
| `ribbon.camber_deg` | 3.0 | stylised | flat-fallback corner camber |
| `ribbon.pos_data_units_per_m` | 10 | sourced | FastF1 pos_data is decimetres (spec 5.3) |
| `ribbon.lap_length_tolerance_pct` | 5 | sourced | spec 5.10.1 item 7 |
| `braking.speed_drop_kmh` | 50 | sourced | spec 5.10.1 item 6 (kept from v2) |
| `braking.window_m` | 100 | sourced | item 6 |
| `xmode.full_throttle_pct` | 99 | stylised | longest full-throttle stretches, inferred |

The Savitzky-Golay windows and the camber angle are proposed defaults, tunable during /ship.
All are stylised, so the spec-auditor needs the provenance label, not an external source.

## Tests first
Under `tests/circuits/`. Pure-geometry tests run in CI against synthetic fixtures; the
cache-dependent sweep is marked `slow` and skips when the FastF1 cache is absent.

- `test_geometry.py`
  - `test_resample_gives_uniform_2m_spacing` — resampled spacing is ~2 m within tolerance.
  - `test_loop_closure_first_last_coincide` — first and last centreline points coincide
    after resample and close (feature-spec test 4).
  - `test_rmf_no_twist_flip_across_hairpin` — on a synthetic hairpin, rotation-minimising
    frame normals stay continuous (consecutive dot > 0) while a Frenet baseline is shown to
    flip — the parallel-transport check (feature-spec test 2, E-17).
  - `test_ribbon_no_self_intersection_synthetic_hairpin` — extrude 12 m along a sub-6 m
    radius; the clamp engages and no edges cross (E-17).
  - `test_halfwidth_clamped_to_local_radius` — the inner edge never crosses the centreline
    on tight curvature.
  - `test_savgol_z_smoothed_harder_than_xy` — Z uses the wider window.
  - `test_no_self_intersection_across_ingested_circuits` (property/parametrised, `slow`,
    skip-if-no-cache) — the E-17 "asserted across every ingested circuit" invariant.
- `test_annotations.py`
  - `test_braking_zone_flagged_on_50kmh_drop_within_100m`; `test_gentle_deceleration_not_flagged`.
  - `test_xmode_section_is_longest_full_throttle_stretch`.
  - `test_corners_drawn_from_circuit_info`.
- `test_elevation.py`
  - `test_elevation_exaggerated_and_flagged_stylised`.
  - `test_missing_z_falls_back_to_flat_camber_and_flagged` (F-12).
- `test_export.py`
  - `test_glb_roundtrips_with_ribbon_mesh` — write GLB, re-read, vertex/index counts match.
  - `test_metadata_json_carries_stylised_flags` — elevation, banking and X-mode labelled
    stylised (F-12).
  - `test_lap_length_within_5pct` — a synthetic closed loop of known length passes the gate
    (feature-spec test 3).
- `test_build_index.py`
  - `test_index_generated_from_ingested_only` — built from a fake source list, no hard-coded
    22 or 24 (F-08).
  - `test_madrid_absent_until_ingested` (E-13).
- `test_config.py`
  - `test_ribbon_constants_load_with_provenance` — constants resolve through `config.get`;
    provenance comments present.

## Edge cases handled
- **E-17** — rotation-minimising frames plus the half-width clamp; a frame-flip test on a
  synthetic hairpin and a no-self-intersection sweep across all ingested circuits.
- **E-13** — data-driven `index.json` from ingested sessions; Madrid absent until its first
  session; counts computed at build time.
- **F-12** — elevation x1.5 and the camber fallback are emitted as `stylised`; banking is
  never treated as data.
- **F-08** — the circuit library is generated, not hand-listed; it feeds the future
  `GET /api/v1/circuits`.
- In/out-lap poisoning — fastest clean lap only (reuses F01's accurate-lap filtering); dry
  sessions selected via `Session.is_dry`.

## Acceptance checklist
- [ ] One `ribbon.glb` + `meta.json` per circuit with data; Madrid absent until ingested.
- [ ] All geometry tests green across the library (self-intersection, frame flip, loop
      closure, lap length within 5%).
- [ ] Every stylised choice (elevation, banking, X-mode) labelled in metadata the UI can surface.
- [ ] Circuit index generated from ingested data, never hand-listed.
- [ ] Every new constant lives in `configs/ribbon.yaml` with a sourced/stylised provenance
      comment (spec-auditor clean).
- [ ] fastf1 imported only in `senna/data`; no stray module-level RNG or globals.

## Out of scope
- Rendering and the Circuit Explorer view (F11).
- Energy-zone values / H_max (F03 owns them; `configs/circuits.yaml` is untouched).
- Pit-lane strategy modelling (F04 emits only the pit-lane spline geometry).
- Official section data for X-mode (stylised until it exists).
- Serving the index over the API (F10).

## Deferred to F11 (open question to record there)
How the frontend and CI obtain the GLBs, given F04 writes them gitignored under
`data/circuits/`. Committing the small, stable ribbon geometry is a fine option and the
current front-runner; decide it when F11 needs the assets in a build.

## Change log vs the presented plan
1. Q1 — add `pygltflib` for GLB export (confirmed).
2. Q2 — outputs gitignored under `data/circuits/`, regenerated by `make circuits`; the
   frontend/CI delivery question is recorded above for F11.
3. Q3 — F04's stylised constants go in a new `configs/ribbon.yaml`, not a block appended to
   `circuits.yaml`, so `circuits.yaml` stays purely the sourced H_max registry.
