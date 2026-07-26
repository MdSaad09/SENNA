"""FastF1 access — the only module in the package that imports fastf1.

Cache first, always (E-12): enable_cache runs before any other call in here,
so bulk ingest asks Jolpica once and every retry reads from disk. Session
choice comes from the event schedule's own Session1-5 columns, never a fixed
name list — sprint weekends renamed their sessions twice already (E-11).
"""

from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

# re-exported so the orchestrator can catch the hourly-budget stop without
# importing fastf1 itself
from fastf1.exceptions import RateLimitExceededError  # noqa: F401

from senna.data.cleaning import clean_pos_data, missing_channels

SESSION_SLOTS = range(1, 6)

# the car-data channels 5.3.2 consumes; absence is reported, never fatal (F-14)
CAR_CHANNELS = ["Speed", "Throttle", "Brake", "nGear", "RPM", "DRS"]


class MissingPositionDataError(LookupError):
    """The chosen lap has no X/Y/Z channel — the session cannot yield a ribbon."""


def enable_cache(cache_dir: str | Path) -> None:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))


def fetch_schedule(season: int) -> pd.DataFrame:
    return fastf1.get_event_schedule(season, include_testing=False)


def plan_sessions(schedule: pd.DataFrame, sessions_to_ingest: list[str]) -> list[dict]:
    planned = []
    for _, event in schedule.iterrows():
        for slot in SESSION_SLOTS:
            session_name = event.get(f"Session{slot}")
            if session_name in sessions_to_ingest:
                planned.append(
                    {
                        "round": event["RoundNumber"],
                        "event_name": event["EventName"],
                        "session_name": session_name,
                        "session_date_utc": event[f"Session{slot}DateUtc"],
                    }
                )
    return planned


def load_session_frames(
    season: int, round_number: int, session_name: str
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """One session's consumed frames (5.3.2), plus its missing car channels."""
    session = fastf1.get_session(season, round_number, session_name)
    session.load(laps=True, telemetry=True, weather=True, messages=True)
    frames = {
        "laps": pd.DataFrame(session.laps),
        "weather": session.weather_data,
        "race_control": session.race_control_messages,
        "results": session.results,
    }
    return frames, _probe_missing_channels(session)


def load_car_data(
    season: int, round_number: int, session_name: str
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Per-driver car telemetry plus the laps frame that windows it (F02 energy fits).

    Telemetry never went to Postgres — the on-disk cache is the store, so this
    stays cheap on reruns and this module stays the only fastf1 import site.
    """
    session = fastf1.get_session(season, round_number, session_name)
    session.load(laps=True, telemetry=True, weather=False, messages=False)
    return dict(session.car_data), pd.DataFrame(session.laps)


def load_fastest_lap_geometry(
    season: int, round_number: int, session_name: str, *, zscore_max: float
) -> tuple[dict[str, np.ndarray], pd.DataFrame]:
    """Fastest accurate lap's cleaned centreline and telemetry, plus corners (F04, 5.10.1).

    The centreline runs through clean_pos_data (5.3.4): decimetres to metres,
    OnTrack points only, point-to-point z-score gate. Picking an accurate lap and
    then cleaning keeps a track-limits lap or a GPS teleport out of the ribbon, so
    a data spike never masquerades as a geometry self-intersection (E-17). Speed
    and throttle ride the car-data channel for the braking and X-mode annotations.
    Corners come from CircuitInfo. This stays the one site that imports fastf1.
    """
    session = fastf1.get_session(season, round_number, session_name)
    session.load(laps=True, telemetry=True, weather=False, messages=False)
    lap = session.laps.pick_accurate().pick_fastest()

    pos = lap.get_pos_data()
    if pos.empty or "X" not in pos.columns:
        # some archive sessions carry laps but no position channel; the caller
        # skips the event and its coverage flag stays honest (F-08), instead of a
        # KeyError killing the whole library build
        raise MissingPositionDataError(
            f"{season} round {round_number} {session_name}: fastest accurate lap "
            "has no position data — the ribbon cannot be built from this session"
        )
    centreline, _ = clean_pos_data(pos, zscore_max)
    car = lap.get_car_data().add_distance()
    geometry = {
        "x_m": centreline["X"].to_numpy(),
        "y_m": centreline["Y"].to_numpy(),
        "z_m": centreline["Z"].to_numpy(),
        "speed_kmh": car["Speed"].to_numpy(dtype=float),
        "throttle_pct": car["Throttle"].to_numpy(dtype=float),
        "distance_m": car["Distance"].to_numpy(dtype=float),
    }
    return geometry, session.get_circuit_info().corners


def _probe_missing_channels(session) -> list[str]:
    try:
        car_data = session.laps.pick_fastest().get_car_data()
    except Exception:
        # no laps or no telemetry at all — every channel is missing (F-14),
        # which is a report entry, not a reason to abort the session
        return list(CAR_CHANNELS)
    return missing_channels(car_data, CAR_CHANNELS)
