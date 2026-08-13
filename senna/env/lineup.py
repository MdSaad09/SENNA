"""Who is in which seat, and what the fitted table says about them (F17).

`configs/drivers.yaml` is keyed by driver code and era; a race needs arrays in seat order.
This is the translation, and the three rungs of the fallback ladder are the whole of it:

    the driver's fitted cell at this circuit     -> "circuit"
    their lap-weighted mean over fitted circuits -> "driver_mean"
    nothing the table can say about this seat    -> "drawn"

The last rung is not zero. Every fitted effect is centred, so a seat pinned at exactly
zero is a seat at the field average, and on a grid the average is quicker than most of it —
an unknown driver would quietly become one of the best cars on the track. `seat_pace_s`
carries NaN there instead and `reset` leaves that seat the offset it drew, which is also
why a named race and the unnamed race at the same seed differ only in the named seats.

A missing table is that third rung for every seat, so a clone with no generated
drivers.yaml still races. The alternative is M2 refusing to run on a fresh checkout.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from senna import config

_CIRCUIT = "circuit"
_DRIVER_MEAN = "driver_mean"
_DRAWN = "drawn"


@dataclass(frozen=True)
class Lineup:
    codes: tuple[str, ...]      # seat order, truncated to the grid
    seat_pace_s: np.ndarray     # seconds per lap, NaN where the seat draws instead
    deg_mult: np.ndarray        # multiplier on the pooled degradation amplitude, 1.0 default
    levels: tuple[str, ...]     # which rung answered for each seat


def resolve(
    codes, *, circuit: str, era: str, n_cars: int, configs_dir: Path | None = None
) -> Lineup:
    table = _table(configs_dir)
    era_key = int(era)
    seat_pace_s = np.full(n_cars, np.nan)
    deg_mult = np.ones(n_cars)
    levels = [_DRAWN] * n_cars

    seats = tuple(codes)[:n_cars]
    for seat, code in enumerate(seats):
        entry = (table.get(code) or {}).get(era_key)
        if not entry:
            continue
        cell_s = (entry.get("seat_pace_s") or {}).get(circuit)
        mean_s = entry.get("seat_pace_mean_s")
        if cell_s is not None:
            seat_pace_s[seat], levels[seat] = float(cell_s), _CIRCUIT
        elif mean_s is not None:
            seat_pace_s[seat], levels[seat] = float(mean_s), _DRIVER_MEAN
        # a driver can carry a tyre style without a publishable seat pace, and the two
        # gates are separate, so this is not tied to whether a pace rung answered
        if entry.get("deg_mult") is not None:
            deg_mult[seat] = float(entry["deg_mult"])

    return Lineup(
        codes=seats, seat_pace_s=seat_pace_s, deg_mult=deg_mult, levels=tuple(levels)
    )


def _table(configs_dir: Path | None) -> dict:
    try:
        return config.load("drivers", configs_dir).get("drivers") or {}
    except FileNotFoundError:
        # not a silent default for a fitted constant, which the loader is right to refuse:
        # the table is an optional overlay, and its absence has a defined meaning
        return {}
