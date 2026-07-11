# F01 — Data ingestion & quality reports

Depends on: F00
Spec anchors: 5.3 (all of it), E-09 to E-14, F-10, F-11, F-14, AR-14 to AR-16

## Goal
All usable 2022–2026 F1 data lands in Postgres once, cleanly, resumably, and with a
per-season quality report — the cleaning contract turned into code. No model may be
fitted until the reports exist (F-14).

## Deliverables
- senna/data/: FastF1 (>=3.7, on-disk cache, Jolpica-backed) session loader driven by the event schedule, sprint-aware (E-11); OpenF1 REST client, historical only, ~3 req/s throttle, 2023 onward (F-11)
- Resumable checkpoints per event; completeness assertion, expected vs loaded (E-12)
- The 5.3.4 cleaning contract as pure, unit-tested functions: IsAccurate filter, in/out-lap exclusion, TrackStatus digit parsing, NaT policy, telemetry gap splitting at 2 s, decimetre-to-metre, wet and red-flag exclusions
- Postgres schema + alembic migration including era/source flags and the simulated-energy columns (5.3.5)
- data_quality_report.md generator per season: events expected vs loaded, rows kept vs dropped per rule, channels missing per session
- The frozen calibration split — 2026 rounds 1–6 calibrate, 7+ held out — recorded in configs/data_split.yaml (E-14)

## Out of scope
Any fitting (F02), synthetic generation (F03), circuit geometry (F04).

## Constants & configs
- OpenF1 rate limit and backoff — sourced AR-15 — configs/ingest.yaml
- Calibration/validation round lists — sourced E-14, frozen now — configs/data_split.yaml

## Tests first
- Each cleaning rule against crafted fixtures: NaT in-lap, TrackStatus "4"/"6"/"5", sprint weekend names, truncated stint, missing channel
- Resumability: simulate a kill mid-ingest, rerun, no duplicates, completeness passes
- Throttle: the client never exceeds the configured request rate (fake clock)

## Done means
- Every expected 2022–2026 event loaded, or explicitly excluded with a written reason
- One data_quality_report.md per season, committed
- Reingest is idempotent; completeness assertions pass
- Zero code paths can reach ergast.com (grep-level guarantee, R-04)

## Notes for the plan session
Bulk ingest is hours of wall time. Build the resumable path first and let it run while
the cleaning-rule tests are being written. Jolpica is a free community service: cache
first, throttle always.
