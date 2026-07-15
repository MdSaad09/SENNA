"""FastF1 access — the only module in the package that imports fastf1.

Cache first, always (E-12): enable_cache runs before any other call in here,
so bulk ingest asks Jolpica once and every retry reads from disk. Session
choice comes from the event schedule's own Session1-5 columns, never a fixed
name list — sprint weekends renamed their sessions twice already (E-11).
"""

from pathlib import Path

import fastf1
import pandas as pd

# re-exported so the orchestrator can catch the hourly-budget stop without
# importing fastf1 itself
from fastf1.exceptions import RateLimitExceededError  # noqa: F401

from senna.data.cleaning import missing_channels

SESSION_SLOTS = range(1, 6)

# the car-data channels 5.3.2 consumes; absence is reported, never fatal (F-14)
CAR_CHANNELS = ["Speed", "Throttle", "Brake", "nGear", "RPM", "DRS"]


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


def _probe_missing_channels(session) -> list[str]:
    try:
        car_data = session.laps.pick_fastest().get_car_data()
    except Exception:
        # no laps or no telemetry at all — every channel is missing (F-14),
        # which is a report entry, not a reason to abort the session
        return list(CAR_CHANNELS)
    return missing_channels(car_data, CAR_CHANNELS)
