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

## Rows kept vs dropped per rule

Each rule is counted against every stored lap independently — the rows do
not chain, so the Dropped column must not be summed. The telemetry-gap,
position and wet/red rules run at fit time (F02); section 3 covers their
inputs.

| Rule | Rows in | Dropped | Flagged | Kept |
|---|---|---|---|---|
| is_accurate | 12064 | 1898 | 0 | 10166 |
| in_out_laps | 12064 | 778 | 0 | 11286 |
| is_green | 12064 | 0 | 1663 | 12064 |
| lap_time_nat | 12064 | 0 | 218 | 12064 |

## Channels missing per session

- none

## Generation metadata

- generated_at: 2026-07-15T15:42:44+00:00
- season: 2026
- sessions covered: 26
