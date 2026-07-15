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
