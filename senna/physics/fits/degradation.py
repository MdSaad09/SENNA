"""Tyre degradation: grip(age) = 1 - a * age^b, per compound (T5).

The fitter works on the joint fit's partial residuals (the age contribution
added back after session, driver, compound, fuel and evolution are removed),
so the power law is not double-counting what E-10 already explained. It
refuses poisoned input outright: an in/out or inaccurate lap in a degradation
dataset means the upstream filter failed, and fitting through it would turn a
cleaning bug into fake thermal runaway (E-09).

F24 added the identification honesty and the repair ladder. The a >= 0 bound
means flat residuals pin the optimiser at zero, and for years that clip was
stored as a measurement — 37 of 145 curves said "this tyre never wears" and
the trained policy found the exploit. A fit is now `identified` only when its
predicted delta over its own observed age range clears a noise floor; a clip
never is. Unidentified fits are repaired from the pooled per-compound refit
(more data than any one circuit) or, failing that, the other era's pooled
curve — and every substitution names its source, forever.
"""

from dataclasses import dataclass, replace

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
    # False means the data could not measure wear over the ages it covers — a
    # statement about the data, never a measurement of zero wear (E-10, F24)
    identified: bool


def fit_degradation(
    laps: pd.DataFrame,
    t0_s: float,
    *,
    bounds: tuple[list[float], list[float]],
    signal_floor_s: float,
    min_laps: int,
    min_stints: int,
    min_drivers: int,
    min_max_age: int,
    p0: list[float],
    maxfev: int,
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
            p0=p0,
            bounds=bounds,
            maxfev=maxfev,
        )
        thin = (
            len(compound_laps) < min_laps
            or compound_laps.groupby("driver")["stint"].nunique().sum() < min_stints
            or compound_laps["driver"].nunique() < min_drivers
            or age.max() < min_max_age
        )
        max_age = int(age.max())
        fits[str(compound)] = DegradationFit(
            a=float(amplitude_s) / t0_s,  # seconds of delta over t0 = fractional grip loss
            b=float(exponent),
            n_laps=len(compound_laps),
            max_age_seen=max_age,
            low_confidence=bool(thin),
            # a bound-clip lands at ~1e-10, not 0.0, so the test is the predicted
            # delta over the ages the data covers, never a == 0 — and a parameter
            # pinned at either bound is the optimiser refused, not a measurement,
            # whichever parameter it was (E-10)
            identified=(
                float(amplitude_s) * max_age ** float(exponent) >= signal_floor_s
                and not _pinned(float(exponent), bounds[0][1], bounds[1][1])
            ),
        )
    return fits


def _pinned(value: float, lo: float, hi: float, *, tol: float = 1e-6) -> bool:
    return abs(value - lo) <= tol or abs(value - hi) <= tol


def fit_pooled_degradation(
    frac_residuals: pd.DataFrame,
    *,
    bounds: tuple[list[float], list[float]],
    p0: list[float],
    maxfev: int,
    signal_floor_frac: float,
) -> dict[str, DegradationFit]:
    """One curve per compound over every circuit's residuals at once.

    Pooling works in fractional units (pace_residual_s / t0_s) so an 80 s lap
    and a 105 s lap weigh in honestly; the fitted `a` is then t0-free, which is
    what lets it stand in at any circuit. The thinness gates do not apply — the
    pool is never thin — so low_confidence stays False and the substitution
    marks itself instead, via the source the repair records.
    """
    fits = {}
    for compound, rows in frac_residuals.groupby("compound"):
        age = rows["tyre_life"].to_numpy(dtype=float)
        frac = rows["frac_residual"].to_numpy(dtype=float)
        (a, b), _ = curve_fit(
            lambda x, a_, b_: a_ * x**b_, age, frac, p0=p0, bounds=bounds, maxfev=maxfev
        )
        max_age = int(age.max())
        fits[str(compound)] = DegradationFit(
            a=float(a),
            b=float(b),
            n_laps=len(rows),
            max_age_seen=max_age,
            low_confidence=False,
            identified=(
                float(a) * max_age ** float(b) >= signal_floor_frac
                and not _pinned(float(b), bounds[0][1], bounds[1][1])
            ),
        )
    return fits


def repair_degradation(
    deg: dict, pooled_by_era: dict[str, dict[str, DegradationFit]]
) -> tuple[dict, dict]:
    """Substitute every unidentified circuit fit from the ladder: the era's own
    pooled curve first, the other era's second, nothing third — an unrepaired
    fit stays unidentified for the scenario backstop to refuse, never silently
    promoted to a curve. The circuit keeps its own n_laps and max_age_seen (the
    cliff is where *its* data ran out), takes only the borrowed shape, and the
    returned sources dict records exactly the substitutions and nothing else."""
    repaired = {}
    sources: dict[tuple[str, str, str], str] = {}
    for (slug, era), compounds in deg.items():
        out = dict(compounds)
        for compound, fit in compounds.items():
            if fit.identified:
                continue
            rung = pooled_curve_for(era, compound, pooled_by_era)
            if rung is None:
                continue
            source, donor = rung
            out[compound] = replace(fit, a=donor.a, b=donor.b, low_confidence=True)
            sources[(slug, era, compound)] = source
        repaired[(slug, era)] = out
    return repaired, sources


def pooled_curve_for(era: str, compound: str, pooled_by_era: dict):
    own = pooled_by_era.get(era, {}).get(compound)
    if own is not None and own.identified:
        return "pooled", own
    for other_era in sorted(pooled_by_era):
        if other_era == era:
            continue
        donor = pooled_by_era[other_era].get(compound)
        if donor is not None and donor.identified:
            return "prior_cross_era", donor
    return None


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
