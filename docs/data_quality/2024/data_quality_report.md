# Data quality report — 2024

## Completeness

| Event | Session | Source | State | Reason |
|---|---|---|---|---|
| Bahrain Grand Prix | Race | fastf1 | loaded |  |
| Bahrain Grand Prix | Race | openf1 | loaded |  |
| Saudi Arabian Grand Prix | Race | fastf1 | loaded |  |
| Saudi Arabian Grand Prix | Race | openf1 | loaded |  |
| Australian Grand Prix | Race | fastf1 | loaded |  |
| Australian Grand Prix | Race | openf1 | loaded |  |
| Japanese Grand Prix | Race | fastf1 | loaded |  |
| Japanese Grand Prix | Race | openf1 | loaded |  |
| Chinese Grand Prix | Race | fastf1 | loaded |  |
| Chinese Grand Prix | Sprint | fastf1 | loaded |  |
| Chinese Grand Prix | Race | openf1 | loaded |  |
| Chinese Grand Prix | Sprint | openf1 | loaded |  |
| Miami Grand Prix | Race | fastf1 | loaded |  |
| Miami Grand Prix | Sprint | fastf1 | loaded |  |
| Miami Grand Prix | Race | openf1 | loaded |  |
| Miami Grand Prix | Sprint | openf1 | loaded |  |
| Emilia Romagna Grand Prix | Race | fastf1 | loaded |  |
| Emilia Romagna Grand Prix | Race | openf1 | loaded |  |
| Monaco Grand Prix | Race | fastf1 | loaded |  |
| Monaco Grand Prix | Race | openf1 | loaded |  |
| Canadian Grand Prix | Race | fastf1 | loaded |  |
| Canadian Grand Prix | Race | openf1 | loaded |  |
| Spanish Grand Prix | Race | fastf1 | loaded |  |
| Spanish Grand Prix | Race | openf1 | loaded |  |
| Austrian Grand Prix | Race | fastf1 | loaded |  |
| Austrian Grand Prix | Sprint | fastf1 | loaded |  |
| Austrian Grand Prix | Race | openf1 | loaded |  |
| Austrian Grand Prix | Sprint | openf1 | loaded |  |
| British Grand Prix | Race | fastf1 | loaded |  |
| British Grand Prix | Race | openf1 | loaded |  |
| Hungarian Grand Prix | Race | fastf1 | loaded |  |
| Hungarian Grand Prix | Race | openf1 | loaded |  |
| Belgian Grand Prix | Race | fastf1 | loaded |  |
| Belgian Grand Prix | Race | openf1 | loaded |  |
| Dutch Grand Prix | Race | fastf1 | loaded |  |
| Dutch Grand Prix | Race | openf1 | loaded |  |
| Italian Grand Prix | Race | fastf1 | loaded |  |
| Italian Grand Prix | Race | openf1 | loaded |  |
| Azerbaijan Grand Prix | Race | fastf1 | loaded |  |
| Azerbaijan Grand Prix | Race | openf1 | loaded |  |
| Singapore Grand Prix | Race | fastf1 | loaded |  |
| Singapore Grand Prix | Race | openf1 | loaded |  |
| United States Grand Prix | Race | fastf1 | loaded |  |
| United States Grand Prix | Sprint | fastf1 | loaded |  |
| United States Grand Prix | Race | openf1 | loaded |  |
| United States Grand Prix | Sprint | openf1 | loaded |  |
| Mexico City Grand Prix | Race | fastf1 | loaded |  |
| Mexico City Grand Prix | Race | openf1 | loaded |  |
| São Paulo Grand Prix | Race | fastf1 | loaded |  |
| São Paulo Grand Prix | Sprint | fastf1 | loaded |  |
| São Paulo Grand Prix | Race | openf1 | loaded |  |
| São Paulo Grand Prix | Sprint | openf1 | loaded |  |
| Las Vegas Grand Prix | Race | fastf1 | loaded |  |
| Las Vegas Grand Prix | Race | openf1 | loaded |  |
| Qatar Grand Prix | Race | fastf1 | loaded |  |
| Qatar Grand Prix | Sprint | fastf1 | loaded |  |
| Qatar Grand Prix | Race | openf1 | loaded |  |
| Qatar Grand Prix | Sprint | openf1 | loaded |  |
| Abu Dhabi Grand Prix | Race | fastf1 | loaded |  |
| Abu Dhabi Grand Prix | Race | openf1 | loaded |  |

## Rows kept vs dropped per rule

Each rule is counted against every stored lap independently — the rows do
not chain, so the Dropped column must not be summed. The telemetry-gap,
position and wet/red rules run at fit time (F02); section 3 covers their
inputs.

| Rule | Rows in | Dropped | Flagged | Kept |
|---|---|---|---|---|
| is_accurate | 29023 | 3259 | 0 | 25764 |
| in_out_laps | 29023 | 1721 | 0 | 27302 |
| is_green | 29023 | 0 | 2143 | 29023 |
| lap_time_nat | 29023 | 0 | 386 | 29023 |

## Channels missing per session

- none

## Generation metadata

- generated_at: 2026-07-15T15:42:44+00:00
- season: 2024
- sessions covered: 60
