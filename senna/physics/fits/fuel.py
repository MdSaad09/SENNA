"""Status-aware race fuel profiles (T6 groundwork).

Fuel mass is never observed; it is constructed. The burn profile is scaled so
the tank empties at the flag — total burn equals the race allowance (F-06/T6) —
with laps behind an SC, VSC or red flag burning at a reduced factor. That bend
in the line is what lets the E-10 fit separate fuel from track evolution; in a
clean race the profile stays exactly affine in lap_number and the fitter must
flag the attribution as unidentifiable rather than invent it.
"""

import pandas as pd

INTERVENTION_DIGITS = set("4567")  # FastF1 TrackStatus: SC=4, red=5, VSC=6, VSC ending=7


def fuel_profile(laps: pd.DataFrame, race_fuel_kg: float, sc_burn_factor: float) -> pd.Series:
    """Fuel remaining (kg) at the start of each lap of one driver's race."""
    ordered = laps.sort_values("lap_number")
    slowed = ordered["track_status"].map(
        lambda status: bool(INTERVENTION_DIGITS & set(str(status)))
    )
    burn_weights = slowed.map({True: sc_burn_factor, False: 1.0})
    kg_per_weight = race_fuel_kg / burn_weights.sum()
    burned_before_kg = kg_per_weight * burn_weights.cumsum().shift(1, fill_value=0.0)
    return (race_fuel_kg - burned_before_kg).reindex(laps.index).rename("fuel_kg")


def session_fuel(laps: pd.DataFrame, race_fuel_kg: float, sc_burn_factor: float) -> pd.Series:
    """Profiles for a multi-session circuit frame, per (session, driver).

    Every session's allowance scales with its lap count against the circuit's
    longest race, so kg-per-lap comes out the same everywhere. That is the
    right construction for sprints (T6) and, deliberately, for red-flag
    shortened races too: a stopped race still burned normal kg-per-lap while
    it ran, and the fuel *level* error this leaves is absorbed by the joint
    fit's session fixed effects — only the slope reaches the estimate."""
    session_laps = laps.groupby("session_id")["lap_number"].max()
    longest_race = float(session_laps.max())
    parts = []
    for (session_id, _), group in laps.groupby(["session_id", "driver"]):
        allowance_kg = race_fuel_kg * float(session_laps[session_id]) / longest_race
        parts.append(fuel_profile(group, allowance_kg, sc_burn_factor))
    return pd.concat(parts).reindex(laps.index)
