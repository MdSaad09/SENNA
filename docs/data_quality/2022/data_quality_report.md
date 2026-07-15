# Data quality report — 2022

## Completeness

| Event | Session | Source | State | Reason |
|---|---|---|---|---|
| Bahrain Grand Prix | Race | fastf1 | loaded |  |
| Saudi Arabian Grand Prix | Race | fastf1 | loaded |  |
| Australian Grand Prix | Race | fastf1 | loaded |  |
| Emilia Romagna Grand Prix | Race | fastf1 | loaded |  |
| Emilia Romagna Grand Prix | Sprint | fastf1 | loaded |  |
| Miami Grand Prix | Race | fastf1 | loaded |  |
| Spanish Grand Prix | Race | fastf1 | loaded |  |
| Monaco Grand Prix | Race | fastf1 | loaded |  |
| Azerbaijan Grand Prix | Race | fastf1 | loaded |  |
| Canadian Grand Prix | Race | fastf1 | loaded |  |
| British Grand Prix | Race | fastf1 | loaded |  |
| Austrian Grand Prix | Race | fastf1 | loaded |  |
| Austrian Grand Prix | Sprint | fastf1 | loaded |  |
| French Grand Prix | Race | fastf1 | loaded |  |
| Hungarian Grand Prix | Race | fastf1 | loaded |  |
| Belgian Grand Prix | Race | fastf1 | loaded |  |
| Dutch Grand Prix | Race | fastf1 | loaded |  |
| Italian Grand Prix | Race | fastf1 | loaded |  |
| Singapore Grand Prix | Race | fastf1 | loaded |  |
| Japanese Grand Prix | Race | fastf1 | loaded |  |
| United States Grand Prix | Race | fastf1 | loaded |  |
| Mexico City Grand Prix | Race | fastf1 | loaded |  |
| São Paulo Grand Prix | Race | fastf1 | loaded |  |
| São Paulo Grand Prix | Sprint | fastf1 | loaded |  |
| Abu Dhabi Grand Prix | Race | fastf1 | loaded |  |

## Rows kept vs dropped per rule

Each rule is counted against every stored lap independently — the rows do
not chain, so the Dropped column must not be summed. The telemetry-gap,
position and wet/red rules run at fit time (F02); section 3 covers their
inputs.

| Rule | Rows in | Dropped | Flagged | Kept |
|---|---|---|---|---|
| is_accurate | 24882 | 4060 | 0 | 20822 |
| in_out_laps | 24882 | 1656 | 0 | 23226 |
| is_green | 24882 | 0 | 3549 | 24882 |
| lap_time_nat | 24882 | 0 | 588 | 24882 |

## Channels missing per session

- none

## Generation metadata

- generated_at: 2026-07-15T15:42:44+00:00
- season: 2022
- sessions covered: 25
