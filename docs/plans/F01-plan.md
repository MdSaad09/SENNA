# F01 — Data ingestion & quality reports: plan

## Context

F00 (repo skeleton, CI, spec split) is Done; F01 is next and unblocked. The goal is the
cleaning contract turned into code: all usable 2022–2026 F1 data lands in Postgres once,
cleanly, resumably, with a per-season quality report. F02 may not fit anything until the
reports exist (F-14). The repo today has no `senna/data/`, no config loader, no alembic,
and no ergast grep guard — F01 creates all of them.

**Spec-conflict check:** `docs/spec/5.3-data-pipeline.md` matches the source PDF exactly
(verified page-by-page). Three places where the spec is silent and this plan decides:
(1) the v2 base DB schema ("Section 8.3") is referenced but not reproduced in v3 and the
v2 doc isn't in the repo — the base schema below is derived from the columns 5.3.2/5.3.3
say we consume, plus the 5.3.5 deltas; (2) no checkpoint/resume design exists in the
spec — designed here; (3) the spec mandates throttle/backoff but gives only "~3 req/s"
(AR-15) — backoff numbers are stylised config.

## Objective & spec anchors

Rows that shaped the design:

- **F-10 / R-04** — Ergast is dead; Jolpica via fastf1>=3.7; bulk ingest once, store in
  Postgres, never query live. Drives the grep-level ergast guard and the cache-first loader.
- **F-11** — OpenF1 historical only, 2023+, ~3 req/s free tier. Drives the client's
  first-season guard and the token-bucket throttle.
- **F-14** — FastF1 quirks (NaT laps, IsAccurate, TrackStatus digit strings, sprint
  naming, truncated stints, missing channels) become the explicit cleaning contract +
  per-season quality report gate.
- **E-09** — in/out and inaccurate laps poison tyre fits → flag, never destroy: the DB
  stores the flagged superset; fits filter at query time.
- **E-11** — sprint weekends: ingest by session type from the event schedule's
  `EventFormat`/Session columns, never a fixed FP1–R name list.
- **E-12** — rate limits mid-bulk-ingest: on-disk cache, client throttle, resumable
  per-session checkpoints, completeness assertion before modelling.
- **E-13** — Madrid has no data until September: expected events = schedule rows whose
  date has passed, so completeness never lies about the future.
- **E-14** — calibration split frozen now: 2026 rounds 1–6 calibrate, 7+ held out,
  recorded in `configs/data_split.yaml` with the freeze date.
- **AR-14/15/16** — Jolpica interface, OpenF1 tier limits, 4–5 Hz telemetry cadence.

## Deliverables

New files:

- `senna/config.py` — the one config loader (senna/CLAUDE.md mandate): `load(name)`
  reads `configs/<name>.yaml`; reading a `null` constant raises `NullConstantError`.
  Stdlib + PyYAML only, so the future env hot loop can import it safely.
- `senna/data/__init__.py` — public ingest surface; imports nothing heavy.
- `senna/data/schema.py` — SQLAlchemy 2.0 declarative models (`Mapped`/`mapped_column`);
  imports sqlalchemy only.
- `senna/data/db.py` — async engine + session factory from `DATABASE_URL`; the only
  file that knows asyncpg exists.
- `senna/data/throttle.py` — `TokenBucket(rate, burst, clock, sleep)`; pure logic,
  injectable clock for tests.
- `senna/data/openf1.py` — sync httpx client: session-key mapping, `/pit`, `/stints`;
  raises on year < first_season (F-11); retry with exponential backoff on 429/5xx.
- `senna/data/fastf1_loader.py` — the only file importing fastf1: enables the on-disk
  cache before any call, iterates `get_event_schedule(year, include_testing=False)`,
  loads the configured session types per event (E-11), probes which telemetry channels
  each session has.
- `senna/data/cleaning.py` — the 5.3.4 contract as pure functions, each returning
  `(DataFrame, DropCount)`: IsAccurate filter, in/out-lap exclusion, TrackStatus digit
  parsing (green = whole lap status "1"), NaT policy (never impute for fits; impute +
  flag only for replay), telemetry gap split at 2 s, decimetre→metre + OnTrack filter +
  z-score speed gate, wet/red-flag race exclusion.
- `senna/data/quality.py` — `DropCount`/`SessionQuality` dataclasses; markdown renderer;
  `report_path(season)` — the function F02's refuse-to-fit gate will call.
- `senna/data/checkpoints.py` — checkpoint read/write + `assert_complete` (E-12/E-13).
- `senna/data/ingest.py` — orchestrator + CLI (`python -m senna.data.ingest --seasons
  … --source {fastf1,openf1,all} --report-only`); one `asyncio.run()` at the top.
- `migrations/` + `alembic.ini` — alembic async template, one initial revision.
- `configs/ingest.yaml`, `configs/data_split.yaml` — see constants table.
- `tests/data/` (conftest + one test file per module), `tests/config/test_config.py`,
  ergast-guard test in `tests/docs/` (clones the `test_old_name_absent_from_prose`
  runtime-assembled-needle pattern from `tests/docs/test_spec_anchors.py`).
- `.env.example` — `DATABASE_URL` for the compose Postgres.

Modified:

- `Makefile` — `make ingest` becomes real; add `make migrate` (`alembic upgrade head`).
- `.github/workflows/ci.yml` — add a `postgres:16-alpine` service container so the
  resumability/idempotency tests run against real transactions.
- `requirements.in` — promote `pyyaml` to a direct dep (config loader imports it;
  already locked at 6.0.3 transitively), then `make lock`.
- `docs/data_quality/<season>/data_quality_report.md` — generated per season, committed
  after the bulk run.

Key design decisions (the why, briefly):

- **Store the flagged superset, never a cleaned subset.** 5.3.4 keeps in/out laps for
  pit timing and SC laps for event-rate fits, so ingest stores raw rows + derived flags
  (`is_green`, `lap_time_imputed`); F02 filters at query time with the same pure functions.
- **Async everywhere, no second driver.** The stack pins asyncpg only; alembic uses its
  async template; bulk inserts are SQLAlchemy Core `insert(...)` executemany over
  `df.to_dict("records")` — never `pandas.to_sql`. All async confined to `db.py`,
  `checkpoints.py`, and the write step.
- **Idempotency = delete-and-reload per (session, source) in one transaction**, not
  upsert — race_control has no natural key, and all-or-nothing per session is what makes
  resume safe.
- **Checkpoints: one row per (season, round, source, session_name)**, states
  `pending → loaded | failed | excluded(reason)`. The flip to `loaded` commits in the
  same transaction as the rows, so a kill mid-write rolls both back — no `in_progress`
  state needed. Rerun skips `loaded`, retries the rest; the FastF1 cache makes retries
  cheap.
- **Completeness (E-12/E-13):** expected = schedule rows (testing excluded) with past
  dates; OpenF1 additionally season ≥ 2023. Every expected (event, source, session) must
  be `loaded` or `excluded` with a written reason, or `assert_complete` raises.
- **Raw telemetry/position traces are not stored in Postgres** — the FastF1 on-disk
  cache is the telemetry store; F02 reads it through `fastf1_loader` accessors. The
  quality report covers channel presence per session.

### Base schema (initial alembic revision)

| Table | Key columns | Unique constraint |
|---|---|---|
| events | season, round, event_name, event_format, event_date | (season, round) |
| sessions | event_id FK, session_name, session_type, date_utc, openf1_session_key/meeting_key (nullable), missing_channels JSONB | (event_id, session_name) |
| laps | session_id FK, driver, driver_number, team, lap_number, stint, compound, tyre_life, fresh_tyre, lap_time_s (nullable — NaT stays null), lap_time_imputed, sector1/2/3_s, speed_st, position, track_status, is_accurate, is_green, pit_in/out_time_s, lap_start_time_s, **era**, **source** (real_2022…real_2026 / synthetic_2026), **energy_deployed_mj / energy_harvested_mj / soc_end_mj** (nullable, simulated rows only — 5.3.5) | (session_id, driver_number, lap_number, source) |
| weather | session_id, time_s, air_temp, track_temp, humidity, rainfall, wind_speed | (session_id, time_s) |
| race_control | session_id, time_s, category, flag, status, message, lap | surrogate PK; idempotency via delete-and-reload |
| results | session_id, driver_abbrev, team_name, grid_position, position, status, points | (session_id, driver_abbrev) |
| openf1_pit_stops | session_id, driver_number, lap_number, pit_duration_s | (session_id, driver_number, lap_number) |
| openf1_stints | session_id, driver_number, stint_number, compound, lap_start, lap_end, tyre_age_at_start | (session_id, driver_number, stint_number) |
| simulation_runs | id, created_at, env_config_hash, model_version, config JSONB (minimal now — 5.3.5/E-15) | — |
| agent_decisions | id, run_id FK, lap_number, decision JSONB (one row per decision — 5.3.5) | — |
| ingest_checkpoints | season, round, source, session_name, state, rows_loaded, error, excluded_reason, updated_at | (season, round, source, session_name) |

## Constants & configs

`configs/ingest.yaml` (new):

| Key | Value | Origin |
|---|---|---|
| seasons | [2022, 2023, 2024, 2025, 2026] | sourced 5.3.1 — coverage window |
| fastf1.cache_dir | data/cache/fastf1 | stylised — local path, already gitignored under data/cache/ |
| fastf1.sessions_to_ingest | [Race, Sprint] | stylised — what the 5.3.2 feeds consume; widen in yaml, never code (E-11) |
| openf1.base_url | https://api.openf1.org/v1 | sourced 5.3.3 |
| openf1.first_season | 2023 | sourced F-11 / AR-15 — no 2022 coverage |
| openf1.endpoints | [pit, stints] | stylised — intervals/race_control/weather cross-checks deferred |
| openf1.rate_limit_rps | 3.0 | sourced AR-15 — free tier ~3 req/s |
| openf1.burst | 3 | stylised — token-bucket capacity |
| openf1.max_retries | 5 | stylised — bulk-ingest patience on 429/5xx |
| openf1.backoff_base_s / factor / cap_s | 1.0 / 2.0 / 60.0 | stylised — spec mandates backoff, gives no numbers |
| cleaning.telemetry_gap_split_s | 2.0 | sourced 5.3.4 |
| cleaning.pos_speed_zscore_max | 4.0 | stylised — 5.3.4 mandates the gate but gives no threshold |
| quality.report_dir | docs/data_quality | stylised — committed location; F02's gate reads it |

`configs/data_split.yaml` (new):

| Key | Value | Origin |
|---|---|---|
| season | 2026 | sourced E-14 |
| calibration_rounds | [1, 2, 3, 4, 5, 6] | sourced E-14 — frozen |
| validation_rounds_from | 7 | sourced E-14 — rounds 7+ and all future rounds held out |
| frozen_on | "2026-07-14" | sourced E-14 — the split date the spec requires recording |

## Tests first

`tests/data/conftest.py` builds small hand-crafted frames with FastF1's exact column
names (no network anywhere):

- `test_cleaning.py`
  - `test_isaccurate_false_dropped_and_counted` — IsAccurate filter returns the frame
    minus flagged rows and a DropCount matching (E-09).
  - `test_in_out_laps_excluded_from_fits_kept_for_pit_timing` — PitIn/PitOutTime rows
    leave the pace frame, remain in the pit-timing frame (E-09).
  - `test_track_status_green_only_if_whole_lap_status_1` — "1" green; "4" (SC), "6"
    (VSC), "5" (red), and mixed strings like "12" all non-green.
  - `test_nat_laptime_never_imputed_for_fits` / `test_nat_imputed_and_flagged_for_replay`.
  - `test_telemetry_gap_over_2s_splits_trace` — no interpolation across the gap; the
    threshold comes from config, not a literal.
  - `test_pos_data_decimetres_to_metres_offtrack_dropped_outlier_gated`.
  - `test_wet_and_red_flag_races_excluded_from_dry_set`.
  - `test_missing_channel_recorded_not_fatal` — a session without, say, car data still
    ingests; the gap lands in `missing_channels`.
- `test_fastf1_loader.py` — `test_sprint_weekend_sessions_from_schedule_not_name_list`
  (2023 "Sprint Shootout" vs 2024+ "Sprint Qualifying" naming never crashes the plan;
  E-11); `test_truncated_stint_survives_cleaning`.
- `test_throttle.py` — `test_client_never_exceeds_configured_rate` with a fake clock
  recording request timestamps; `test_burst_then_steady_state`.
- `test_openf1.py` — `test_year_before_first_season_raises` (F-11);
  `test_429_backs_off_and_retries` via `httpx.MockTransport`.
- `test_ingest_resume.py` (needs Postgres; `skipif` no `DATABASE_URL`) —
  `test_kill_mid_ingest_then_rerun_no_duplicates`: fake loader raises after N sessions,
  rerun completes, row counts equal a clean single run, unique constraints unviolated,
  `assert_complete` passes (E-12).
  `test_completeness_ignores_future_events` — an unraced future event (Madrid, E-13)
  does not fail the assertion; a past unloaded one does.
- `test_quality.py` — report renders all four sections; per-rule drop counts match the
  DropCounts fed in; `report_path(season)` resolves inside `quality.report_dir`.
- `tests/config/test_config.py` — loader reads yaml; `null` constant raises (the
  anti-black-box contract).
- `tests/docs/test_no_ergast.py` — runtime-assembled needle "erg"+"ast" scanned over
  `git ls-files` output restricted to code dirs (senna/ api/ worker/ scripts/ configs/
  tests/ notebooks/); docs/spec excluded because the feature spec itself names the dead
  service (R-04).

Property tests: none — the spec's property tests (E-01, E-05) first arrive with F05;
nothing in F01 is property-shaped. Called out so the absence is a decision, not a gap.

## Edge cases handled

- **E-09** — in/out + inaccurate laps flagged and excluded from fit views; counts in the
  report per rule.
- **E-10** — not F01's fit, but the schema keeps lap_number, fuel-relevant timing and
  compound columns raw so the joint fit is possible.
- **E-11** — session list comes from the schedule row intersected with configured
  types; sprint naming differences are data, not code.
- **E-12** — cache-first loader, 3 req/s token bucket, per-session checkpoints,
  delete-and-reload transactions, `assert_complete` before any modelling.
- **E-13** — expected = past events only; Madrid auto-appears when its first session is
  ingested in September.
- **E-14** — split frozen in `configs/data_split.yaml` with the freeze date; nothing in
  F01 reads 2026 rounds 7+ for anything but storage.

## Acceptance checklist (from the feature spec's "done means")

- [ ] Every expected 2022–2026 event loaded, or explicitly excluded with a written
      reason (checkpoint state `excluded` + reason, surfaced in the report)
- [ ] One data_quality_report.md per season, committed
- [ ] Reingest is idempotent; completeness assertions pass
- [ ] Zero code paths can reach ergast.com — grep-level guarantee enforced by
      `test_no_ergast.py` in CI (R-04)

## Out of scope (deliberately)

- Any fitting (F02) — but `quality.report_path()` is the hook F02's gate will call.
- Synthetic generation (F03), circuit geometry / `get_circuit_info` (F04).
- Raw telemetry/pos-trace storage in Postgres — the FastF1 cache is the telemetry
  store; a summary table is F02's call if the fits want one.
- OpenF1 intervals / race_control / weather endpoints — cross-checks land with the fits
  that consume them; the client + config make adding an endpoint a yaml edit.
- Full simulation_runs / agent_decisions column sets — created minimal per 5.3.5 so the
  initial migration owns the tables; later features migrate.

## Sequencing note (from the feature spec)

Bulk ingest is hours of wall time. Build order inside /ship: config loader → schema +
migration → checkpoints + orchestrator skeleton → kick off the real bulk ingest locally
in the background → cleaning functions + quality report while it runs → reports
generated and committed once ingest completes.

## Decisions (Saad, 14 Jul 2026, at plan approval)

1. **Base schema:** Saad has the v2 document but wants the build to follow v3 alone, so
   the schema above stands — derived from the columns 5.3.2/5.3.3 consume plus the
   5.3.5 deltas. The v2 Section 8.3 schema is deliberately not consulted.
2. **Session types: Race + Sprint, no practice, no quali.** No F02 fit consumes
   qualifying laps, and F04's ribbon (one clean fast lap per circuit) reads through the
   cache-first loader and can fetch a single quali session on demand when it needs one.
   Widening the list later is a yaml edit; the checkpoint design makes the rerun
   incremental — only the newly configured sessions ingest.
