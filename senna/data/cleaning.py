"""The 5.3.4 cleaning contract as pure functions.

Each rule takes a frame with FastF1's own column names and returns what it
kept plus a DropCount for the quality report. Nothing here mutates its input,
touches the network, or reads config — thresholds arrive as arguments so the
provenance stays in configs/ingest.yaml.
"""

import pandas as pd

from senna.data.quality import DropCount


def drop_inaccurate(laps: pd.DataFrame) -> tuple[pd.DataFrame, DropCount]:
    kept = laps[laps["IsAccurate"]]
    count = DropCount(
        rule="is_accurate",
        rows_in=len(laps),
        rows_dropped=len(laps) - len(kept),
        rows_flagged=0,
    )
    return kept, count


def split_in_out_laps(laps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, DropCount]:
    """E-09: in/out laps leave the pace frame but stay in the pit-timing frame."""
    in_or_out = laps["PitInTime"].notna() | laps["PitOutTime"].notna()
    count = DropCount(
        rule="in_out_laps",
        rows_in=len(laps),
        rows_dropped=int(in_or_out.sum()),
        rows_flagged=0,
    )
    return laps[~in_or_out], laps[in_or_out], count


def flag_green_laps(laps: pd.DataFrame) -> tuple[pd.DataFrame, DropCount]:
    """A lap is green only if its TrackStatus string is 1 for the whole lap.

    "12" means green then SC mid-lap — not a clean lap. Non-green laps are
    flagged, never dropped: they feed the event-rate fits (5.3.4).
    """
    is_green = laps["TrackStatus"].map(lambda status: set(str(status)) == {"1"})
    flagged = laps.assign(is_green=is_green)
    count = DropCount(
        rule="is_green",
        rows_in=len(laps),
        rows_dropped=0,
        rows_flagged=int((~is_green).sum()),
    )
    return flagged, count


def impute_laptime_for_replay(laps: pd.DataFrame) -> tuple[pd.DataFrame, DropCount]:
    """Replay display only — fits never call this (5.3.4: never impute for fits)."""
    missing = laps["LapTime"].isna()
    replay = laps.assign(
        LapTime=laps["LapTime"].fillna(laps["LapTime"].median()),
        lap_time_imputed=missing,
    )
    count = DropCount(
        rule="lap_time_imputed",
        rows_in=len(laps),
        rows_dropped=0,
        rows_flagged=int(missing.sum()),
    )
    return replay, count


def split_telemetry_gaps(
    car_data: pd.DataFrame, gap_split_s: float
) -> tuple[pd.DataFrame, DropCount]:
    """Gaps strictly over the threshold start a new trace; never interpolate across one."""
    deltas_s = car_data["Time"].diff().dt.total_seconds()
    breaks = deltas_s > gap_split_s
    traced = car_data.assign(trace_id=breaks.cumsum().astype(int))
    count = DropCount(
        rule="telemetry_gaps",
        rows_in=len(car_data),
        rows_dropped=0,
        rows_flagged=int(breaks.sum()),
    )
    return traced, count


def clean_pos_data(pos: pd.DataFrame, zscore_max: float) -> tuple[pd.DataFrame, DropCount]:
    """Decimetres to metres, OnTrack only, then a z-score gate on point-to-point speed."""
    rows_in = len(pos)
    metres = pos.assign(X=pos["X"] / 10.0, Y=pos["Y"] / 10.0, Z=pos["Z"] / 10.0)
    on_track = metres[metres["Status"] == "OnTrack"]

    step_m = (
        on_track[["X", "Y", "Z"]].diff().pow(2).sum(axis=1).pow(0.5)
    )
    speed_mps = step_m / on_track["Time"].diff().dt.total_seconds()
    zscore = (speed_mps - speed_mps.mean()) / speed_mps.std()
    # the first point has no inbound speed; a NaN z-score keeps it
    kept = on_track[~(zscore.abs() > zscore_max)]

    count = DropCount(
        rule="pos_data",
        rows_in=rows_in,
        rows_dropped=rows_in - len(kept),
        rows_flagged=0,
    )
    return kept, count


def is_dry_race(weather: pd.DataFrame, race_control: pd.DataFrame) -> bool:
    """Wet or red-flagged races leave the dry tyre fits and are analysed separately."""
    rained = bool(weather["Rainfall"].any())
    red_flagged = bool((race_control["Flag"] == "RED").any())
    return not (rained or red_flagged)


def missing_channels(car_data: pd.DataFrame | None, expected_channels: list[str]) -> list[str]:
    """F-14: a missing channel is recorded for the report, never fatal to ingest."""
    if car_data is None:
        return list(expected_channels)
    return [channel for channel in expected_channels if channel not in car_data.columns]
