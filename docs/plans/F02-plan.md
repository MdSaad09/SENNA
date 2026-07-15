# F02 — Physics model fits: plan

## Context

F01 landed all 2022–2026 race data in Postgres behind the cleaning contract, with
per-season quality reports. F02 turns that data into every fitted constant the
simulator needs and writes them to a new `configs/physics_params.yaml` — the
interpretability contract for the physics layer. F03 (synthetic 2026) and F05 (env)
consume this file. Data on hand: nine 2026 races (Australia → Britain); rounds 1–6
calibrate per the frozen split, rounds 7+ stay held out. Sprints exist at China,
Miami and Canada. Telemetry lives in the FastF1 on-disk cache, not Postgres.

## Objective & spec anchors

Produce every fitted constant with a residual plot each, all in
`configs/physics_params.yaml` with `fitted: <notebook>` provenance — no nulls among
the F02-owned constants F05 reads, nothing silently promoted past grade C.

Anchors that shaped choices:
- **E-10** — joint fuel/evolution fit; fitting either alone double-counts the trend.
- **E-09** — in/out and inaccurate laps poison tyre fits; the fitter itself refuses them.
- **E-14** — frozen split; the fitter refuses 2026 rounds ≥ 7.
- **F-06 / T6** — fuel from the energy allowance (~70 kg era); status-aware burn profile.
- **F-13** — energy series are simulator-internal: integrals estimate budgets from
  Speed/Brake/Throttle traces; no real per-lap ERS telemetry exists.
- **F-14** — the fitting entrypoint raises if a season's quality report is missing.
- **AR-10** — 70 kg race fuel is grade C; every 2026 joint-pace output carries the flag.
- **AR-16** — telemetry is ~4–5 Hz; all integrals use actual timestamp deltas.
- **T5 groundwork** — 2026 degradation from rounds 1–6 where available; cluster
  transfer elsewhere, flagged low-confidence.

**Flagged divergence (master spec wins, so it is flagged, not patched):** E-10 says
"joint fit per race", but fuel modelled as linear burn is exactly affine in
lap_number within one race — a and b have no unique per-race solution. Resolution:
(1) a **status-aware fuel profile** (SC/VSC laps burn less, total burn = allowance
per T6), which breaks collinearity in any race with an interruption; (2) fit **per
circuit per era, pooled over that circuit's dry races** with session, driver and
compound fixed effects; (3) where VIF still exceeds the threshold, refit without the
fuel column, report the always-identified combined trend, decompose it via the
inverse-variance-pooled k_m from identified circuits, and mark `identified: false`.
The fitted sum a·fuel + b·lap always reproduces the observed trend — only the
attribution is borrowed when identification is weak, and the yaml says so. E-10's
real failure mode (double-counting) cannot occur by construction. Documented in the
joint-pace notebook.

**Flagged additions beyond F02's deliverable list** (cheap by-products F05's contract
needs; Saad can veto): SC/VSC lap-time multipliers (5.5.3 `status_mult`, fitted from
the flagged non-green laps), per-circuit `t_ref` / `s_ref` (5.5.4 reward scaling),
`sigma_driver` (5.5.3 pace noise), and compound fixed-effect offsets. Weather Markov
and tyre-failure hazards are fitted nowhere in F02's list — left for F03/F05 planning
to own (gap flagged, not filled here).

## Deliverables

New package `senna/physics/fits/` — fitters are pure (DataFrame in, dataclass out; no
I/O, no config reads — thresholds arrive as arguments, the `cleaning.py` convention).
Only `frames.py` touches Postgres; only `run.py` reads configs and writes files.

| File | What and why |
|---|---|
| `senna/physics/fits/gate.py` | F-14 gate: `assert_quality_reports(seasons, report_dir)` raises `MissingQualityReportError` via `quality.report_path()`; runs before any engine exists |
| `senna/physics/fits/frames.py` | Async query layer → pandas frames (laps per circuit-era joined through Session/Event, pit stops, circuit index); reuses F01 cleaners at fit time |
| `senna/physics/fits/fuel.py` | Status-aware fuel profile: green laps weight 1.0, SC/VSC laps `sc_burn_factor`; weights normalised so total burn = allowance (T6) |
| `senna/physics/fits/joint_pace.py` | E-10 OLS via `numpy.linalg.lstsq`: session+driver+compound FEs, per-compound age+age², fuel (→k_m), lap_number (→evolution); VIF + condition number + SEs by hand (no statsmodels); weak-ID decomposition; also t0, sigma_driver, t_ref, s_ref |
| `senna/physics/fits/degradation.py` | grip(age)=1−a·age^b per compound/circuit/era via `scipy.curve_fit` with bounds, on joint-fit partial residuals (a = A/t0); E-09 guard raises on any in/out or inaccurate row — defensively, inside the fitter |
| `senna/physics/fits/hazards.py` | SC/VSC/red per-race rates from `track_status` digits (SC=4, VSC=6/7, red=5), Wilson 95% bands, per-lap `lambda = −ln(1−p)/median_race_laps`; SC/VSC lap-time multipliers; cross-check vs RaceControlMessage reported in the notebook |
| `senna/physics/fits/pit_loss.py` | OpenF1 `pit_duration_s` per circuit → mean, sigma, n (E-05 FIFO inputs); >60 s outliers excluded with counts reported |
| `senna/physics/fits/energy.py` | Braking-energy (ΔKE = ½·m·Δv² per brake phase, mass = car + fuel-at-lap) and full-throttle integrals per green lap; trapezoid over actual timestamps within `trace_id` segments only — nothing crosses a 2 s gap; median cadence stored as AR-16 evidence |
| `senna/physics/fits/clusters.py` | T5 groundwork: KMeans on era-2024 deg coefficients + layout features, k by silhouette over 2–6, seeded; ratio transfer to 2026-dataless circuits, `low_confidence: true` + `source_circuit` |
| `senna/physics/fits/params_writer.py` | Hand-rolled deterministic YAML emitter — fixed key order, sorted slugs, every leaf commented with its origin; `validate_complete()` raises listing nulls among F02-owned F05 keys |
| `senna/physics/fits/plots.py` | Residual-plot helpers (matplotlib Agg) saving PNGs to `docs/fits/<module>/` so plots survive without committed notebook outputs |
| `senna/physics/fits/run.py` | Orchestrator + CLI (`--only`, `--circuit`, `--params-out`); gate first, then fits, then writer; `asyncio.run` wrapper like `ingest.py` |
| `senna/data/fastf1_loader.py` | Gains public `load_car_data(season, round, session)` — the only legal fastf1 import site (senna/CLAUDE.md) |
| `configs/fits.yaml` | New: every fit threshold with provenance (below) |
| `configs/physics_params.yaml` | New: the output artifact — schema below |
| `configs/physics_2026.yaml` | `fitted.mass_sensitivity_s_per_kg` set to pooled k_m, comment pointing at per-circuit values |
| `Makefile` | `fit:` stub becomes `python -m senna.physics.fits.run $(ONLY)`; local-only, never CI (like ingest) |
| `requirements.in` | scipy / scikit-learn / matplotlib promoted from transitive to declared with comments (the pyyaml precedent); `ipykernel` added; then `make lock` |
| `notebooks/fit_*.ipynb` | Five thin notebooks (below) — every computation is an import |
| `tests/physics/fits/test_*.py` | Test battery (below) |

`physics_params.yaml` schema (per circuit slug): `joint_pace.<era>` (t0_s, k_m_s_per_kg,
evolution_s_per_lap, trend_s_per_lap, identified, vif_fuel, condition_number,
sigma_driver_s, t_ref_s, s_ref_s, n_laps), `degradation.<era>` (compound_offsets_s +
per-compound a, b, n_laps, max_age_seen, low_confidence, source_circuit),
`hazards` (sc/vsc/red: n_races, n_with, p_per_race, Wilson band, lambda_per_lap),
`pit_loss` (mean_s, sigma_s, n_stops), `energy.<era>` (braking_energy_mj_per_lap,
full_throttle_s_per_lap, full_throttle_frac, median_cadence_hz, n_laps); plus
`globals` (k_m_pooled_s_per_kg, status_pace multipliers) and `clusters` (k, seed,
features, assignments). `generated_at` is injected, not clock-read, so renders are
byte-deterministic.

## Constants & configs

Every new number, its origin, and where it lives:

| Name | Value | Origin | Yaml |
|---|---|---|---|
| `sc_burn_factor` | 0.6 | stylised — reduced burn under SC/VSC; sensitivity shown in the joint-pace notebook | fits.yaml |
| `vif_max` | 30 | stylised — weak-identification threshold; above it the decomposition path runs | fits.yaml |
| `throttle_full_pct` | 98 | stylised — full-throttle threshold on the Throttle channel | fits.yaml |
| `deg_min_laps` | 30 | stylised — minimum sample for a trusted degradation fit | fits.yaml |
| `deg_min_stints` / `deg_min_drivers` | 3 / 2 | stylised — same gate | fits.yaml |
| `deg_min_max_age` | 12 | stylised — curve must be constrained past this age | fits.yaml |
| `deg_curve_bounds` | a∈[0,5], b∈[0.3,3] | stylised — curve_fit bounds keeping the power law physical | fits.yaml |
| `pit_duration_max_s` | 60 | stylised — excludes penalty/red-flag stops from pit-loss fits, counts reported | fits.yaml |
| `wilson_z` | 1.96 | sourced — 95% normal quantile | fits.yaml |
| `cluster_k_range` | [2, 6] | stylised — silhouette search range | fits.yaml |
| `cluster_seed` | 20260715 | stylised — determinism | fits.yaml |
| every fitted output | — | fitted: named notebook; 2026 joint-pace rows additionally carry the AR-10 grade-C note | physics_params.yaml |

No inline constants anywhere; all thresholds arrive at fitters as arguments.

## Tests first

`tests/physics/fits/`, mirroring the package; no network; crafted frames in the
`tests/data/conftest.py` style. Written and shown failing before implementation.

- `test_gate.py::test_raises_on_missing_season_report` — the mandated F-14 gate (tmp report dirs); `test_passes_when_all_reports_exist`
- `test_fuel.py` — total burn equals allowance; SC laps burn at `sc_burn_factor`; profile monotone decreasing; a clean race is exactly affine in lap_number
- `test_joint_pace.py::test_recovers_injected_coefficients` — mandated: seeded synthetic 57-lap 20-driver race with an SC window (laps 20–24), stint breaks, two compounds, injected a and b; recoverable *because* the SC creates a fuel step; a within ±20% relative, b within ±0.01 s/lap, `identified is True`
- `test_joint_pace.py::test_flags_unidentifiable_clean_race` — the honesty pin: no SC → `identified is False`, VIF above threshold, combined trend still recovered
- `test_joint_pace.py::test_compound_fixed_effects_recovered`, `::test_vif_and_condition_reported`, `::test_refuses_validation_rounds` (E-14 guard)
- `test_degradation.py::test_refuses_in_out_laps` — mandated E-09 guard; `::test_refuses_inaccurate_laps`; `::test_recovers_power_law` (seeded A·age^b + noise); `::test_low_confidence_below_minimums`
- `test_hazards.py` — Wilson band vs hand-computed values including 0/n; digit parsing ("12" is not SC; "4"→SC, "67"→VSC, "5"→red); status multipliers from crafted laps
- `test_pit_loss.py` — mean/sigma/n from crafted rows; outliers and null durations counted, never silent
- `test_energy.py` — irregular 4–5 Hz timestamps: full-throttle seconds equal a hand-summed value; braking ΔKE equals ½mΔv² by hand; a >2 s gap splits the trace and no time or energy crosses it (the cadence-aware pin, AR-16)
- `test_clusters.py` — deterministic assignment under fixed seed; transferred fits carry `low_confidence` + `source_circuit`; ratio-transfer arithmetic
- `test_params_writer.py` — `yaml.safe_load` round-trip equals values; every leaf line carries a legal origin comment; two renders byte-identical; `validate_complete` raises listing nulls

Property tests: none — the spec's property tests (100k action sequences) arrive with
F05; nothing in F02 is property-shaped, and hypothesis is deliberately not added yet.

## Edge cases handled

- **E-09** — frames.py pre-filters via the F01 cleaners *and* the degradation fitter
  independently refuses poisoned input; excluded-row counts reported per fit.
- **E-10** — the joint fit with compound fixed effects is the only pace fit; the
  identifiability divergence above is the honest implementation of its intent.
- **E-14** — fitters take `calibration_rounds` and raise on 2026 rounds ≥ 7.
- **E-05 (feeds)** — pit-loss mean/sigma/n per circuit are exactly the FIFO inputs.
- **Sprints (E-11 legacy)** — sprint sessions enter the joint fit via session fixed
  effects; excluded from per-race hazard counts (different exposure length).
- **Wet/red races** — excluded from dry fits via `Session.is_dry` (5.3.4), analysed
  separately in the notebooks.

## Acceptance checklist

- [ ] `physics_params.yaml` has no nulls among the F02-owned constants F05 lists, each with provenance (`validate_complete` enforces)
- [ ] Residual plots exist per fitted module (PNGs under `docs/fits/`, produced by the five notebooks)
- [ ] Collinearity numbers (VIF, condition number) reported per circuit-era in yaml and notebook
- [ ] Grade C rows still marked C — AR-10 flag propagated onto every 2026 joint-pace output, nothing silently promoted
- [ ] The three mandated tests green: coefficient recovery, in/out-lap refusal, F-14 gate
- [ ] `make fit` runs the full battery locally; `--only`/`--circuit` narrow it
- [ ] Fast test suite stays fast (energy integration runtime lives in the CLI run, not tests)

## Out of scope

- The eight T-transformations themselves (F03) — F02 produces real-era raw material
  (integrals, 2024/2026 fits); the 2026 conversions of them are F03's.
- c_lc, c_atk, p_der (physics_2026.yaml fitted block) — T4/F03 territory.
- Weather Markov chains and tyre-failure hazards — flagged as a gap for F03/F05 plans.
- Anything the env consumes beyond the yaml; circuit geometry (F04).
- OpenF1 intervals/race_control/weather endpoints — FastF1 race control suffices for
  hazards; widening OpenF1 coverage stays a config change if ever needed.

## Questions for Saad

1. **AR-10 (race fuel ~70 kg) is marked "VERIFY before F02"** — have you been able to
   check it against the FIA 2026 regs? *Proposed default: proceed with 70 kg at
   grade C; every 2026 value it touches carries the flag, and re-running `make fit`
   after you verify updates the yaml in one command.*
2. **The E-10 per-race → per-circuit pooling divergence** (flagged above) — accept?
   *Proposed default: yes; the per-race version is mathematically unidentifiable and
   the pooled version with session fixed effects is the standard fix, documented in
   the notebook.*
3. **The flagged extra constants** (status multipliers, t_ref/s_ref, sigma_driver,
   compound offsets) — include now so F05 finds them ready? *Proposed default: yes;
   they are by-products of fits already being run.*

## Verification

- `pytest tests/physics -q` — full battery green (after first being shown red).
- `make fit` end-to-end on the real DB: gate passes, fits run, `physics_params.yaml`
  materialises, `git diff` on a second run is empty (byte-determinism).
- `python -c "from senna import config; c=config.load('physics_params'); ..."` — spot
  read k_m for a circuit through the loader; a null among F02-owned keys raises.
- Execute the five notebooks top to bottom; PNGs appear under `docs/fits/`.
