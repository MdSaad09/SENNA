"""The deterministic twin (A-05, M3). An EventTrace is every stochastic draw a race
realised — the grid, the driver offsets, and per lap the track status, weather, wetness,
tyre failures and the field's applied pit and mode choices. Replaying a trace through
F1RaceEnv freezes those events while the ego's strategy varies, which is what the oracle
regret metric needs ("the deterministic twin of each eval race") and what makes a paired
comparison actually paired: the RNG stream consumes a policy-dependent number of variates
(a tyre only rolls for failure past its cliff, a stop only draws service time when it
happens), so two policies on the same seed diverge in their events after the first
different stop. Pinning the trace is the honest fix.

The trace records what the env APPLIED, not how the rivals decided it, so it survives any
change to the archetype logic (F06 senna/env/rivals.py). It is also the capture the M5
afterstate metric (F14) branches from.
"""

from dataclasses import dataclass

import numpy as np

from senna.env import events


@dataclass
class EventTrace:
    circuit: str
    era: str
    seed: int
    n_laps: int
    n_cars: int
    grid: np.ndarray            # int (n_cars,) — the reset grid permutation
    driver_s: np.ndarray        # float (n_cars,) — the per-car pace offset drawn at reset
    status: np.ndarray          # int (n_laps,) — realised track status per lap
    red_flag: np.ndarray        # bool (n_laps,) — the E-04 event flag per lap
    weather: np.ndarray         # int (n_laps,)
    wetness: np.ndarray         # float (n_laps,)
    failed: np.ndarray          # bool (n_laps, n_cars) — realised tyre failures
    rival_pit: np.ndarray       # int8 (n_laps, n_cars) — compound each non-ego car took (-1 stay)
    rival_mode: np.ndarray      # int8 (n_laps, n_cars) — energy mode applied to each non-ego car

    @classmethod
    def green(cls, circuit, era, n_laps, n_cars, *, grid, driver_s=None):
        """A synthetic all-green, bone-dry trace: no neutralisations, no weather, no
        failures, no rival stops, balanced modes. The Stage A solo reference and the oracle
        toy race run on this — a race with a computable near-optimal answer (5.7)."""
        driver_s = (np.zeros(n_cars) if driver_s is None
                    else np.array(driver_s, dtype=float))  # copy: the trace outlives the caller
        return cls(
            circuit=circuit,
            era=era,
            seed=-1,
            n_laps=n_laps,
            n_cars=n_cars,
            grid=np.array(grid, dtype=int),
            driver_s=driver_s,
            status=np.full(n_laps, events.GREEN, dtype=int),
            red_flag=np.zeros(n_laps, dtype=bool),
            weather=np.full(n_laps, events.DRY, dtype=int),
            wetness=np.zeros(n_laps, dtype=float),
            failed=np.zeros((n_laps, n_cars), dtype=bool),
            rival_pit=np.full((n_laps, n_cars), -1, dtype=np.int8),
            rival_mode=np.full((n_laps, n_cars), 1, dtype=np.int8),  # 1 = balanced
        )

    def save_npz(self, path) -> None:
        np.savez(
            path,
            meta=np.array([self.circuit, self.era, self.seed, self.n_laps, self.n_cars],
                          dtype=object),
            grid=self.grid, driver_s=self.driver_s, status=self.status,
            red_flag=self.red_flag, weather=self.weather, wetness=self.wetness,
            failed=self.failed, rival_pit=self.rival_pit, rival_mode=self.rival_mode,
        )

    @classmethod
    def from_npz(cls, path):
        with np.load(path, allow_pickle=True) as data:
            circuit, era, seed, n_laps, n_cars = data["meta"]
            return cls(
                circuit=str(circuit), era=str(era), seed=int(seed),
                n_laps=int(n_laps), n_cars=int(n_cars),
                grid=data["grid"], driver_s=data["driver_s"], status=data["status"],
                red_flag=data["red_flag"], weather=data["weather"], wetness=data["wetness"],
                failed=data["failed"], rival_pit=data["rival_pit"], rival_mode=data["rival_mode"],
            )
