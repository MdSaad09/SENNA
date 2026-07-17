"""Ribbon annotations: corners, braking zones, X-mode sections (5.10.1 item 6).

Corners are official (from FastF1's CircuitInfo); braking and X-mode are inferred
from the fastest lap's telemetry and are stylised until official section data
exists. Distances are along-lap metres so the frontend can drape each marker on
the ribbon by arc length.
"""

import numpy as np
import pandas as pd


def braking_zones(
    distance_m: np.ndarray, speed_kmh: np.ndarray, drop_kmh: float, window_m: float
) -> list[dict]:
    """Stretches where speed falls more than drop_kmh within a window_m span (5.10.1 item 6)."""
    count = len(distance_m)
    is_braking = np.zeros(count, dtype=bool)
    for start in range(count):
        ahead = distance_m - distance_m[start] <= window_m
        ahead[:start] = False
        drop = speed_kmh[start] - speed_kmh[ahead].min()
        if drop >= drop_kmh:
            trough = start + int(np.argmin(speed_kmh[ahead]))
            is_braking[start : trough + 1] = True

    zones = []
    edge = 0
    while edge < count:
        if not is_braking[edge]:
            edge += 1
            continue
        start = edge
        while edge + 1 < count and is_braking[edge + 1]:
            edge += 1
        segment = speed_kmh[start : edge + 1]
        zones.append(
            {
                "start_m": float(distance_m[start]),
                "end_m": float(distance_m[edge]),
                "entry_kmh": float(segment.max()),
                "min_kmh": float(segment.min()),
            }
        )
        edge += 1
    return zones


def xmode_sections(
    distance_m: np.ndarray, throttle_pct: np.ndarray, full_throttle_pct: float
) -> list[dict]:
    """Full-throttle runs, longest first — the stylised X-mode sections (5.10.1 item 6)."""
    full = throttle_pct >= full_throttle_pct
    sections = []
    edge = 0
    count = len(distance_m)
    while edge < count:
        if not full[edge]:
            edge += 1
            continue
        start = edge
        while edge + 1 < count and full[edge + 1]:
            edge += 1
        sections.append(
            {
                "start_m": float(distance_m[start]),
                "end_m": float(distance_m[edge]),
                "length_m": float(distance_m[edge] - distance_m[start]),
            }
        )
        edge += 1
    return sorted(sections, key=lambda section: section["length_m"], reverse=True)


def corners_from_circuit_info(corners: pd.DataFrame) -> list[dict]:
    """Map FastF1 CircuitInfo corners to along-lap markers (5.10.1 item 6)."""
    return [
        {
            "number": int(row.Number),
            "distance_m": float(row.Distance),
            "angle_deg": float(row.Angle),
            "x": float(row.X),
            "y": float(row.Y),
        }
        for row in corners.itertuples(index=False)
    ]
