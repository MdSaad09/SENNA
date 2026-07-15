"""Tyre degradation: grip(age) = 1 - a * age^b, per compound (T5).

The fitter works on the joint fit's partial residuals (the age contribution
added back after session, driver, compound, fuel and evolution are removed),
so the power law is not double-counting what E-10 already explained. It
refuses poisoned input outright: an in/out or inaccurate lap in a degradation
dataset means the upstream filter failed, and fitting through it would turn a
cleaning bug into fake thermal runaway (E-09).
"""

from dataclasses import dataclass

import pandas as pd
from scipy.optimize import curve_fit


class InOutLapError(ValueError):
    pass


class InaccurateLapError(ValueError):
    pass


@dataclass(frozen=True)
class DegradationFit:
    a: float  # grip loss per age^b, as a fraction of t0 (grip(age) = 1 - a*age^b)
    b: float
    n_laps: int
    max_age_seen: int
    low_confidence: bool


def fit_degradation(
    laps: pd.DataFrame,
    t0_s: float,
    *,
    bounds: tuple[list[float], list[float]],
    min_laps: int,
    min_stints: int,
    min_drivers: int,
    min_max_age: int,
) -> dict[str, DegradationFit]:
    _refuse_poisoned(laps)
    fits = {}
    for compound, compound_laps in laps.groupby("compound"):
        age = compound_laps["tyre_life"].to_numpy(dtype=float)
        residual_s = compound_laps["pace_residual_s"].to_numpy(dtype=float)
        (amplitude_s, exponent), _ = curve_fit(
            lambda x, amplitude, exponent: amplitude * x**exponent,
            age,
            residual_s,
            p0=[max(bounds[0][0], 0.05), 1.2],
            bounds=bounds,
            maxfev=10_000,
        )
        thin = (
            len(compound_laps) < min_laps
            or compound_laps.groupby("driver")["stint"].nunique().sum() < min_stints
            or compound_laps["driver"].nunique() < min_drivers
            or age.max() < min_max_age
        )
        fits[str(compound)] = DegradationFit(
            a=float(amplitude_s) / t0_s,  # seconds of delta over t0 = fractional grip loss
            b=float(exponent),
            n_laps=len(compound_laps),
            max_age_seen=int(age.max()),
            low_confidence=bool(thin),
        )
    return fits


def _refuse_poisoned(laps: pd.DataFrame) -> None:
    in_or_out = laps["pit_in_time_s"].notna() | laps["pit_out_time_s"].notna()
    if in_or_out.any():
        raise InOutLapError(
            f"{int(in_or_out.sum())} in/out lap(s) reached the degradation fitter — "
            "they inflate stint-end deltas into a fake cliff; filter upstream (E-09)"
        )
    inaccurate = ~laps["is_accurate"].astype(bool)
    if inaccurate.any():
        raise InaccurateLapError(
            f"{int(inaccurate.sum())} inaccurate lap(s) reached the degradation "
            "fitter; filter upstream (E-09)"
        )
