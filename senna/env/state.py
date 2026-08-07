"""The race state as a struct of arrays — one numpy row per car, never a list of
car objects. The hot loop touches these arrays directly (senna/CLAUDE.md), so the
whole 22-car field advances in vectorised numpy with no per-car Python overhead and
nothing pandas-shaped in sight.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class RaceState:
    n_cars: int
    lap: int                        # laps completed; 0 at the grid, total_laps at the flag
    compound: np.ndarray            # int code into COMPOUNDS, per car
    tyre_age: np.ndarray            # int laps on the current set
    soc_mj: np.ndarray              # energy store, held in [0, 4]
    fuel_kg: np.ndarray             # remaining fuel
    cumulative_time_s: np.ndarray   # race time so far — the sole source of classification
    grid_position: np.ndarray       # starting slot 1..n, fixed at reset — the grid_delta anchor
    pit_count: np.ndarray           # stops made
    second_compound_used: np.ndarray  # bool: has this car run two distinct compounds (F-20)
    first_compound: np.ndarray      # int code the car started on, to judge "second compound"
    last_harvest_mj: np.ndarray
    last_deploy_mj: np.ndarray
    retired: np.ndarray             # bool: fuel/energy out or a terminal failure
    driver_s: np.ndarray            # fixed per-car pace offset, drawn once at reset
    track_status: int               # 0 green, 1 vsc, 2 sc, 3 red
    status_laps_left: int           # laps the current neutralisation still runs
    weather: int                    # 0 dry, 1 damp, 2 wet
    wetness: float                  # continuous [0, 1], the crossover scalar (E-08)
    red_flags_seen: int
    red_flag_now: bool              # a red flag was raised entering this lap (E-04)
    # which seat the adapter is watching, and nothing more. Since F16 no engine function
    # branches on it — the tick runs twenty-two equal cars, and the pace and pit-response
    # asymmetries live in rivals.draw_field where they belong. The twin is the documented
    # exception (A-05). tests/env/test_engine.py::test_seat_symmetry holds it this way.
    ego: int

    def positions(self) -> np.ndarray:
        """Classification 1..n by cumulative race time; retired cars sink to the back."""
        keys = np.where(self.retired, np.inf, self.cumulative_time_s)
        order = np.argsort(keys, kind="stable")
        rank = np.empty(self.n_cars, dtype=int)
        rank[order] = np.arange(1, self.n_cars + 1)
        return rank
