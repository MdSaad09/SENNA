"""Byte-identical replay through the extracted seam (F16). The extraction moves call
sites; it may not move a formula or a variate. Two instruments hold it to that: a recorder
that writes down every draw the tick asks for, and a golden trace recorded on the code as
it stood before the refactor.

The draw order *is* the seed (5.5.5). Move a call earlier, or draw one array of twenty-two
where the old code drew twenty-two scalars in a Python loop, and every race at every seed
changes silently. That is the failure this suite exists to localise, so run
`test_rng_draw_order_preserved` first and treat the golden trace as the bisect tool.

The fixture's seed, circuits, field list and ego strategy are imported from the script that
recorded it (tests/env/fixtures/generate_f16_golden.py, run before the extraction), so the
replay here cannot drift from the photograph it is compared against.
"""

import time
from pathlib import Path

import numpy as np
import pytest

from senna import config
from senna.env import F1RaceEnv, events, rivals
from senna.env.dynamics import BALANCED
from senna.env.engine import LapDecisions, advance_lap, begin_lap
from senna.env.events_io import LiveSource
from senna.env.scenario import COMPOUNDS, START_COMPOUND, build_scenario, compound_code
from senna.env.state import RaceState
from tests.env.fixtures.generate_f16_golden import (
    CIRCUITS,
    FIELDS,
    PINNED_CONFIGS,
    SEED,
    ego_action,
)

ERA = "2026"
RIVAL_BAND = "train"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# three dataclass allocations per lap (LapContext, LapDecisions, LapOutcome) over a ~60-lap
# race is under a tenth of a percent of the 18,477 steps/s the 5.6.2 benchmark measured, so
# 5% is a smoke alarm with two orders of headroom rather than a squeeze
THROUGHPUT_TOLERANCE = 0.05
TIMED_RACES = 300  # operational: ~17,000 laps a side, a couple of seconds of wall clock
                   # at the measured single-process rate — long enough that a 5% shortfall
                   # reads through timer noise, short enough to stay a smoke alarm


class RecordingRng:
    """A numpy Generator that writes down every draw it is asked for, as (method, shape).

    Nothing else about the stream changes: each call is forwarded and its result returned,
    so a race driven through this recorder is the race the bare generator would have run.
    """

    def __init__(self, rng):
        self._rng = rng
        self.draws: list[tuple[str, tuple]] = []

    def __getattr__(self, name):
        attr = getattr(self._rng, name)
        if not callable(attr):
            return attr

        def record(*args, **kwargs):
            value = attr(*args, **kwargs)
            self.draws.append((name, np.shape(value)))
            return value

        return record


def _grid_state(scenario, n_cars, *, grid, driver_s) -> RaceState:
    """The starting state reset() builds, from the same two draws in the same order."""
    start = compound_code(START_COMPOUND)
    return RaceState(
        n_cars=n_cars,
        lap=0,
        compound=np.full(n_cars, start),
        tyre_age=np.zeros(n_cars, dtype=int),
        soc_mj=np.full(n_cars, scenario.usable_soc_mj),
        fuel_kg=np.full(n_cars, scenario.race_fuel_kg),
        cumulative_time_s=(grid - 1) * 1e-3,
        grid_position=grid,
        pit_count=np.zeros(n_cars, dtype=int),
        second_compound_used=np.zeros(n_cars, dtype=bool),
        first_compound=np.full(n_cars, start),
        last_harvest_mj=np.zeros(n_cars),
        last_deploy_mj=np.zeros(n_cars),
        retired=np.zeros(n_cars, dtype=bool),
        driver_s=driver_s,
        track_status=events.GREEN,
        status_laps_left=0,
        weather=events.DRY,
        wetness=0.0,
        red_flags_seen=0,
        red_flag_now=False,
        ego=0,
    )


def _max_age_by_code(scenario) -> np.ndarray:
    fallback = scenario.env["obs"]["tyre_age_norm_laps"]
    return np.array([scenario.deg_max_age.get(name, fallback) for name in COMPOUNDS])


def _unwatched(_phase, _state) -> None:
    pass


def _drive_field_race(scenario, n_cars, rng, *, book, watch=_unwatched):
    """A full race through the engine, driven the way the adapter drives it: rivals fill
    every seat — the ego's included, so no seat is decided differently from any other — and
    each lap resolves the track before the field commits to it.

    `watch(phase, state)` is called after "grid" and then after "begin_lap", "decide" and
    "advance_lap" on every lap, so a caller can look at the state or at what was drawn
    without the driver knowing why.
    """
    grid = rng.permutation(n_cars) + 1
    driver_s = rng.normal(0.0, scenario.sigma_driver_s, n_cars)
    state = _grid_state(scenario, n_cars, grid=grid, driver_s=driver_s)
    field = rivals.draw_field(book, RIVAL_BAND, n_cars=n_cars, ego=0, rng=rng)
    watch("grid", state)

    # the live source carries the drawn pace sigma, so it is built after the field is
    # drawn — per-lap noise has depended on the archetype mix since F06
    source = LiveSource(scenario, sigma_mult=field.sigma_mult)
    max_age_by_code = _max_age_by_code(scenario)
    validity = scenario.env["compound_validity"]

    while state.lap < scenario.total_laps:
        context = begin_lap(state, rng, source=source, lap_index=state.lap)
        watch("begin_lap", state)

        decisions = LapDecisions(
            pit=rivals.pit_choices(
                book, field, state, status_onset=context.onset, red_flag=context.red_flag,
                max_age_by_code=max_age_by_code, validity=validity,
                total_laps=scenario.total_laps, rng=rng,
            ),
            mode=np.full(n_cars, BALANCED),
        )
        watch("decide", state)

        advance_lap(state, context, decisions, scenario, rng, source=source, sink=None)
        watch("advance_lap", state)

    return state


def _snapshot(state) -> dict:
    """The seven fixture arrays, copied out of the live field."""
    return {
        name: state.positions() if name == "positions" else getattr(state, name).copy()
        for name in FIELDS
    }


def test_rng_draw_order_preserved():
    """The six draw sites, in the order F1RaceEnv has consumed them since F05: the track
    status, the weather chain, the rivals' safety-car response, the per-car tyre-failure
    hazard, the field's pace noise, then pit service for whoever is stopping.

    The test drives the two phases itself, so every draw is attributed to the phase that
    made it and no site can hide behind another with the same shape.
    """
    scenario = build_scenario(CIRCUITS[0], ERA, configs_dir=PINNED_CONFIGS)
    n_cars = scenario.grid_size
    rng = RecordingRng(np.random.default_rng(SEED))
    book = rivals.load_book(PINNED_CONFIGS, validity=scenario.env["compound_validity"])
    per_lap = []

    def watch(phase, _state):
        if phase == "grid":
            rng.draws.clear()  # reset's own draws are not part of the tick
            return
        if phase == "begin_lap":
            per_lap.append({})
        per_lap[-1][phase] = list(rng.draws)
        rng.draws.clear()

    _drive_field_race(scenario, n_cars, rng, book=book, watch=watch)

    for lap in per_lap:
        opening = [name for name, _ in lap["begin_lap"]]
        # the status roll is skipped while a neutralisation counts down; the weather chain
        # runs every lap and always after it
        assert opening in (["choice"], ["random", "choice"])
        assert all(shape == () for name, shape in lap["begin_lap"] if name == "random")

        # the safety-car response: one field-wide draw made while the field decides, and
        # only on an onset lap
        deciding = lap["decide"]
        assert [name for name, _ in deciding] in ([], ["random"])
        assert all(shape == (n_cars,) for _, shape in deciding)

        running = lap["advance_lap"]
        names = [name for name, _ in running]
        noise = names.index("normal")
        # the tyre-failure hazard rolls per car, in a Python loop: vectorising it would
        # appear here as a single draw of shape (n_cars,) and move every seed's race
        assert names[:noise] == ["random"] * noise
        assert all(shape == () for _, shape in running[:noise])
        # then pace noise for the whole field, then pit service for the cars stopping
        assert running[noise][1] == (n_cars,)
        assert names[noise + 1:] in ([], ["normal"])

    # a race that never neutralised, never failed a tyre and never pitted anybody would
    # pass the loop above without exercising three of the six sites
    assert any(len(lap["begin_lap"]) == 2 for lap in per_lap)
    assert any(lap["decide"] for lap in per_lap)
    assert any(name == "random" for lap in per_lap for name, _ in lap["advance_lap"])
    assert any(
        [name for name, _ in lap["advance_lap"]].count("normal") == 2 for lap in per_lap
    )


@pytest.mark.parametrize("circuit", CIRCUITS)
def test_golden_trace_identical(circuit):
    """Every car, every lap, exactly the race the pre-refactor code ran. Equality, not
    closeness: a drift of one ulp means a draw moved, and a moved draw is a different
    championship.

    The replay is driven through F1RaceEnv because the recorded strategy includes requests
    the mask snapped, and coercion stays the adapter's job after the extraction (F-16).
    What the engine owes is everything downstream of the executed decision.
    """
    env = F1RaceEnv(circuit, ERA, configs_dir=PINNED_CONFIGS)
    env.reset(seed=SEED)
    state = env._state  # the fixture is the whole field, not the ego's observation
    rows = [_snapshot(state)]

    for lap in range(env.total_laps):
        _, _, terminated, _, _ = env.step(ego_action(lap))
        rows.append(_snapshot(state))
        if terminated:
            break

    with np.load(FIXTURES / f"F16_golden_{circuit}.npz") as golden:
        for name in FIELDS:
            replayed = np.array([row[name] for row in rows])
            assert replayed.shape == golden[name].shape, name
            assert np.array_equal(replayed, golden[name]), name


def _engine_laps_per_s(scenario, book) -> float:
    rng = np.random.default_rng(SEED)
    start = time.perf_counter()
    for _ in range(TIMED_RACES):
        _drive_field_race(scenario, scenario.grid_size, rng, book=book)
    return TIMED_RACES * scenario.total_laps / (time.perf_counter() - start)


def _env_steps_per_s(circuit) -> float:
    env = F1RaceEnv(circuit, ERA)
    steps = 0
    start = time.perf_counter()
    for _ in range(TIMED_RACES):
        env.reset(seed=SEED)
        terminated = False
        for lap in range(env.total_laps):
            _, _, terminated, _, _ = env.step(ego_action(lap))
            steps += 1
            if terminated:
                break
    return steps / (time.perf_counter() - start)


@pytest.mark.slow
def test_an_engine_lap_costs_less_than_an_env_step():
    """A coarse alarm, not the 5.6.2 gate — read the name literally.

    The 5.6.2 reading is stamped with hardware, commit and config hash precisely so it is
    never read out of context, so nothing portable can assert "within 5% of 18,477". What
    this does assert is a ratio on whatever machine is running: an engine lap does strictly
    less work than the env step wrapping it — no reward, no observation, no mask, no info
    dict — so an engine lap costing more than a whole env step means the extraction's own
    per-lap cost swallowed everything it removed. Measured slack is large (the real ratio
    is about 1.5), so this fires only on a catastrophic regression. A true before/after
    comparison needs `make bench` run on both commits by hand.
    """
    circuit = CIRCUITS[0]
    scenario = build_scenario(circuit, ERA)
    book = rivals.load_book(validity=scenario.env["compound_validity"])

    engine_laps_s = _engine_laps_per_s(scenario, book)
    env_steps_s = _env_steps_per_s(circuit)

    assert env_steps_s > config.load("baselines")["bench"]["min_steps_s"]
    assert engine_laps_s >= (1.0 - THROUGHPUT_TOLERANCE) * env_steps_s
