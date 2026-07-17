"""T2 — corner-speed exponent: how much apex speed the downforce cut costs.

v_corner scales with downforce^exponent at fixed radius; the spec's prior is
the fourth root (5.4 T2). The exponent is fitted globally from matched 2024 vs
2026 apexes on both-era circuits — it is an effective 2024-to-2026 transform
constant, deliberately absorbing tyre and mass differences, which is exactly
what applying it to an unseen circuit requires.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from senna.physics.synth.segments import lap_phases


@dataclass(frozen=True)
class CornerExponentFit:
    exponent: float
    n_corners: int
    fallback: bool  # True -> the prior stands, flagged stylised in transforms.yaml


def fit_corner_exponent(
    apex_pairs: pd.DataFrame,
    *,
    downforce_ratio: float,
    prior: float,
    bounds: tuple[float, float],
    min_corners: int,
) -> CornerExponentFit:
    n_corners = len(apex_pairs)
    if n_corners < min_corners:
        return CornerExponentFit(exponent=prior, n_corners=n_corners, fallback=True)

    # log(v26/v24) = exponent * log(ratio) per corner; the mean is the
    # least-squares slope through the origin in a single regressor
    ratios = np.log(
        apex_pairs["v_2026_kmh"].to_numpy(dtype=float)
        / apex_pairs["v_2024_kmh"].to_numpy(dtype=float)
    )
    exponent = float(np.mean(ratios) / np.log(downforce_ratio))
    low, high = bounds
    if not low <= exponent <= high:
        return CornerExponentFit(exponent=prior, n_corners=n_corners, fallback=True)
    return CornerExponentFit(exponent=exponent, n_corners=n_corners, fallback=False)


def apex_speeds_kmh(car_data: pd.DataFrame, *, throttle_full_pct: float) -> list[float]:
    """Apex speed of every non-throttle phase, in lap order — T2's raw material."""
    return [
        min(phase.v_start_kmh, phase.v_end_kmh)
        for phase in lap_phases(car_data, throttle_full_pct=throttle_full_pct)
        if phase.kind != "throttle"
    ]


def matched_apexes(
    apexes_2024_kmh: list[float],
    apexes_2026_kmh: list[float],
    *,
    circuit: str,
    min_corner_apex_kmh: float,
) -> pd.DataFrame:
    """Pair corners by lap-order ordinal; only aero-dominated apexes inform T2.

    Ordinal matching only holds when both eras resolve the same corner count;
    a mismatched lap contributes nothing rather than misaligned pairs.
    """
    if len(apexes_2024_kmh) != len(apexes_2026_kmh):
        return pd.DataFrame(columns=["circuit", "v_2024_kmh", "v_2026_kmh"])
    pairs = pd.DataFrame(
        {
            "circuit": circuit,
            "v_2024_kmh": apexes_2024_kmh,
            "v_2026_kmh": apexes_2026_kmh,
        }
    )
    return pairs[pairs["v_2024_kmh"] >= min_corner_apex_kmh].reset_index(drop=True)
