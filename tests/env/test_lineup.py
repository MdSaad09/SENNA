"""Named seats: who is driving, and what that does to the race (F17).

Until now every car on the grid was the same driver with a different random number. A
lineup replaces that number for the seats it knows, and leaves the draw alone everywhere
else — which is the whole design, because the alternative moves every seeded race in the
repo. `reset` draws `N(0, sigma_driver_s)` for all twenty-two seats exactly as it always
has and then overwrites the named ones, so `drivers=None` is byte-identical by
construction and an unnamed seat keeps a real offset rather than quietly becoming the best
car on the grid at zero.

The table these tests read is `tests/env/fixtures/driver_table.py`, not the generated
`configs/drivers.yaml`: the real one is a fit, and a test pinned to a fit moves whenever
the physics is refitted.

Two private reads appear below, `env._state` and `env._rivals`. Neither has a public
accessor and both are the behaviour under test — the seat offsets a reset installed, and
the archetype the field draw handed a named seat — so they are read the way
tests/env/test_engine_identity.py reads `_state`, rather than inferred from a proxy.
"""

from collections import Counter
from dataclasses import replace

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from senna.env import F1RaceEnv, dynamics
from senna.env.dynamics import BALANCED
from senna.env.engine import LapDecisions, advance_lap, begin_lap
from senna.env.events_io import STAY_OUT, LiveSource
from senna.env.scenario import START_COMPOUND, build_scenario, compound_code
from tests.env.conftest import CIRCUIT, SEED
from tests.env.fixtures.driver_table import (
    DEG_MULT,
    FAST,
    HEAVY_WEAR,
    SEAT_PACE_MEAN_S,
    SEAT_PACE_S,
    SLOW,
    UNKNOWN,
)
from tests.env.fixtures.generate_f16_golden import PINNED_CONFIGS
from tests.env.test_engine_identity import RecordingRng

ERA = "2026"
THIN_CIRCUIT = "monaco_grand_prix"  # where the fixture's FAST seat has no fitted cell

RACES = 600  # operational: a third of a second per example, and enough draws that the
             # uniformity band below sits four standard errors from a third


@pytest.fixture
def named_scenario(driver_configs):
    """Built once and reused across the hypothesis examples below: parsing the fitted
    physics is the whole cost of this file, and it does not vary with the generated
    multipliers."""
    return build_scenario(CIRCUIT, ERA, drivers=[FAST, SLOW], configs_dir=driver_configs)


def _race_to_the_flag(env, *, seed):
    """Every seat to the flag on the identical decision every lap: stay out, hold balanced.

    The engine enforces no sporting rule — legality is the adapter's job (senna/env/
    CLAUDE.md) — and what this needs is a field with no strategy in it at all, so that a
    finishing order can only be about pace. Events are deterministic and the pace noise is
    switched off for the same reason: at one race, per-lap scatter would swamp the effect
    under test rather than average out of it.
    """
    scenario = env.scenario
    state = env._state
    rng = np.random.default_rng(seed)
    source = LiveSource(scenario, sigma_mult=np.zeros(state.n_cars), hazards="none",
                        weather="dry")
    stay_out = LapDecisions(pit=np.full(state.n_cars, STAY_OUT),
                            mode=np.full(state.n_cars, BALANCED))

    while state.lap < scenario.total_laps:
        context = begin_lap(state, rng, source=source, lap_index=state.lap)
        advance_lap(state, context, stay_out, scenario, rng, source=source, sink=None)
    return state


def test_a_default_scenario_never_reads_the_driver_table():
    """tests/env/fixtures/pinned_configs/ holds no drivers.yaml and must never need one.
    Its README warns about exactly this: a config `build_scenario` loads unconditionally
    but which is absent there raises FileNotFoundError, which is why ablations.yaml is
    kept out of the default path too. The F16 golden replay is what breaks, and that
    replay is F17's identity gate rather than a formality."""
    scenario = build_scenario(CIRCUIT, ERA, drivers=None, configs_dir=PINNED_CONFIGS)

    assert scenario.lineup is None


def test_a_named_lineup_consumes_the_same_variates(driver_configs, monkeypatch):
    """Reset draws the grid, then the driver offsets, then the rival field. F16's lesson is
    that removing the middle draw moves every seeded race in the repo — the frozen model's
    evaluation, the Stage B traces, F14 — so a named lineup draws anyway and overwrites
    afterwards. Then a named race and the same-seed unnamed race are the same race with
    different people in it, which is also what makes the unnamed-seat fallback free."""
    plain = F1RaceEnv(CIRCUIT, ERA, configs_dir=driver_configs)
    named = F1RaceEnv(CIRCUIT, ERA, drivers=[FAST, SLOW], configs_dir=driver_configs)

    recorders = []
    default_rng = np.random.default_rng

    def recording(seed):
        recorders.append(RecordingRng(default_rng(seed)))
        return recorders[-1]

    monkeypatch.setattr(np.random, "default_rng", recording)
    plain.reset(seed=SEED)
    named.reset(seed=SEED)

    unnamed_draws, named_draws = (recorder.draws for recorder in recorders)
    assert unnamed_draws  # the recorder must have seen the reset, or this proves nothing
    assert named_draws == unnamed_draws
    # and the reason to draw anyway rather than skip: the seat moved, the stream did not
    assert named._state.driver_s[0] != plain._state.driver_s[0]


def test_a_named_lineup_seeds_the_fitted_offsets(driver_configs):
    env = F1RaceEnv(CIRCUIT, ERA, drivers=[FAST, SLOW, HEAVY_WEAR], configs_dir=driver_configs)

    env.reset(seed=SEED)

    seats = (FAST, SLOW, HEAVY_WEAR)
    fitted_s = [SEAT_PACE_S[ERA][code][CIRCUIT] for code in seats]
    assert env._state.driver_s[:3].tolist() == pytest.approx(fitted_s)
    # each seat says which rung of the ladder it came from, so a reader can tell a
    # measured seat from an inferred one without rerunning the fit
    assert env.scenario.lineup.levels[:3] == ("circuit", "circuit", "circuit")
    assert env.scenario.lineup.deg_mult[2] == pytest.approx(DEG_MULT[ERA][HEAVY_WEAR])


def test_an_unnamed_seat_falls_back_to_the_draw(driver_configs):
    """A code the table has never heard of, and eighteen seats past the end of the lineup.
    Not zero: every fitted offset is centred on zero, so a seat pinned at exactly zero is
    a seat at the field average, and on a grid whose average is the fastest thing there is
    that quietly makes an unknown driver the best car on it."""
    named = F1RaceEnv(CIRCUIT, ERA, drivers=[FAST, UNKNOWN], configs_dir=driver_configs)
    plain = F1RaceEnv(CIRCUIT, ERA, configs_dir=driver_configs)

    named.reset(seed=SEED)
    plain.reset(seed=SEED)

    assert named._state.driver_s[0] == pytest.approx(SEAT_PACE_S[ERA][FAST][CIRCUIT])
    # the unknown code and every seat past the lineup keep the value this seed drew for
    # them — a named race is the unnamed race plus identity, not a different race
    assert named._state.driver_s[1:].tolist() == pytest.approx(plain._state.driver_s[1:].tolist())
    assert named._state.driver_s[1] != 0.0
    assert named.scenario.lineup.levels[1] == "drawn"
    assert named.scenario.lineup.deg_mult[1] == 1.0


def test_a_solo_race_takes_the_named_seat(driver_configs):
    """F07 Stage A runs a one-car grid. `build_scenario` does not know about `solo`, so the
    lineup is resolved at the full grid width and the one-car race reads a prefix of it —
    which is only correct because the ego is seat 0. Pinned here because the slice is
    otherwise a silent contract: widen it to a suffix and every twenty-two-car test still
    passes while a solo race quietly drives on the last seat's tyres."""
    env = F1RaceEnv(CIRCUIT, ERA, solo=True, drivers=[HEAVY_WEAR], configs_dir=driver_configs)

    env.reset(seed=SEED)

    assert env.n_cars == 1
    assert env._state.driver_s[0] == pytest.approx(SEAT_PACE_S[ERA][HEAVY_WEAR][CIRCUIT])
    # and the tyre style reaches the lap-time model for that one car, not seat 21's
    assert env.scenario.lineup.deg_mult[0] == pytest.approx(DEG_MULT[ERA][HEAVY_WEAR])


def test_a_thin_circuit_falls_back_to_the_driver_mean(driver_configs):
    """The fixture's FAST seat has no Monaco cell, because a cell below
    min_laps_for_seat_pace is not published rather than published noisily (E-10). The seat
    still gets a number — that driver's own lap-weighted mean over the circuits that did
    clear the gate — and the level records which rung answered."""
    env = F1RaceEnv(THIN_CIRCUIT, ERA, drivers=[FAST, SLOW], configs_dir=driver_configs)

    env.reset(seed=SEED)

    assert env.scenario.lineup.levels[:2] == ("driver_mean", "circuit")
    assert env._state.driver_s[0] == pytest.approx(SEAT_PACE_MEAN_S[ERA][FAST])
    assert env._state.driver_s[1] == pytest.approx(SEAT_PACE_S[ERA][SLOW][THIN_CIRCUIT])


def test_a_faster_driver_finishes_ahead_on_equal_strategy(driver_configs):
    """The end-to-end statement that identity reaches the result: two seats, the same
    decision on every lap, differing only in the seat pace the table gave them."""
    env = F1RaceEnv(CIRCUIT, ERA, drivers=[FAST, SLOW], configs_dir=driver_configs)
    env.reset(seed=SEED)

    state = _race_to_the_flag(env, seed=SEED)

    assert state.positions()[0] < state.positions()[1]
    gap_s = state.cumulative_time_s[1] - state.cumulative_time_s[0]
    pace_gap_s = SEAT_PACE_S[ERA][SLOW][CIRCUIT] - SEAT_PACE_S[ERA][FAST][CIRCUIT]
    # every lap, not once at the start: an offset installed at reset and then dropped from
    # the lap-time model would show up here as a gap two orders of magnitude too small
    assert gap_s == pytest.approx(pace_gap_s * env.total_laps, rel=0.2)


def test_the_table_s_multiplier_reaches_the_lap_time(driver_configs):
    """The chain the property test below does not cover: table -> resolve -> scenario ->
    lap_time_s. That one hand-builds a deg_mult array and injects it with `replace`, so it
    proves the multiplication happens and nothing about whose multiplier arrives. Neuter
    the lookup entirely and it stays green; this goes red.

    HEAVY_WEAR is the only fixture seat carrying a fitted multiplier away from 1.0, so on
    the same worn tyre it must lose time to a seat on the pooled curve, and on a fresh set
    the two must be identical — T5's form is unchanged, so age zero costs nobody anything.
    """
    scenario = build_scenario(CIRCUIT, ERA, drivers=[SLOW, HEAVY_WEAR],
                              configs_dir=driver_configs)
    n = scenario.grid_size
    modes = np.full(n, BALANCED)
    request_mj = dynamics.deploy_request_mj(modes, scenario)

    def lap_s(age):
        return dynamics.lap_time_s(
            compound=np.full(n, compound_code(START_COMPOUND)), age=np.full(n, age),
            fuel_kg=np.full(n, scenario.race_fuel_kg), modes=modes,
            delivered_mj=request_mj, request_mj=request_mj, derate_s=np.zeros(n),
            gap_ahead_s=np.full(n, scenario.dirty_air_threshold_s), wetness=0.0,
            track_status=np.zeros(n, dtype=int), driver_s=np.zeros(n),
            noise_s=np.zeros(n), scenario=scenario,
        )

    assert scenario.lineup.deg_mult[1] == pytest.approx(DEG_MULT[ERA][HEAVY_WEAR])
    assert lap_s(20)[1] > lap_s(20)[0]  # the harsher seat pays for a worn set
    assert lap_s(0)[1] == pytest.approx(lap_s(0)[0])  # and nothing for a fresh one


@pytest.mark.property
@given(
    # a published multiplier outside this range would be a fit nobody would ship: it says
    # a driver wears a set at half or double the field's rate
    gentle=st.floats(min_value=0.5, max_value=1.4),
    step=st.floats(min_value=0.05, max_value=0.5),
    age=st.integers(min_value=1, max_value=35),
)
@settings(max_examples=50, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_tyre_management_lengthens_the_useful_stint(named_scenario, gentle, step, age):
    """Direction, not magnitude. A gentler multiplier costs less lap time at any given tyre
    age, so it reaches any given lap time later — which is what "lengthens the useful
    stint" means in an engine whose stint length is a decision rather than a limit. T5's
    form is unchanged: the multiplier scales the fitted amplitude `a`, so a fresh tyre
    still costs nothing whoever is driving it."""
    scenario = named_scenario
    n = scenario.grid_size
    deg_mult = np.ones(n)
    # two seats at the age under test, two on a fresh set, gentle against harsh in each pair
    deg_mult[[0, 2]] = gentle
    deg_mult[[1, 3]] = gentle + step
    scenario = replace(scenario, lineup=replace(scenario.lineup, deg_mult=deg_mult))

    modes = np.full(n, BALANCED)
    request_mj = dynamics.deploy_request_mj(modes, scenario)
    lap_s = dynamics.lap_time_s(
        compound=np.full(n, compound_code(START_COMPOUND)),
        age=np.where(np.arange(n) < 2, age, 0),
        fuel_kg=np.full(n, scenario.race_fuel_kg),
        modes=modes,
        delivered_mj=request_mj,
        request_mj=request_mj,
        derate_s=np.zeros(n),
        gap_ahead_s=np.full(n, scenario.dirty_air_threshold_s),  # nobody in traffic
        wetness=0.0,
        track_status=np.zeros(n, dtype=int),
        driver_s=np.zeros(n),
        noise_s=np.zeros(n),
        scenario=scenario,
    )

    assert lap_s[1] > lap_s[0]
    assert lap_s[3] == pytest.approx(lap_s[2])


@pytest.mark.property
@given(base_seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=3, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_archetype_assignment_is_independent_of_driver_identity(driver_configs, base_seed):
    """The M1 guard, and the test least obvious to a reader in six months.

    senna/env/rivals.py records a deliberate choice: archetypes carry no mean pace offset,
    because tying strategy style to car pace would confound the paired-baseline metric.
    Driver identity threatens exactly that. If the fastest seat were also systematically
    the undercutter, M1 could no longer tell a better strategy from a better car, and every
    number in the F14 chapter that rests on it would move. So the archetype draw must not
    consult the driver table at any seed, and a later feature that wants "Verstappen is
    aggressive *and* fast" has to argue with M1 before it argues with this test.
    """
    named = F1RaceEnv(CIRCUIT, ERA, drivers=[FAST, SLOW, HEAVY_WEAR],
                      configs_dir=driver_configs)
    plain = F1RaceEnv(CIRCUIT, ERA, configs_dir=driver_configs)
    seeds = np.random.default_rng(base_seed).integers(0, 2**31, size=RACES)

    styles = Counter()
    for seed in seeds:
        named.reset(seed=int(seed))
        plain.reset(seed=int(seed))
        assert np.array_equal(named._rivals.archetype, plain._rivals.archetype)
        styles[int(named._rivals.archetype[1])] += 1  # the seat SLOW is named into

    assert len(styles) == 3  # every archetype reaches the seat
    # deliberately loose: this is a statement about the shape of the draw, not a precision
    # claim. The exact equality above is what bites; the band only catches a table that
    # skews the field without touching the stream.
    for races in styles.values():
        assert 0.24 <= races / RACES <= 0.43
