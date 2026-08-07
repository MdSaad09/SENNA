"""The race engine (F16): one lap of a Formula 1 race advanced without a learning agent.

`begin_lap` resolves what the track is doing before anyone decides; `advance_lap` runs the
lap the whole field committed to. Neither knows about rewards, observations, masks or an
ego seat, and that inversion is what this suite pins. The transition physics of 5.5.3 does
not change with the extraction, so tests/env/test_dynamics.py still owns the formulas and
tests/env/test_engine_identity.py owns the byte-identical replay.

Nothing in this file constructs F1RaceEnv. That is deliberate: if a test here needs the
Gymnasium adapter, the inversion did not happen.

Suite seed 616, clear of the env suite's 512 and the twin suite's 704 (5.5.5).
"""

import ast
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from senna.env import events
from senna.env.dynamics import BALANCED
from senna.env.engine import LapDecisions, advance_lap, begin_lap
from senna.env.events_io import LiveSource, TraceSink, TraceSource
from senna.env.scenario import START_COMPOUND, build_scenario, compound_code
from senna.env.state import RaceState
from senna.env.twin import EventTrace

SEED = 616
CIRCUIT = "bahrain_grand_prix"
ERA = "2026"
FULL_GRID = 22
SOLO = 1  # F07 Stage A: draw_field returns an empty non-ego set, so the tick must not
          # assume a car has neighbours
STAY_OUT = -1
HARD = compound_code("HARD")

ENGINE_MODULE = Path(__file__).resolve().parents[2] / "senna" / "env" / "engine.py"
# the engine advances a race, so it may not reach for the agent's half of the world
# (F16 done-means: no gym, SB3, reward or observation import); pandas is the senna/
# hot-loop ban that the 5.6.2 throughput gate rests on
BANNED_IMPORTS = (
    "gymnasium", "stable_baselines3", "sb3_contrib", "pandas",
    "senna.env.reward", "senna.env.reward_v2", "senna.env.observation",
)

# seat i boxes on STOP_LAPS[i % 3]: a real queue in the pit lane (E-05) without the whole
# field arriving on the same lap
STOP_LAPS = (16, 17, 18)
SEAT = 5
SEAT_STOP_LAP = 20

# a track that changes under the field: four laps of safety car, then rain that never dries
NEUTRALISED_LAPS = slice(10, 14)
RAIN_FROM_LAP = 20
RAIN_WETNESS = 0.6


def _grid_state(scenario, n_cars, *, ego=0) -> RaceState:
    """The field on the grid — reset()'s starting state with the drawn parts pinned, so a
    test controls exactly what differs between two races."""
    grid = np.arange(1, n_cars + 1)
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
        driver_s=np.zeros(n_cars),
        track_status=events.GREEN,
        status_laps_left=0,
        weather=events.DRY,
        wetness=0.0,
        red_flags_seen=0,
        red_flag_now=False,
        ego=ego,
    )


def _live_source(scenario, n_cars):
    """The live event path: rolled hazards and weather, the per-car failure hazard, drawn
    pace noise and pit service. Unit pace sigma for every car, so the field is separated by
    what it decides rather than by which archetype it drew."""
    return LiveSource(scenario, sigma_mult=np.ones(n_cars))


def _trace_source(trace, scenario, n_cars):
    """The twin's half of the seam: every event read from the trace instead of drawn."""
    return TraceSource(trace, scenario, n_cars=n_cars)


def _recording_sink(scenario, state):
    """A sink over a fresh trace, and the trace it fills — record=True's half of the seam."""
    trace = EventTrace.green(
        CIRCUIT, ERA, scenario.total_laps, state.n_cars,
        grid=state.grid_position, driver_s=state.driver_s,
    )
    return TraceSink(trace), trace


def _scripted_trace(scenario, n_cars, grid):
    """An all-green trace edited so the track visibly changes lap to lap. A decision that
    read last lap's status or weather would be wrong on every flip lap."""
    trace = EventTrace.green(CIRCUIT, ERA, scenario.total_laps, n_cars, grid=grid)
    trace.status[NEUTRALISED_LAPS] = events.SC
    trace.weather[RAIN_FROM_LAP:] = events.WET
    trace.wetness[RAIN_FROM_LAP:] = RAIN_WETNESS
    return trace


def _stay_out(n_cars) -> LapDecisions:
    """Nobody boxes, everybody runs balanced. `pit` carries the compound code a car boxes
    to, or -1 to stay out — the field-wide shape, with no seat singled out."""
    return LapDecisions(pit=np.full(n_cars, STAY_OUT), mode=np.full(n_cars, BALANCED))


def _everyone_stays_out(state, _context) -> LapDecisions:
    return _stay_out(state.n_cars)


def _one_stop_each(state, _context) -> LapDecisions:
    """Every car serves one stop for HARD, staggered by seat."""
    seats = np.arange(state.n_cars)
    boxing = np.array([STOP_LAPS[seat % len(STOP_LAPS)] == state.lap for seat in seats])
    return LapDecisions(
        pit=np.where(boxing, HARD, STAY_OUT), mode=np.full(state.n_cars, BALANCED)
    )


def _stop_at_seat_five(state, _context) -> LapDecisions:
    pit = np.full(state.n_cars, STAY_OUT)
    if state.lap == SEAT_STOP_LAP:
        pit[SEAT] = HARD
    return LapDecisions(pit=pit, mode=np.full(state.n_cars, BALANCED))


def _watch_the_track(seen):
    """A decision function that writes down what the track looked like when it was asked,
    and boxes nobody."""

    def decide(state, _context) -> LapDecisions:
        seen.append((int(state.track_status), int(state.weather), float(state.wetness)))
        return _stay_out(state.n_cars)

    return decide


def _drive_to_flag(state, scenario, rng, *, source, decide, sink=None) -> RaceState:
    """The two-phase tick, lap after lap: resolve the track, collect the field's decisions,
    run the lap. Observe the track, everyone commits, the lap runs — the order a real race
    happens in and the reason the interface is two calls rather than one."""
    while state.lap < scenario.total_laps:
        context = begin_lap(state, scenario, rng, source=source, lap_index=state.lap)
        decisions = decide(state, context)
        advance_lap(state, context, decisions, scenario, rng, source=source, sink=sink)
    return state


def test_engine_imports_no_gym():
    """The tick may not import the agent's half of the world. Read as imports rather than
    as file text, in the style of the R-04 guard, because the module docstring is entitled
    to say out loud that it knows nothing about Gymnasium."""
    tree = ast.parse(ENGINE_MODULE.read_text())

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)

    offenders = sorted(
        name for name in imported
        if any(name == banned or name.startswith(f"{banned}.") for banned in BANNED_IMPORTS)
    )
    assert offenders == []

    subclassed = [
        ast.unparse(base)
        for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        for base in node.bases
    ]
    assert [base for base in subclassed if base.endswith("Env")] == []


@pytest.mark.parametrize("n_cars", [SOLO, FULL_GRID], ids=["solo", "full_grid"])
def test_advance_without_reward(n_cars):
    """A race runs to the flag on begin_lap and advance_lap alone, and classifies a field —
    no reward, no observation, no mask, no agent anywhere in the loop."""
    scenario = build_scenario(CIRCUIT, ERA)
    state = _grid_state(scenario, n_cars)

    _drive_to_flag(
        state, scenario, np.random.default_rng(SEED),
        source=_live_source(scenario, n_cars), decide=_one_stop_each,
    )

    assert state.lap == scenario.total_laps
    assert np.array_equal(np.sort(state.positions()), np.arange(1, n_cars + 1))
    assert not state.retired.all()
    assert np.all(state.pit_count >= 1)  # the stops the field decided on were served
    assert np.all(state.cumulative_time_s > scenario.t_ref_s)  # a race, not a lap


def test_decisions_are_field_wide():
    """One stop at seat 5 changes seat 5's race, and the caller never says which seat the
    agent is sitting in — the twenty-two-wide array is the whole interface."""
    scenario = build_scenario(CIRCUIT, ERA)

    baseline = _grid_state(scenario, FULL_GRID)
    _drive_to_flag(
        baseline, scenario, np.random.default_rng(SEED),
        source=_live_source(scenario, FULL_GRID), decide=_everyone_stays_out,
    )

    boxed = _grid_state(scenario, FULL_GRID)
    _drive_to_flag(
        boxed, scenario, np.random.default_rng(SEED),
        source=_live_source(scenario, FULL_GRID), decide=_stop_at_seat_five,
    )

    assert boxed.cumulative_time_s[SEAT] != baseline.cumulative_time_s[SEAT]
    # one track, one pit lane and one stream of draws: the stop is felt beyond seat 5
    others = np.arange(FULL_GRID) != SEAT
    assert (boxed.cumulative_time_s[others] != baseline.cumulative_time_s[others]).any()


@pytest.mark.parametrize("n_cars", [SOLO, FULL_GRID], ids=["solo", "full_grid"])
def test_two_phase_ordering(n_cars):
    """Decisions are collected between the two phases, so whoever makes them reads this
    lap's track status and weather rather than last lap's. This is the seam that makes the
    deferred mask-lag fix a one-line change later."""
    scenario = build_scenario(CIRCUIT, ERA)
    state = _grid_state(scenario, n_cars)
    trace = _scripted_trace(scenario, n_cars, state.grid_position)
    seen = []

    _drive_to_flag(
        state, scenario, np.random.default_rng(SEED),
        source=_trace_source(trace, scenario, n_cars), decide=_watch_the_track(seen),
    )

    this_lap = [
        (int(trace.status[lap]), int(trace.weather[lap]), float(trace.wetness[lap]))
        for lap in range(scenario.total_laps)
    ]
    assert seen == this_lap
    # the scripted track changes under the field, so reading it one lap late is visible
    assert seen != [this_lap[0], *this_lap[:-1]]


def test_event_source_round_trip():
    """A live race recorded into a sink replays through the source that reads it: the same
    track status, weather and wetness, lap for lap. The replay runs on a different seed, so
    an event that leaked out of the live stream instead of the trace would show.

    The recorded failures are not compared, because the twin deliberately recomputes the
    ego's row from its own tyre age (A-05) — what round-trips is the track, not that row.
    """
    scenario = build_scenario(CIRCUIT, ERA)

    live = _grid_state(scenario, FULL_GRID)
    sink, trace = _recording_sink(scenario, live)
    recorded = []
    _drive_to_flag(
        live, scenario, np.random.default_rng(SEED), source=_live_source(scenario, FULL_GRID),
        sink=sink, decide=_watch_the_track(recorded),
    )

    replay = _grid_state(scenario, FULL_GRID)
    replayed = []
    _drive_to_flag(
        replay, scenario, np.random.default_rng(SEED + 1),
        source=_trace_source(trace, scenario, FULL_GRID), decide=_watch_the_track(replayed),
    )

    assert replayed == recorded


def test_a_shape_mismatched_source_is_refused_at_construction():
    """A trace of the wrong shape would misreplay mid-race rather than fail loudly, so the
    source refuses it up front — the _check_twin guarantee, kept through the move."""
    scenario = build_scenario(CIRCUIT, ERA)
    short = EventTrace.green(
        CIRCUIT, ERA, scenario.total_laps - 1, FULL_GRID, grid=np.arange(1, FULL_GRID + 1)
    )

    with pytest.raises(ValueError, match="laps"):
        _trace_source(short, scenario, FULL_GRID)


@pytest.mark.property
@given(
    ego=st.integers(min_value=0, max_value=FULL_GRID - 1),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
@settings(max_examples=8, deadline=None)
def test_seat_symmetry(ego, seed):
    """On the live path no seat is privileged: the same seed and the same field-wide
    decisions produce the same twenty-two races whatever `state.ego` says. The ego is an
    indexing convenience for the adapter and a slot draw_field fills; the tick does not
    branch on it.

    The twin path is deliberately out of scope. Its ego row is recomputed from the ego's
    own tyre age so the field stays frozen while the strategy varies (A-05, F16 decision
    2), and covering both paths here would prove less than testing the live one honestly.
    """
    scenario = build_scenario(CIRCUIT, ERA)

    reference = _grid_state(scenario, FULL_GRID, ego=0)
    _drive_to_flag(
        reference, scenario, np.random.default_rng(seed),
        source=_live_source(scenario, FULL_GRID), decide=_one_stop_each,
    )

    moved = _grid_state(scenario, FULL_GRID, ego=ego)
    _drive_to_flag(
        moved, scenario, np.random.default_rng(seed),
        source=_live_source(scenario, FULL_GRID), decide=_one_stop_each,
    )

    for field in ("cumulative_time_s", "soc_mj", "compound", "tyre_age", "fuel_kg", "retired"):
        assert np.array_equal(getattr(reference, field), getattr(moved, field)), field
    assert np.array_equal(reference.positions(), moved.positions())
