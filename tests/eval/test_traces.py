"""M2's real-race traces (F-24 / A-10, with E-04 and E-08 riding inside them). A
counterfactual is only worth reading against the events the team actually strategized
around, so the ten era-matched races replay a trace synthesized from ingested laps rather
than one drawn from the markov chain — the red flag and the wet crossover have to be in
the trace, not resampled.

Pinned here: the track-status digit mapping, the real-to-sim lap rescale, the grid rules
for pit-lane starts and short fields, the env's own acceptance of the synthesized result,
and the strict-era guard that refuses a circuit whose "2024" scenario is really the 2026
fallback. Rows are hand-built tuples: no database, no FastF1, no network.
"""

import numpy as np
import pytest

from senna import config
from senna.env import events
from senna.eval.traces import require_native_era_fits, trace_from_real_race
from tests.eval.conftest import SEED

CIRCUIT = "bahrain_grand_prix"  # carries native 2024 joint-pace and degradation fits
ERA = "2024"
COMPOUNDS = ("MEDIUM", "HARD", "SOFT")


def _driver_laps(real_total_laps, *, out_laps=(), status_by_lap=None):
    """One driver's ingested laps in the extract-query order, plus the lap's track-status
    digits: (lap_number, stint, compound, pit_in_time_s, track_status). A stint's last lap
    is the one carrying a pit-in time, and the next stint starts on its out-lap."""
    status_by_lap = status_by_lap or {}
    rows = []
    stint = 1
    for lap in range(1, real_total_laps + 1):
        if lap in out_laps:
            stint += 1
        pit_in_time_s = 3600.0 + lap * 95.0 if (lap + 1) in out_laps else None
        rows.append((
            lap, stint, COMPOUNDS[(stint - 1) % len(COMPOUNDS)], pit_in_time_s,
            status_by_lap.get(lap, "1"),
        ))
    return rows


def _dry_weather(real_total_laps):
    return [(float(lap * 95), False) for lap in range(real_total_laps)]


def _synthesize(scenario, laps_by_driver, grid, *, real_total_laps):
    return trace_from_real_race(
        circuit=CIRCUIT, era=ERA, scenario=scenario, laps_by_driver=laps_by_driver,
        weather_rows=_dry_weather(real_total_laps), grid=grid,
        real_total_laps=real_total_laps, seed=SEED, cfg=config.load("eval"),
    )


def test_trace_synthesis_from_handbuilt_rows(make_env):
    env = make_env(CIRCUIT, ERA)
    scenario = env.scenario
    real_total_laps = scenario.total_laps
    drivers = ("VER", "HAM", "LEC", "NOR")
    laps_by_driver = {
        driver: _driver_laps(real_total_laps, out_laps=(18, 39)) for driver in drivers
    }

    trace = _synthesize(
        scenario, laps_by_driver, {driver: i + 1 for i, driver in enumerate(drivers)},
        real_total_laps=real_total_laps,
    )

    n_laps, n_cars = scenario.total_laps, scenario.grid_size
    assert (trace.n_laps, trace.n_cars) == (n_laps, n_cars)
    assert (trace.circuit, trace.era) == (CIRCUIT, ERA)
    assert trace.status.shape == (n_laps,) and trace.status.dtype.kind == "i"
    assert trace.red_flag.shape == (n_laps,) and trace.red_flag.dtype == bool
    assert trace.weather.shape == (n_laps,) and trace.weather.dtype.kind == "i"
    assert trace.wetness.shape == (n_laps,) and trace.wetness.dtype.kind == "f"
    assert trace.failed.shape == (n_laps, n_cars) and trace.failed.dtype == bool
    assert not trace.failed.any()  # declared synthetic: M2 injects no tyre failures
    assert trace.rival_pit.shape == (n_laps, n_cars) and trace.rival_pit.dtype == np.int8
    assert trace.rival_mode.shape == (n_laps, n_cars) and trace.rival_mode.dtype == np.int8
    assert trace.grid.shape == (n_cars,) and trace.grid.dtype.kind == "i"
    assert trace.driver_s.shape == (n_cars,) and trace.driver_s.dtype.kind == "f"

    # the env's twin check is the real acceptance test: a trace it refuses is not a trace
    env.reset(seed=SEED, options={"twin": trace})


def test_status_digits_map_to_the_right_states(make_env):
    scenario = make_env(CIRCUIT, ERA).scenario
    real_total_laps = scenario.total_laps
    digits = {10: "4", 20: "6", 21: "7", 30: "5"}
    laps_by_driver = {
        driver: _driver_laps(real_total_laps, status_by_lap=digits)
        for driver in ("VER", "HAM", "LEC")
    }

    trace = _synthesize(
        scenario, laps_by_driver, {"VER": 1, "HAM": 2, "LEC": 3},
        real_total_laps=real_total_laps,
    )

    assert trace.status[9] == events.SC
    assert trace.status[19] == events.VSC
    assert trace.status[20] == events.VSC  # 6 and 7 are both virtual safety car (E-03)
    assert trace.status[29] == events.RED
    assert bool(trace.red_flag[29]) is True
    assert trace.status[0] == events.GREEN
    assert not trace.red_flag[[0, 9, 19, 20]].any()


def test_real_laps_rescale_onto_the_sim_distance(make_env):
    scenario = make_env(CIRCUIT, ERA).scenario
    real_total_laps = 70  # a longer real race than the sim distance for this circuit
    out_laps = (21, 46)
    laps_by_driver = {
        driver: _driver_laps(real_total_laps, out_laps=out_laps)
        for driver in ("VER", "HAM", "LEC", "NOR")
    }

    trace = _synthesize(
        scenario, laps_by_driver, {"VER": 1, "HAM": 2, "LEC": 3, "NOR": 4},
        real_total_laps=real_total_laps,
    )

    # the trace marks the out-lap the rival rejoined on, rescaled onto the sim distance
    stop_laps = set((np.flatnonzero((trace.rival_pit >= 0).any(axis=1)) + 1).tolist())
    expected = {round(lap * scenario.total_laps / real_total_laps) for lap in out_laps}
    assert stop_laps == expected
    assert all(1 <= lap <= trace.n_laps for lap in stop_laps)


def test_pit_lane_and_short_fields_are_placed_at_the_back(make_env):
    scenario = make_env(CIRCUIT, ERA).scenario
    n_cars = scenario.grid_size
    real_total_laps = scenario.total_laps

    # cars are indexed in laps_by_driver order, so the harness can say which car is whom
    drivers = [f"D{i:02d}" for i in range(n_cars)]
    full_field = {driver: _driver_laps(real_total_laps) for driver in drivers}
    # D00 started from the pit lane; the rest line up 1..19
    full = _synthesize(
        scenario, full_field, {driver: i for i, driver in enumerate(drivers)},
        real_total_laps=real_total_laps,
    )

    assert sorted(full.grid.tolist()) == list(range(1, n_cars + 1))
    assert full.grid[0] == n_cars
    assert full.grid[1:].tolist() == list(range(1, n_cars))

    short_drivers = ("VER", "HAM", "LEC", "NOR", "RUS")
    short = _synthesize(
        scenario,
        {driver: _driver_laps(real_total_laps) for driver in short_drivers},
        {"VER": 1, "HAM": 2, "LEC": 3, "NOR": None, "RUS": 5},
        real_total_laps=real_total_laps,
    )

    slots = short.grid.tolist()
    assert short.n_cars == n_cars  # padded to a full field, so the env still accepts it
    assert sorted(slots) == list(range(1, n_cars + 1))
    assert slots[0] == 1
    assert slots[0] < slots[1] < slots[2] < slots[4]  # classified starters keep their order
    assert slots[3] > slots[4]  # the pit-lane start falls behind every classified starter


def test_a_circuit_without_native_2024_fits_is_refused():
    # build_scenario falls back to the 2026 joint-pace and degradation fits where a circuit
    # has no 2024 ones, and would hand back a "2024" scenario running 2026 physics — an
    # era-matched counterfactual built on that is a mislabelled comparison, not a coarse one
    require_native_era_fits(CIRCUIT, ERA)

    with pytest.raises(ValueError, match="canadian_grand_prix"):
        require_native_era_fits("canadian_grand_prix", ERA)
