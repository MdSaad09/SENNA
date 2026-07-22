"""reset(options={"grid_position": n}) pins the ego's slot for serving (F10): the API
maps SimulationCreate.grid_position through it. Additive on purpose — the twin path
keeps taking its grid verbatim from the trace.
"""

import numpy as np

from senna.env import F1RaceEnv
from senna.env.twin import EventTrace
from tests.env.conftest import CIRCUIT, SEED

# mediums with one mid-race stop to hard — the same completing line test_twin plays
ACTIONS = [[0, 1]] * 15 + [[3, 1]] + [[0, 1]] * 200


def _race_grid(seed: int, grid_position: int) -> np.ndarray:
    """Roll a full recorded race and read the grid off the public trace."""
    env = F1RaceEnv(CIRCUIT, "2026", record=True)
    env.reset(seed=seed, options={"grid_position": grid_position})
    terminated = False
    for action in ACTIONS:
        _, _, terminated, _, _ = env.step(np.array(action))
        if terminated:
            break
    assert terminated, "the fixed line must reach the flag for the trace to be readable"
    return env.recorded_trace().grid


def test_the_option_pins_the_ego_slot(make_env):
    for slot in (1, 7, 22):
        env = make_env()
        _, info = env.reset(seed=SEED, options={"grid_position": slot})
        assert info["position"] == slot  # lap-0 order is the grid


def test_the_rest_of_the_field_permutes_the_remaining_slots():
    grid = _race_grid(SEED, 7)
    assert grid[0] == 7  # ego is car 0
    assert sorted(grid) == list(range(1, len(grid) + 1))


def test_the_same_seed_and_pin_reproduce_the_same_grid():
    first = _race_grid(SEED, 7)
    assert first[0] == 7  # reproducing an unpinned grid would pass vacuously
    assert np.array_equal(first, _race_grid(SEED, 7))


def test_the_twin_path_still_takes_its_grid_from_the_trace():
    reference = F1RaceEnv(CIRCUIT, "2026")
    n = reference.n_cars
    grid = np.arange(1, n + 1)
    grid[0], grid[2] = 3, 1  # the trace puts the ego third

    trace = EventTrace.green(CIRCUIT, "2026", reference.total_laps, n, grid=grid)
    _, info = F1RaceEnv(CIRCUIT, "2026", twin=trace).reset(seed=SEED)
    assert info["position"] == 3
