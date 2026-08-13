"""Per-driver tyre style: one multiplier on the pooled degradation amplitude (F17, T5).

`degradation.py` refuses a per-driver *curve* for a real statistical reason — one driver's
stints cannot identify a power law. What is estimable is a single number per driver: how
fast they wear a set relative to the curve everyone shares. The partial residuals already
have that driver's mean pace removed (the joint fit's design carries driver dummies), so
what is left is the age contribution plus noise, and the multiplier is the least-squares
slope of that residual on the degradation the pooled curve predicts for the same lap.

Regressing on the *prediction* rather than on age is what lets one number pool across
circuits and compounds whose `a` and `b` differ by an order of magnitude. An age-by-driver
interaction would be fitting a different quantity at every circuit and calling it one.

Two properties of the published table are load-bearing:

- the multipliers are normalised to a lap-weighted mean of 1.0, because the pooled `a` was
  fitted on all drivers at once. Without it, naming a full grid would move every stint
  length in the race rather than redistributing wear between seats.
- a driver the design cannot pin down is published as 1.0 and flagged, never as a noisy
  coefficient wearing a `fitted` tag. That is E-10's discipline one layer down, and here
  the instrument is a stint-clustered standard error rather than a VIF.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from senna.env.dynamics import tyre_deg_s
from senna.physics.fits.degradation import DegradationFit


@dataclass(frozen=True)
class DegStyleFit:
    mult: float       # multiplier on the pooled amplitude; 1.0 means "wears it like the field"
    se: float         # stint-clustered, and on the same scale as the published mult
    rel_se: float     # se / mult of the raw estimate — scale-free, so the gate reads it
    n_stints: int
    n_laps: int
    identified: bool


def deg_prediction_s(
    laps: pd.DataFrame, fits: dict[str, DegradationFit], t0_s: float
) -> pd.Series:
    """What the pooled curve says this lap's tyre has already cost.

    Deliberately the simulator's own `tyre_deg_s` rather than a second spelling of T5: the
    multiplier is a slope against this quantity, so if the two ever drifted apart the
    fitted style would scale a curve the race never runs. A compound with no fit predicts
    zero — there is no curve for a driver to be fast or slow against.
    """
    predicted_s = np.zeros(len(laps))
    age = laps["tyre_life"].to_numpy(dtype=float)
    compound = laps["compound"].to_numpy()
    for name, fit in fits.items():
        on_compound = compound == name
        predicted_s[on_compound] = tyre_deg_s(t0_s, fit.a, fit.b, age[on_compound])
    return pd.Series(predicted_s, index=laps.index)


def fit_deg_multipliers(
    laps: pd.DataFrame, *, min_stints: int, max_rel_se: float
) -> dict[str, DegStyleFit]:
    """One multiplier per driver over every circuit and compound in `laps`.

    Wants columns driver, session_id, stint, pace_residual_s and predicted_deg_s.
    """
    raw = {
        str(code): _one_driver(rows) for code, rows in laps.groupby("driver")
    }
    identified = {
        code: fit
        for code, fit in raw.items()
        if fit["n_stints"] >= min_stints and fit["rel_se"] <= max_rel_se
    }
    scale = _normalising_scale(identified)

    published = {}
    for code, fit in raw.items():
        if code in identified:
            published[code] = DegStyleFit(
                mult=fit["mult"] / scale, se=fit["se"] / scale, rel_se=fit["rel_se"],
                n_stints=fit["n_stints"], n_laps=fit["n_laps"], identified=True,
            )
        else:
            # the honest value and the honest tag. The error bar stays the raw estimate's,
            # because it is the diagnostic that explains the refusal
            published[code] = DegStyleFit(
                mult=1.0, se=fit["se"], rel_se=fit["rel_se"],
                n_stints=fit["n_stints"], n_laps=fit["n_laps"], identified=False,
            )
    return published


def _normalising_scale(identified: dict[str, dict]) -> float:
    """The constant that puts the published vector's lap-weighted mean at exactly 1.0.

    Solving sum(w*p)/sum(w) == 1, with p = m/c for an identified driver and 1.0 for the
    rest, leaves c as the lap-weighted mean of the identified raw multipliers alone. It
    divides both mult and se, and rel_se is invariant under it, so no driver crosses the
    identification gate as a result of applying it.
    """
    if not identified:
        return 1.0
    laps = sum(fit["n_laps"] for fit in identified.values())
    return sum(fit["n_laps"] * fit["mult"] for fit in identified.values()) / laps


def _one_driver(laps: pd.DataFrame) -> dict:
    predicted_s = laps["predicted_deg_s"].to_numpy(dtype=float)
    residual_s = laps["pace_residual_s"].to_numpy(dtype=float)
    # a stint number restarts every session, so the cluster key needs both — keyed on
    # either alone this silently merges a driver's Bahrain second stint with their Monaco
    # second stint, and both the count gate and the error bar read low
    stints = laps.groupby(["session_id", "stint"])
    sample = {"n_stints": int(stints.ngroups), "n_laps": int(len(laps))}

    signal = float(predicted_s @ predicted_s)
    if signal <= 0.0:
        # a quarter of the committed degradation curves sit at exactly a = 0, where the
        # fitter hit its lower bound on a flat residual cloud. A driver whose whole sample
        # came from those has no denominator, which reads as unidentified rather than as a
        # division that quietly returns an infinity
        return {"mult": 1.0, "se": np.inf, "rel_se": np.inf, **sample}

    mult = float(residual_s @ predicted_s) / signal
    error_s = residual_s - mult * predicted_s
    # clustered by stint. A set that runs hot is slow for its whole life, so a stint's laps
    # are one observation and not twenty; on the era-2024 fit the lap-level error bar runs
    # 2.3x small at the median, which is enough to walk a thin driver through the gate.
    meat = sum(
        float((group["_predicted_s"] * group["_error_s"]).sum()) ** 2
        for _, group in laps.assign(_predicted_s=predicted_s, _error_s=error_s).groupby(
            ["session_id", "stint"]
        )
    )
    se = float(np.sqrt(meat) / signal)
    return {"mult": mult, "se": se, "rel_se": se / abs(mult) if mult else np.inf, **sample}
