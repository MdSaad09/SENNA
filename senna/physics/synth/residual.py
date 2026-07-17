"""T8 — residual recalibration: one named constant per circuit.

After T1-T7, per calibration circuit c_circuit = median(real 2026 green lap
time) - median(model-implied lap time). It absorbs everything the physics
terms leave on the table into a single interpretable offset; circuits with no
2026 data take the pooled c_global. The held-out error on rounds 7+ is the
headline sim-to-real number, and it is computed in validate.py, never here —
a residual tuned on the validation rounds would validate itself.
"""

import numpy as np
import pandas as pd

from senna.physics.synth.frames import refuse_validation_rounds


def fit_residual_s(
    real_laps: pd.DataFrame, model_median_s: float, *, calibration_rounds: list[int]
) -> float:
    """c_circuit from green, accurate calibration laps (E-09, E-14)."""
    refuse_validation_rounds(real_laps, calibration_rounds)
    clean = real_laps[
        real_laps["is_green"].fillna(False).astype(bool)
        & real_laps["is_accurate"].fillna(False).astype(bool)
    ]
    return float(np.median(clean["lap_time_s"])) - model_median_s


def pool_residual_s(c_by_circuit: dict[str, float]) -> float:
    """c_global for circuits without their own 2026 calibration."""
    return float(np.median(list(c_by_circuit.values())))
