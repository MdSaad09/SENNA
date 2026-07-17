# F03 — Synthetic 2026 generator (T1–T8): plan

## Context

F02 turned the 2022–2026 Postgres data into fitted constants: per-circuit joint pace
(t0, k_m, evolution, sigma_driver), tyre degradation with cluster transfer, braking and
full-throttle energy integrals, pit loss, and SC/VSC/red hazard bands — all in
`configs/physics_params.yaml`. F03 turns that 2024-era raw material into 2026-era race
dynamics for every circuit via the eight named transformations of spec 5.4, calibrated
on 2026 rounds 1–6 and validated on rounds 7+ (frozen split, E-14). The output is what
F05's env will read. Reality check from the live params file: five circuits have real
both-era joint-pace fits (Australia, China, Japan, Miami, Monaco), Canada is 2026-only,
France has neither modern era — so the generator needs an explicit precedence rule,
not a single code path.

## Objective & spec anchors

Every circuit in the data-driven index gets a defensible 2026 profile — base pace,
energy budget (the "four numbers"), fuel/mass, tyres, overtaking — written to a new
`configs/transforms.yaml` with fitted provenance, plus the 5.4.1 validation suite
reported per held-out circuit with Chapter 6 figures from a make target.

Anchors that shaped choices:
- **5.4 T1–T8** — each transformation is one named module; "no GAN" stands: every
  formula is defensible line by line.
- **5.4.1 / A-02** — calibrate on rounds 1–6, validate on 7+; KS < 0.15, stint EMD,
  pit loss within 1.0 s, event-rate bands, derate plausibility.
- **E-02** — per-event H_max lives in a new `circuits.yaml` with source note and date.
- **E-13** — Madrid is simply absent until its data exists; the circuit index is
  generated from ingested data, no special-casing.
- **E-14** — every calibration fitter refuses rounds 7+; only one module may read
  held-out data, and a test enforces the import boundary.
- **F-02/F-04** — energy accounting is SOC + per-circuit E_dep and harvest-by-mode;
  no per-lap deployment cap anywhere.
- **F-05** — T7's 2026 aid is Manual Override (gap ≤ 1.0 s); the 2024-era model uses
  the same 1.0 s detection rule for DRS, era symmetry via config.
- **F-06 / AR-10** — T6 fuel from the ~70 kg allowance. Verified 16 Jul (INDEX
  decisions log); this plan lifts the grade-C flag — question 1 below.
- **AR-01/02/08/09** — the sourced deltas T1–T3 consume, read from physics_2026.yaml.
- **AR-06/07** — lift-and-coast at 350 kW forcing Z-mode, super clipping ~250 kW;
  these two mechanisms are T4's harvest-by-mode terms.
- **AR-17/18** — dirty air and compounds are fit-don't-assume; T7 fits the 2026 shift,
  T5 stays the F02 refit-plus-transfer (F03 adds a completeness gate, not new fits).

**Interpretation flags (master spec wins, so they are flagged, not patched):**
1. T2's corner-speed exponent is fitted **globally** across the five both-era
  circuits, not per circuit — five circuits cannot identify per-circuit exponents;
  per-circuit spread becomes a notebook diagnostic. Fallback to the 0.25 prior
  (flagged stylised) if the sample gates fail.
2. T8's "median(simulated)" uses the **deterministic** model-implied lap curve, not a
  Monte Carlo draw — a fitted constant must not depend on a seed. The MC exists for
  the 5.4.1 distribution comparisons only.
3. T1 needs 2024 telemetry; where a circuit has none (France), its T-deltas transfer
  from its T5 cluster mates, flagged `low_confidence` + `source_circuit` — the same
  donor mechanism F02 already uses. Where real 2026 fits exist (the six calibration
  circuits), real beats transform and the transform prediction is logged beside it as
  a free error diagnostic.

## Deliverables

New package `senna/physics/synth/` mirroring `fits/`: fitters pure (frames in,
dataclasses out, thresholds as arguments), only `frames.py`/`heldout.py` touch
Postgres, only `run.py`/`validate.py` read configs and write files.

| File | What and why |
|---|---|
| `senna/physics/synth/frames.py` | DB→pandas for synth (2026 calibration laps, position/gap frames for T7); replicates the `_held_in` guard from `fits/frames.py` |
| `senna/physics/synth/heldout.py` | the ONLY module allowed to read rounds 7+; loaders named `held_out_*`; imported only by `validate.py` (test-enforced) |
| `senna/physics/synth/segments.py` | telemetry lap segmentation: acceleration / braking / corner phases from Brake+Throttle edges, distance by ∫v·dt, never across a `trace_id` gap (AR-16 conventions from `fits/energy.py`) |
| `senna/physics/synth/pointmass.py` | T1: fit effective (P_eff, β_eff, μ_eff, κ_eff) per circuit from 2024 telemetry — no sourced ρ/CdA/η anywhere; self-check gate reproduces observed 2024 phase times; swap in 2026 power+taper+drag → full-throttle time, terminal speeds, E_dep, Δlap_s |
| `senna/physics/synth/aero.py` | T2: matched-corner apex extraction 2024 vs 2026 on both-era circuits; global exponent fit of log(v26/v24) vs log(0.70); prior fallback flagged |
| `senna/physics/synth/energy_budget.py` | T4: per circuit H_max (circuits.yaml), harvest-by-mode = braking (re-integrated on the 2026 profile) + clipping (250 kW × full-throttle time) + lift-and-coast sweep → **c_lc = fitted sweep slope**; E_dep from T1; derate-deficit ranking; derived c_atk and p_der (question 3) |
| `senna/physics/synth/mass_fuel.py` | T3+T6: 70 kg allowance, burn rescale via `fits/fuel.py`, static mass delta through fitted k_m — per-lap mass lives in k_m only, never double-counted in T1 |
| `senna/physics/synth/overtaking.py` | T7: racing-pass and opportunity extraction from `Lap.position` + cumulative-time gaps (lap 1, pit cycles, non-green, restarts, retirements excluded); sprint sessions enter the extraction — the model is per-opportunity, so shorter exposure cannot bias it (unlike the per-race hazard counts F02 excluded them from), and 2026 sprint laps are scarce real passing evidence; logistic P(pass) with circuit effects + a 2026 era shift fitted on rounds 1–6 only |
| `senna/physics/synth/assemble.py` | composes t0_2026 = t0_2024 + ΔT1/T2 + ΔT3 per circuit; applies real-beats-transform-beats-donor precedence; T5 completeness gate: every indexed circuit must have a 2026 degradation block or the battery fails loudly |
| `senna/physics/synth/residual.py` | T8: c_circuit = median(real 2026 green laps, rounds 1–6) − median(model-implied curve) per calibration circuit; pooled c_global for unseen circuits; refuses validation rounds |
| `senna/physics/synth/montecarlo.py` | seeded generator-level sampler (explicitly NOT the F05 env, docstring says so): 22 cars × n_races per circuit; draws SC/VSC from fitted hazards, driver effects from sigma_driver, lap noise from joint-fit residuals; deterministic t0/fuel/evolution/degradation/status terms; stints from min-time compound plans + jitter; one SeedSequence spawned per (circuit, race) |
| `senna/physics/synth/validate.py` | the 5.4.1 suite per held-out circuit → `docs/synth/` figures + `docs/synth/validation_summary.yaml`; the only importer of `heldout.py` |
| `senna/physics/synth/plots.py` | Chapter 6 figure helpers rooted at `docs/synth/` (pattern of `fits/plots.py`) |
| `senna/physics/synth/run.py` | battery CLI (`--only`, `--circuit`); dependency order T2→T1→T4→T3/T6→assemble→T7→T8; writes `transforms.yaml` on full runs only |
| `senna/physics/fits/params_writer.py` | `render_params()` gains a header parameter so transforms.yaml reuses the byte-deterministic emitter and null guard |
| `configs/synth.yaml` | new: every battery input threshold with provenance (table below) |
| `configs/circuits.yaml` | new, hand-maintained sourced facts: per-event `h_max_mj` with source note + date (E-02); seeded at the 8.5 baseline (question 2) |
| `configs/transforms.yaml` | new, generated: every T-output per circuit with fitted provenance and low-confidence/fallback flags |
| `configs/physics_2026.yaml` | `fitted.conserve_pace_cost_s_per_mj` ← cross-circuit median c_lc; AR-10 comment updated per the INDEX close-out; c_atk/p_der if question 3 approved |
| `configs/physics_2024.yaml` | add `sporting.drs_detection_gap_s: 1.0` (sourced) for T7 era symmetry |
| `Makefile` | `synth:` → `python -m senna.physics.synth.run`; `synth-figures:` → `python -m senna.physics.synth.validate` (report stays F14's) |
| `notebooks/fit_*.ipynb` | five thin notebooks (below) — every computation an import; `fit_overtaking` states explicitly that sprints enter the pass extraction and why (Saad's addition, 17 Jul) |
| `tests/physics/synth/test_*.py` | test battery (below) |

Ownership rule, one line: **F02 owns fits-from-real-data (physics_params.yaml,
untouched), F03 owns transforms (transforms.yaml), circuits.yaml is sourced facts.**

## Constants & configs

| Name | Value | Origin | Yaml |
|---|---|---|---|
| `pointmass.representative_laps` | 5 | stylised — fastest green laps pooled per circuit | synth.yaml |
| `pointmass.min_straight_s` | 3.0 | stylised — full-throttle run counted as an X-mode section | synth.yaml |
| `pointmass.accel_smooth_window_s` | 0.5 | stylised — finite-difference smoothing at 4–5 Hz (AR-16) | synth.yaml |
| `pointmass.profile_tolerance_frac` | 0.05 | stylised — self-check gate before a circuit's transform is trusted | synth.yaml |
| `pointmass.reference_fuel_frac` | 0.5 | stylised — T1 runs at half tank; per-lap mass lives in k_m only | synth.yaml |
| `aero.exponent_prior` | 0.25 | sourced spec 5.4 T2 — fourth-root prior | synth.yaml |
| `aero.exponent_bounds` | [0.1, 0.6] | stylised — plausibility gate; outside → prior, flagged | synth.yaml |
| `aero.min_corner_apex_kmh` | 150 | stylised — aero-dominated corners only | synth.yaml |
| `aero.min_corners` | 30 | stylised — sample gate for the exponent fit | synth.yaml |
| `energy_budget.lc_sweep_points` | 10 | stylised — lift-point grid per straight for the c_lc slope | synth.yaml |
| `overtaking.pace_window_laps` | 3 | stylised — rolling pace window for Δpace | synth.yaml |
| `overtaking.restart_exclude_laps` | 1 | stylised — post-intervention green laps excluded | synth.yaml |
| `overtaking.retire_lookahead_laps` | 2 | stylised — passes on dying cars excluded | synth.yaml |
| `montecarlo.n_races` | 200 | stylised — KS stability at ~10⁴ green laps per circuit | synth.yaml |
| `montecarlo.seed` | 20260717 | stylised — determinism | synth.yaml |
| `montecarlo.stint_jitter_laps_sigma` | 1.5 | stylised — real pit-window spread | synth.yaml |
| `validation.ks_target` | 0.15 | sourced 5.4.1 | synth.yaml |
| `validation.pit_tolerance_s` | 1.0 | sourced 5.4.1 | synth.yaml |
| `h_max_mj` per event | 8.5 seed | sourced AR-05 default, dated note per event (E-02) | circuits.yaml |
| `sporting.drs_detection_gap_s` | 1.0 | sourced — 2011–2025 sporting regs | physics_2024.yaml |
| every T-output | — | fitted: named notebook; fallbacks flagged | transforms.yaml |

No inline constants anywhere; all thresholds arrive at fitters as arguments.

## Tests first

`tests/physics/synth/`, mirroring the package; no network, no DB; seeded synthetic
telemetry and race frames in the F02 conftest style. Written and shown failing first.

- `test_pointmass.py::test_flat_out_closed_form` — **spec-mandated**: β=0 flat circuit
  below taper onset; full-throttle time matches the analytic point-mass solution and
  E_dep = 350 kW × t exactly
- `test_pointmass.py::test_taper_shape` — P_K(v) = 350 kW at ≤290, 0 at ≥355,
  monotone non-increasing between (parametrized sweep)
- `test_pointmass.py::test_recovers_effective_params` — P_eff/β_eff recovered from
  synthetic telemetry with known values; `::test_never_crosses_trace_gap`;
  `::test_self_check_gate_flags_bad_fit`
- `test_aero.py::test_recovers_known_exponent`; `::test_weak_sample_falls_back_to_prior_flagged`
- `test_energy_budget.py::test_supply_is_min_of_cap_and_mechanisms` — conservation:
  supply = min(H_max, braking + clipping + L&C); `::test_c_lc_matches_analytic_sweep`;
  `::test_missing_circuit_entry_uses_default`; `::test_null_h_max_raises`
- `test_mass_fuel.py::test_total_burn_equals_allowance`; `::test_mass_delta_is_k_m_arithmetic`
- `test_overtaking.py::test_extraction_excludes_lap1_pits_sc_restarts_retirements`;
  `::test_logistic_recovers_injected_shift`
- `test_residual.py::test_refuses_validation_rounds` — **spec-mandated T8 leakage
  guard**; `::test_c_circuit_median_arithmetic`; `::test_c_global_pooling`
- `test_frames.py::test_calibration_loaders_refuse_rounds_7_plus` — **spec-mandated
  split guard (E-14)**; `::test_no_calibration_module_imports_heldout` — the import
  boundary, checked via module inspection
- `test_montecarlo.py::test_same_seed_byte_identical`; `::test_different_seed_differs`;
  `::test_higher_deg_shortens_stints` (monotonic); full-size run carries `slow`
- `test_validate.py::test_ks_and_emd_match_scipy_reference`; `::test_ks_detects_half_second_shift`;
  `::test_band_and_pit_tolerance_checks`
- `test_transforms_writer.py::test_null_guard`; `::test_byte_deterministic`;
  `::test_every_leaf_carries_provenance`

Property tests: none formally — the hypothesis-based 100k-action suites arrive with
F05; the taper and MC determinism pins above are parametrized sweeps, not hypothesis.

## Edge cases handled

- **E-02** — H_max read per event from circuits.yaml with a dated source note;
  default 8.5 only through the config chain, never a code literal.
- **E-13** — the circuit index comes from ingested data; Madrid appears when its data
  does; no list is hard-coded and no claim says "all 24".
- **E-14** — three layers: frames guard (`_held_in` pattern), fitter guard
  (`_refuse_validation_rounds` pattern in T7/T8), and the heldout import boundary
  with its test. `validate.py` alone touches rounds 7+.
- **E-09 (inherited)** — synth frames reuse the F01 cleaners; the MC and residual fit
  see green, accurate laps only.
- **E-10 (inherited)** — mass effects go through the jointly-fitted k_m; T1 runs at a
  fixed reference fuel so fuel-mass pace never enters twice.
- **Mixed-coverage circuits (found in the data)** — Canada (2026 only): real fits
  used, transform skipped, logged. France (neither era): cluster-donor transfer,
  flagged. Miami (no 2026 energy): energy transforms from 2024, real joint pace kept.

## Acceptance checklist

- [ ] Every 5.4.1 target computed and reported per held-out circuit — met, or the
      miss documented with cause in `docs/synth/validation_summary.yaml` (no tuning
      against held-out rounds, ever)
- [ ] Sim-to-real headline number (held-out median error) reported per circuit
- [ ] No transformation reads a hard-coded physics literal — configs only; the
      transforms writer refuses nulls and uncommented leaves
- [ ] `transforms.yaml` covers every circuit in the index, each value with provenance
      and explicit fallback flags where the donor path ran
- [ ] `circuits.yaml` exists with per-event H_max + source note + date
- [ ] `fitted.conserve_pace_cost_s_per_mj` no longer null in physics_2026.yaml
- [ ] The three spec-mandated tests green: T1 closed form, split guard, T8 leakage
- [ ] `make synth` runs the battery; `make synth-figures` regenerates every Chapter 6
      figure from scratch; two consecutive runs are byte-identical
- [ ] Five notebooks execute top to bottom; PNGs land under `docs/synth/`

## Out of scope

- The env consuming these numbers (F05); rival behaviour and archetypes (F06).
- Circuit geometry / GPS ribbons (F04) — T1 segments telemetry, it never needs
  coordinates.
- New tyre fits — T5 is F02's refit + transfer; F03 only gates completeness.
- Weather Markov chains and tyre-failure hazards — the F02 flag stands; F05 planning
  owns the decision.
- Re-ingesting anything; rounds 7+ data is already in Postgres, read-only here.

## Questions for Saad

**Answered 17 Jul 2026:** 1 — yes, AR-10 verified per the INDEX decisions log, cite it
in the physics_2026.yaml comment, 70 kg stands, T6 unblocked. 2 — yes, seed at 8.5
with dated notes; sourced per-event figures substituted later. 3 — yes, fill c_atk and
p_der now. Addition: the overtaking notebook must state explicitly whether sprint
sessions enter the pass extraction, and why (they do — recorded in the deliverables).

1. **Lift AR-10 to verified?** You closed it out on 16 Jul (INDEX decisions log):
   ~70 kg, energy-flow limited. The spec note says T6 blocks until this is surfaced —
   this is the surfacing. *Proposed default: yes — update the physics_2026.yaml
   comment to cite the INDEX close-out, keep 70 kg, T6 unblocked.*
2. **Per-event H_max sourcing.** Real FIA per-event figures exist only in scattered
   2026 reporting. *Proposed default: seed every circuits.yaml entry at the 8.5
   baseline with a dated "no event-specific figure found" note; you research raced
   rounds when convenient and substitute sourced values — the battery reruns in one
   command.*
3. **Fill c_atk and p_der too?** physics_2026.yaml names F02/F03 as their owner and
   they fall out of the same point-mass profile nearly free; strictly they are 5.5.3
   (env) scalars. *Proposed default: yes, fill them now so F05 finds no nulls.*

## Verification

- `pytest tests/physics/synth -q` — battery green after first being shown red;
  `pytest -m "not slow"` stays fast.
- `make synth` end-to-end on the real DB: transforms.yaml materialises; a second run
  produces an empty `git diff` (byte-determinism).
- `make synth-figures`: 5.4.1 figures + validation_summary.yaml regenerate under
  `docs/synth/`; KS/EMD/pit/event-band numbers appear per held-out circuit.
- Spot-read through the loader: `config.load('transforms')` → E_dep and the four
  energy numbers for a calibration circuit and a donor-flagged circuit; a null raises.
- Execute the five notebooks (`fit_point_mass`, `fit_corner_exponent`,
  `fit_energy_budget`, `fit_overtaking`, `fit_residual_2026`) top to bottom.
