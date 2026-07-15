"""Per-circuit event hazards: SC, VSC and red-flag rates with honest bands.

Rates are per-race Bernoulli (the 5.4.1 validation target is phrased that
way); the band is the Wilson score interval, which stays usable at 0-of-n and
at the five-or-so races a circuit gives us — wide bands being the honest
answer at that sample size. VSC and SC are classified separately throughout:
collapsing them prices VSC pit windows like SC windows (E-03).
"""

import math

import pandas as pd

STATUS_EVENTS = {"4": "sc", "5": "red", "6": "vsc", "7": "vsc"}  # FastF1 TrackStatus digits


def classify_track_status(track_status: str) -> set[str]:
    """"12" is the digits 1 and 2 — green then yellow, never SC (5.3.4)."""
    return {STATUS_EVENTS[d] for d in str(track_status) if d in STATUS_EVENTS}


def wilson_band(n_with: int, n_races: int, z: float) -> tuple[float, float]:
    p = n_with / n_races
    scale = 1.0 + z**2 / n_races
    centre = (p + z**2 / (2 * n_races)) / scale
    half = z * math.sqrt(p * (1 - p) / n_races + z**2 / (4 * n_races**2)) / scale
    return max(0.0, centre - half), min(1.0, centre + half)


def per_race_events(laps: pd.DataFrame) -> pd.DataFrame:
    """One row per race: did each event type appear on any lap."""
    events = laps["track_status"].map(classify_track_status)
    flags = pd.DataFrame(
        {kind: events.map(lambda kinds, k=kind: k in kinds) for kind in ("sc", "vsc", "red")},
        index=laps.index,
    )
    return flags.groupby(laps["session_id"]).any()


def per_lap_hazard(p_per_race: float, race_laps: float) -> float:
    """The constant per-lap hazard that reproduces the per-race probability (5.5.3)."""
    if p_per_race >= 1.0:
        return 1.0
    return -math.log(1.0 - p_per_race) / race_laps


def status_multipliers(laps: pd.DataFrame) -> dict[str, float]:
    """SC and VSC lap-time multipliers vs the green median (5.5.3 status_mult)."""
    timed = laps[laps["lap_time_s"].notna()]
    green_median_s = timed.loc[timed["is_green"], "lap_time_s"].median()
    events = timed["track_status"].map(classify_track_status)
    return {
        kind: float(timed.loc[events.map(lambda kinds, k=kind: k in kinds), "lap_time_s"].median()
                    / green_median_s)
        for kind in ("sc", "vsc")
    }
