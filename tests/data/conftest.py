"""Crafted-frame builders with FastF1's exact column spellings. No network anywhere."""

import pandas as pd
import pytest

# FastF1 hands these back as timedelta64; an all-NaT column would otherwise be
# inferred as datetime64, so the builder round-trips through a plain list.
_TIMEDELTA_COLUMNS = (
    "LapTime",
    "PitInTime",
    "PitOutTime",
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    "LapStartTime",
)


def _lap_row(lap_number: int) -> dict:
    return {
        "Driver": "VER",
        "DriverNumber": "1",
        "Team": "Red Bull Racing",
        "LapNumber": float(lap_number),
        "LapTime": pd.Timedelta(seconds=90.0),
        "Stint": 1.0,
        "Compound": "MEDIUM",
        "TyreLife": float(lap_number),
        "FreshTyre": True,
        "PitInTime": pd.NaT,
        "PitOutTime": pd.NaT,
        "Sector1Time": pd.Timedelta(seconds=28.0),
        "Sector2Time": pd.Timedelta(seconds=31.0),
        "Sector3Time": pd.Timedelta(seconds=31.0),
        "SpeedST": 312.0,
        "Position": 1.0,
        "TrackStatus": "1",
        "IsAccurate": True,
        "LapStartTime": pd.Timedelta(seconds=90.0 * (lap_number - 1)),
    }


@pytest.fixture
def make_laps():
    """One dict of overrides per lap; lap numbers run 1..n unless overridden."""

    def build(overrides_per_lap: list[dict]) -> pd.DataFrame:
        rows = [
            {**_lap_row(lap_number), **overrides}
            for lap_number, overrides in enumerate(overrides_per_lap, start=1)
        ]
        frame = pd.DataFrame(rows)
        for col in _TIMEDELTA_COLUMNS:
            frame[col] = pd.to_timedelta(frame[col].tolist())
        return frame

    return build


@pytest.fixture
def make_car_data():
    """Car telemetry at the caller's timestamps — cadence is ~4-5 Hz in real data (AR-16)."""

    def build(time_s: list[float]) -> pd.DataFrame:
        n = len(time_s)
        return pd.DataFrame(
            {
                "Time": pd.to_timedelta(time_s, unit="s"),
                "Speed": [250.0] * n,
                "Throttle": [100.0] * n,
                "Brake": [False] * n,
                "nGear": [7] * n,
                "RPM": [11000.0] * n,
                "DRS": [0] * n,
            }
        )

    return build


@pytest.fixture
def make_pos_data():
    """Position samples along the x axis, coordinates in decimetres as FastF1 ships them."""

    def build(
        x_dm: list[float], status: list[str] | None = None, step_s: float = 0.2
    ) -> pd.DataFrame:
        n = len(x_dm)
        return pd.DataFrame(
            {
                "Time": pd.to_timedelta([i * step_s for i in range(n)], unit="s"),
                "X": x_dm,
                "Y": [0.0] * n,
                "Z": [0.0] * n,
                "Status": status if status is not None else ["OnTrack"] * n,
            }
        )

    return build


@pytest.fixture
def make_weather():
    def build(rainfall: list[bool]) -> pd.DataFrame:
        n = len(rainfall)
        return pd.DataFrame(
            {
                "Time": pd.to_timedelta(range(n), unit="m"),
                "AirTemp": [24.0] * n,
                "TrackTemp": [38.0] * n,
                "Humidity": [55.0] * n,
                "Rainfall": rainfall,
                "WindSpeed": [2.5] * n,
            }
        )

    return build


@pytest.fixture
def make_race_control():
    def build(flags: list[str]) -> pd.DataFrame:
        n = len(flags)
        return pd.DataFrame(
            {
                "Time": pd.to_datetime([f"2024-03-02 15:{i:02d}:00" for i in range(n)]),
                "Category": ["Flag"] * n,
                "Flag": flags,
                "Status": [""] * n,
                "Message": [f"{flag} FLAG" for flag in flags],
                "Lap": list(range(1, n + 1)),
            }
        )

    return build


class VirtualClock:
    """Injectable clock/sleep pair: sleeping advances virtual time and is recorded."""

    def __init__(self) -> None:
        self.now_s = 0.0
        self.sleeps: list[float] = []

    def read(self) -> float:
        return self.now_s

    def sleep(self, duration_s: float) -> None:
        assert duration_s >= 0, f"asked to sleep {duration_s}s"
        self.sleeps.append(duration_s)
        self.now_s += duration_s


@pytest.fixture
def virtual_clock() -> VirtualClock:
    return VirtualClock()
