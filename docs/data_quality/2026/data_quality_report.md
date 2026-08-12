# Data quality report — 2026

## Completeness

| Event | Session | Source | State | Reason |
|---|---|---|---|---|
| Australian Grand Prix | Race | fastf1 | loaded |  |
| Australian Grand Prix | Race | openf1 | loaded |  |
| Chinese Grand Prix | Race | fastf1 | loaded |  |
| Chinese Grand Prix | Sprint | fastf1 | loaded |  |
| Chinese Grand Prix | Race | openf1 | loaded |  |
| Chinese Grand Prix | Sprint | openf1 | loaded |  |
| Japanese Grand Prix | Race | fastf1 | loaded |  |
| Japanese Grand Prix | Race | openf1 | loaded |  |
| Miami Grand Prix | Race | fastf1 | loaded |  |
| Miami Grand Prix | Sprint | fastf1 | loaded |  |
| Miami Grand Prix | Race | openf1 | loaded |  |
| Miami Grand Prix | Sprint | openf1 | loaded |  |
| Canadian Grand Prix | Race | fastf1 | loaded |  |
| Canadian Grand Prix | Sprint | fastf1 | loaded |  |
| Canadian Grand Prix | Race | openf1 | loaded |  |
| Canadian Grand Prix | Sprint | openf1 | loaded |  |
| Monaco Grand Prix | Race | fastf1 | loaded |  |
| Monaco Grand Prix | Race | openf1 | loaded |  |
| Barcelona Grand Prix | Race | fastf1 | loaded |  |
| Barcelona Grand Prix | Race | openf1 | loaded |  |
| Austrian Grand Prix | Race | fastf1 | loaded |  |
| Austrian Grand Prix | Race | openf1 | loaded |  |
| British Grand Prix | Race | fastf1 | loaded |  |
| British Grand Prix | Sprint | fastf1 | loaded |  |
| British Grand Prix | Race | openf1 | loaded |  |
| British Grand Prix | Sprint | openf1 | loaded |  |
| Belgian Grand Prix | Race | fastf1 | loaded |  |
| Belgian Grand Prix | Race | openf1 | loaded |  |
| Hungarian Grand Prix | Race | fastf1 | loaded |  |
| Hungarian Grand Prix | Race | openf1 | loaded |  |

## Rows kept vs dropped per rule

Each rule is counted against every stored lap independently — the rows do
not chain, so the Dropped column must not be summed. The telemetry-gap,
position and wet/red rules run at fit time (F02); section 3 covers their
inputs.

| Rule | Rows in | Dropped | Flagged | Kept |
|---|---|---|---|---|
| is_accurate | 14367 | 2203 | 0 | 12164 |
| in_out_laps | 14367 | 927 | 0 | 13440 |
| is_green | 14367 | 0 | 1911 | 14367 |
| lap_time_nat | 14367 | 0 | 304 | 14367 |
| no_tyre_age | 14367 | 46 | 0 | 14321 |

## Channels missing per session

- none

## Generation metadata

- generated_at: 2026-08-11T18:41:50+00:00
- season: 2026
- sessions covered: 30
