"""Telemetry lap segmentation shared by T1 and T2.

A lap is a sequence of throttle, brake and coast phases. Phases never span a
trace_id boundary: a dropout split upstream by split_telemetry_gaps would
otherwise let one phase borrow time and distance from across the hole (AR-16).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

KMH_TO_MS = 1.0 / 3.6


@dataclass(frozen=True)
class Phase:
    kind: str  # "throttle" | "brake" | "coast"
    t_start_s: float
    t_end_s: float
    v_start_kmh: float
    v_end_kmh: float
    dist_m: float
    trace_id: int


def lap_phases(car_data: pd.DataFrame, *, throttle_full_pct: float) -> list[Phase]:
    phases = []
    for trace_id, trace in car_data.groupby("trace_id"):
        time_s = trace["Time"].dt.total_seconds().to_numpy()
        speed_kmh = trace["Speed"].to_numpy(dtype=float)
        brake = trace["Brake"].to_numpy(dtype=bool)
        throttle_full = trace["Throttle"].to_numpy(dtype=float) >= throttle_full_pct
        kind = np.where(brake, "brake", np.where(throttle_full, "throttle", "coast"))

        breaks = np.flatnonzero(kind[1:] != kind[:-1]) + 1
        for start, end in zip(
            np.concatenate([[0], breaks]),
            np.concatenate([breaks, [len(kind)]]),
            strict=True,
        ):
            if end - start < 2:
                continue  # a single sample has no duration and no distance
            span_t = time_s[start:end]
            span_v = speed_kmh[start:end] * KMH_TO_MS
            phases.append(
                Phase(
                    kind=str(kind[start]),
                    t_start_s=float(span_t[0]),
                    t_end_s=float(span_t[-1]),
                    v_start_kmh=float(speed_kmh[start]),
                    v_end_kmh=float(speed_kmh[end - 1]),
                    dist_m=float(np.trapezoid(span_v, span_t)),
                    trace_id=int(trace_id),
                )
            )
    return phases
