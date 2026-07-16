"""Pit-lane loss per circuit from OpenF1 pit durations — the E-05 FIFO inputs."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PitLossFit:
    mean_s: float
    sigma_s: float  # sample std (ddof=1), the FIFO service-time spread
    n_stops: int
    n_excluded: int  # nulls and over-max stops: penalties, red flags, bad rows


def fit_pit_loss(pit_stops: pd.DataFrame, *, max_duration_s: float) -> PitLossFit:
    durations_s = pit_stops["pit_duration_s"]
    usable = durations_s.notna() & (durations_s <= max_duration_s)
    kept = durations_s[usable]
    return PitLossFit(
        mean_s=float(kept.mean()),
        sigma_s=float(kept.std(ddof=1)),
        n_stops=int(usable.sum()),
        n_excluded=int(len(durations_s) - usable.sum()),
    )
