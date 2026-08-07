"""One lap of a Formula 1 race, advanced without a learning agent (F16).

Before this module the tick lived inside `F1RaceEnv.step()`, which meant a lap could only
be advanced by something holding a Gymnasium action and willing to be handed a reward. The
race was a thing the agent did. Here it is the other way round: `advance_lap` takes the
state of twenty-two cars and the decision each of them made, and returns what happened.
Rewards, observations, masks and the idea of an ego seat all live one layer up, in the
adapter — this module imports none of them, and tests/env/test_engine.py enforces that.

The lap runs in two phases, which is both a design choice and how a race actually works:

    context = begin_lap(...)      # what is the track doing
    decisions = <everyone commits>
    outcome = advance_lap(...)    # the lap runs

Rivals already needed the neutralisation onset before they could choose (E-06), so the
seam has to open between resolving the track and collecting decisions. A consequence worth
knowing: whoever decides now reads *this* lap's track status and weather rather than last
lap's.

Where events come from is senna/env/events_io.py's problem — a live race rolls them, a
twin replays them. Draw order is the seed (5.5.5), so every rng consumption below sits
exactly where `F1RaceEnv.step()` put it before the extraction; the golden traces in
tests/env/fixtures hold it there.
"""

from dataclasses import dataclass

import numpy as np

from senna.env import dynamics, events
from senna.env.events_io import STAY_OUT
from senna.env.pitlane import resolve_pit_lane


@dataclass(frozen=True)
class LapDecisions:
    """What every car on the grid committed to this lap. Both arrays are n_cars wide and
    no index is special: the adapter fills twenty-one seats from the rival archetypes and
    one from whatever is driving, and the tick cannot tell which is which.

    Decisions arrive already legal. The engine does not mask, snap or validate — legality
    is the adapter's job (F-16), and a caller that skips it will get an illegal race run
    faithfully rather than an error.
    """

    pit: np.ndarray   # compound code to box onto, or STAY_OUT
    mode: np.ndarray  # energy/pace mode, per dynamics.CONSERVE..DEFEND


@dataclass(frozen=True)
class LapContext:
    """What the track is doing, resolved before anyone decides."""

    lap_index: int
    red_flag: bool
    onset: int  # the neutralisation that began this lap, GREEN if none — E-06's cue


def begin_lap(state, rng, *, source, lap_index: int) -> LapContext:
    """Resolve the track for this lap: status first, then the weather chain. Mutates the
    state's status, wetness and red-flag count, so the decisions collected next see the
    conditions they are actually deciding in.

    Takes no scenario: what the track does is entirely the source's business, whether it
    is rolling hazards or reading a trace."""
    red_flag, onset = source.track_status(state, lap_index, rng)
    source.weather(state, lap_index, rng)
    return LapContext(lap_index=lap_index, red_flag=red_flag, onset=onset)


def advance_lap(state, context, decisions, scenario, rng, *, source, sink=None
                ) -> dynamics.LapOutcome:
    """Run the lap the field committed to, and return what happened to every car.

    The order is the transition model of 5.5.3 read top to bottom: who failed, how much
    traffic each car is in, what the energy store could supply, the lap time that falls
    out of it, then the pit lane. State is mutated in place — the race is one object
    moving forward, not a value rebuilt each lap.
    """
    failed = source.failures(state, context.lap_index, rng)
    gap_ahead_s = gaps_ahead(state, scenario)

    harvest_mj = np.full(
        state.n_cars, dynamics.per_lap_harvest_mj(scenario, state.track_status)
    )
    request_mj = dynamics.deploy_request_mj(decisions.mode, scenario)
    delivered_mj, derate_s, soc_next_mj = dynamics.resolve_energy(
        state.soc_mj, harvest_mj, request_mj, scenario
    )

    noise_s = source.lap_noise(state, rng)
    racing_time_s = dynamics.lap_time_s(
        compound=state.compound, age=state.tyre_age, fuel_kg=state.fuel_kg,
        modes=decisions.mode, delivered_mj=delivered_mj, request_mj=request_mj,
        derate_s=derate_s, gap_ahead_s=gap_ahead_s, wetness=state.wetness,
        track_status=np.full(state.n_cars, state.track_status),
        driver_s=state.driver_s, noise_s=noise_s, scenario=scenario,
    )
    pit_time_s = _pit_times(state, decisions.pit, failed, context, scenario, source, rng)
    lap_time_s = racing_time_s + pit_time_s

    if sink is not None:
        sink.capture(state, context, decisions, failed)

    _apply_pits(state, decisions.pit, failed, context.red_flag)
    state.cumulative_time_s = state.cumulative_time_s + lap_time_s
    state.tyre_age = np.where(
        (decisions.pit != STAY_OUT) | failed | context.red_flag, 0, state.tyre_age + 1
    )
    state.soc_mj = soc_next_mj
    state.last_harvest_mj = harvest_mj
    state.last_deploy_mj = delivered_mj
    state.fuel_kg = _burn_fuel(state, scenario)
    state.lap += 1
    state.red_flag_now = context.red_flag
    if state.track_status == events.RED:
        state.track_status = events.GREEN  # the race resumes after the neutralisation

    return dynamics.LapOutcome(
        lap_time_s=lap_time_s,
        racing_time_s=racing_time_s,
        pit_time_s=pit_time_s,
        harvest_mj=harvest_mj,
        deploy_mj=delivered_mj,
        soc_next_mj=soc_next_mj,
        derate_penalty_s=derate_s,
        failed=failed,
        red_flag=context.red_flag,
    )


def gaps_ahead(state, scenario) -> np.ndarray:
    """Each car's time gap to the car classified one place ahead — the traffic input. A
    leader gets the dirty-air threshold so it is never counted as being in traffic."""
    gaps = np.full(state.n_cars, scenario.dirty_air_threshold_s)
    rank = state.positions()
    by_rank = np.argsort(rank, kind="stable")  # car index at each 0-based place
    for place in range(1, state.n_cars):
        car, ahead = by_rank[place], by_rank[place - 1]
        gaps[car] = state.cumulative_time_s[car] - state.cumulative_time_s[ahead]
    return gaps


def _pit_times(state, pit, failed, context, scenario, source, rng) -> np.ndarray:
    """Green pit loss with FIFO stacking for scheduled stops (E-05); a flat penalty for a
    tyre-failure stop (+25 s, kept from v2); free under a red flag (E-04)."""
    env_cfg = scenario.env
    pit_time_s = np.zeros(state.n_cars)
    stopping = (pit != STAY_OUT) & ~failed
    if not context.red_flag and stopping.any():
        cars = np.flatnonzero(stopping)
        draws = source.pit_service_s(cars.size, rng)
        service = np.maximum(env_cfg["pit"]["min_service_s"], draws) * _status_pit_multiplier(
            state, env_cfg
        )
        exit_s = resolve_pit_lane(
            state.cumulative_time_s[cars], service, lane_gap_s=env_cfg["pit"]["lane_gap_s"]
        )
        pit_time_s[cars] = exit_s - state.cumulative_time_s[cars]
    pit_time_s[failed] = env_cfg["forced_pit"]["tyre_failure_penalty_s"]
    return pit_time_s


def _status_pit_multiplier(state, env_cfg) -> float:
    if state.track_status == events.SC:
        return env_cfg["pit_loss_mult"]["sc"]
    if state.track_status == events.VSC:
        return env_cfg["pit_loss_mult"]["vsc"]
    return 1.0


def _apply_pits(state, pit, failed, red_flag: bool) -> None:
    changed = pit != STAY_OUT
    state.compound = np.where(changed, pit, state.compound)
    stopped = changed | failed | red_flag
    new_compound = state.compound != state.first_compound
    state.second_compound_used |= stopped & new_compound
    state.pit_count += (changed | failed).astype(int)


def _burn_fuel(state, scenario) -> np.ndarray:
    """Burn this lap's fuel. A car that cannot cover the lap retires — it never reaches the
    flag; a car landing on exactly zero at the line has finished, not retired, so the winner
    of a green race is never mis-scored as a DNF."""
    base = scenario.race_fuel_kg / scenario.total_laps
    if state.track_status in (events.SC, events.VSC):
        base *= scenario.sc_burn_factor
    state.retired |= state.fuel_kg < base - 1e-9
    return np.maximum(0.0, state.fuel_kg - base)
