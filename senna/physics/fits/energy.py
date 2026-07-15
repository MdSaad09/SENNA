"""Braking-energy and full-throttle integrals from car telemetry (T1/T4 inputs).

No real per-lap ERS series exists (F-13): these integrals estimate what a 2026
powertrain could harvest and deploy from what the car observably did — braking
kinetic-energy deltas and time spent at full throttle. The cadence is ~4-5 Hz
and uneven (AR-16), so everything integrates over actual timestamp deltas, and
nothing crosses a trace break: a dropout split upstream by split_telemetry_gaps
would otherwise donate invented energy to the lap.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from senna.physics.fits.fuel import fuel_profile

KMH_TO_MS = 1.0 / 3.6


@dataclass(frozen=True)
class LapEnergyIntegrals:
    full_throttle_s: float
    braking_energy_mj: float
    cadence_hz: float


def lap_energy_integrals(
    car_data: pd.DataFrame, *, throttle_full_pct: float, mass_kg: float
) -> LapEnergyIntegrals:
    """Integrals over one lap's telemetry, already split into trace_id segments."""
    full_throttle_s = 0.0
    braking_j = 0.0
    deltas_s: list[np.ndarray] = []
    for _, trace in car_data.groupby("trace_id"):
        time_s = trace["Time"].dt.total_seconds().to_numpy()
        dt_s = np.diff(time_s)
        deltas_s.append(dt_s)
        # trapezoid on the full-throttle indicator: a sample at 97% next to one
        # at 100% contributes half its interval, matching the uneven cadence
        flat_out = (trace["Throttle"].to_numpy(dtype=float) >= throttle_full_pct).astype(float)
        full_throttle_s += float(np.sum(dt_s * (flat_out[:-1] + flat_out[1:]) / 2.0))
        braking_j += _braking_phases_j(
            trace["Brake"].to_numpy(dtype=bool),
            trace["Speed"].to_numpy(dtype=float) * KMH_TO_MS,
            mass_kg,
        )
    within_trace_dt_s = np.concatenate(deltas_s) if deltas_s else np.array([])
    cadence_hz = 1.0 / float(np.median(within_trace_dt_s)) if within_trace_dt_s.size else 0.0
    return LapEnergyIntegrals(
        full_throttle_s=full_throttle_s,
        braking_energy_mj=braking_j / 1e6,
        cadence_hz=cadence_hz,
    )


def _braking_phases_j(brake: np.ndarray, speed_ms: np.ndarray, mass_kg: float) -> float:
    """Kinetic energy shed across each contiguous brake application."""
    edges = np.flatnonzero(np.diff(brake.astype(int)))
    starts = [i + 1 for i in edges if not brake[i]]
    ends = [i for i in edges if brake[i]]
    if brake[0]:
        starts.insert(0, 0)
    if brake[-1]:
        ends.append(len(brake) - 1)
    total_j = 0.0
    for start, end in zip(starts, ends, strict=True):
        shed_j = 0.5 * mass_kg * (speed_ms[start] ** 2 - speed_ms[end] ** 2)
        total_j += max(0.0, shed_j)  # uphill or noisy phases must not pay energy back
    return total_j


def session_energy_frame(
    car_data_by_driver: dict[str, pd.DataFrame],
    session_laps: pd.DataFrame,
    *,
    gap_split_s: float,
    throttle_full_pct: float,
    car_mass_kg: float,
    race_fuel_kg: float,
    sc_burn_factor: float,
) -> pd.DataFrame:
    """Per-lap integrals for one race session, FastF1-native laps as input.

    Only green, accurate, non-in/out laps with a start time and duration are
    integrated (5.3.4); mass is the car plus constructed fuel at the lap start.
    """
    from senna.data.cleaning import split_telemetry_gaps

    rows = []
    for driver_number, car_data in car_data_by_driver.items():
        driver_laps = session_laps[
            session_laps["DriverNumber"].astype(str) == str(driver_number)
        ]
        usable = driver_laps[
            driver_laps["IsAccurate"].fillna(False).astype(bool)
            & driver_laps["PitInTime"].isna()
            & driver_laps["PitOutTime"].isna()
            & driver_laps["LapTime"].notna()
            & driver_laps["LapStartTime"].notna()
            & driver_laps["TrackStatus"].map(lambda s: set(str(s)) == {"1"})
        ]
        if usable.empty:
            continue
        fuel_kg = fuel_profile(
            driver_laps.rename(
                columns={"LapNumber": "lap_number", "TrackStatus": "track_status"}
            ),
            race_fuel_kg=race_fuel_kg,
            sc_burn_factor=sc_burn_factor,
        )
        traced, _ = split_telemetry_gaps(car_data, gap_split_s)
        for index, lap in usable.iterrows():
            window = (traced["Time"] >= lap["LapStartTime"]) & (
                traced["Time"] < lap["LapStartTime"] + lap["LapTime"]
            )
            lap_trace = traced[window]
            if len(lap_trace) < 2:
                continue
            integrals = lap_energy_integrals(
                lap_trace,
                throttle_full_pct=throttle_full_pct,
                mass_kg=car_mass_kg + float(fuel_kg[index]),
            )
            rows.append(
                {
                    "driver_number": str(driver_number),
                    "lap_number": int(lap["LapNumber"]),
                    "lap_time_s": lap["LapTime"].total_seconds(),
                    "full_throttle_s": integrals.full_throttle_s,
                    "braking_energy_mj": integrals.braking_energy_mj,
                    "cadence_hz": integrals.cadence_hz,
                }
            )
    return pd.DataFrame(rows)
