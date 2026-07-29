# Frozen data snapshot (A-09)

Written by `make snapshot` (senna/data/snapshot.py). The dump itself is
gitignored and rides the tagged GitHub release as an asset; this manifest is
the committed half — verify a downloaded dump with `shasum -a 256` against
the digest below, then `make restore` into a `*_test` database.

| | |
|---|---|
| Dump | `senna-20260729.dump` |
| sha256 | `be306e264e83b2abce53f703b6c93e1df57236df48d61ca348c063912661a59a` |
| Size (bytes) | 13223686 (13.2 MB) |

| Table | Rows |
|---|---|
| agent_decisions | 29018 |
| alembic_version | 1 |
| events | 103 |
| ingest_checkpoints | 231 |
| lap_frames | 912 |
| laps | 123708 |
| openf1_pit_stops | 2908 |
| openf1_stints | 5244 |
| race_control | 11322 |
| results | 2588 |
| sessions | 128 |
| simulation_runs | 486 |
| weather | 18852 |
