"""Event traces synthesized from real races, for the ten era-matched counterfactuals (M2).

M2 asks what the agent would have done with the team's own race in front of it. Replaying
the team's stops into a synthetic dry race answers a different and much easier question:
the real strategy stops looking like a response to anything and the comparison becomes
trivially winnable. So the events come from the ingested laps — the safety cars where they
fell, the red flag with its free tyre change (E-04), the rain arriving when it arrived
(E-08) — and both legs of the pair race through them.

Driver pace is fitted, not drawn (F17). This module has always been handed `laps_by_driver`
keyed by real driver codes and then filled `driver_s` from `rng.normal` — it knew which seat
was Verstappen's and gave him a coin flip, which made the counterfactual era-matched in its
events and not in its pace. Each seat now takes the effect the joint regression measured for
that driver at this circuit-era. Read it as the seat rather than the person: era 2024 pools
2022-2025, so the number carries whatever car they drove in those seasons, and
configs/drivers.yaml records the laps and seasons behind each one.

What stays synthetic is stated rather than buried. Tyre failures are not identifiable from
timing data, so no car loses one. Rival energy modes are balanced, the same reasoning the
replay baseline already publishes: a 2024 strategy carries no 2026 energy decision. A seat
the table cannot speak for — a phantom car padding a short field, or a driver with too few
clean laps — keeps a drawn offset. And the wetness curve is a mapping from a rainfall flag,
which is a stylised choice: it is the paragraph the British GP write-up owes (E-08).
"""

import numpy as np

from senna import config
from senna.env import events
from senna.env.lineup import resolve
from senna.env.scenario import compound_code
from senna.env.twin import EventTrace

_SLICKS = ("SOFT", "MEDIUM", "HARD")
_BALANCED = 1
# FastF1 track-status digits (5.3.2). 6 and 7 are both virtual safety car phases and stay
# one state here, because collapsing VSC into SC is the E-03 mistake, not this one.
_STATUS_DIGITS = {"4": events.SC, "5": events.RED, "6": events.VSC, "7": events.VSC}


class EraFitError(ValueError):
    """A circuit whose scenario for this era is really the other era's fits."""


def require_native_era_fits(circuit: str, era: str, *, configs_dir=None) -> None:
    """Refuse a circuit that has no fits of its own for this era.

    build_scenario falls back to the 2026 fits where a circuit has no 2024 ones, which is a
    reasonable default for a demo and a lie for a counterfactual: the run would carry an
    era-matched label while running the very physics the era match exists to remove.
    """
    params = config.load("physics_params", configs_dir)["circuits"].get(circuit, {})
    era_int = int(era)
    joint = (params.get("joint_pace") or {}).get(era_int)
    degradation = (params.get("degradation") or {}).get(era_int) or {}
    fitted_slicks = [name for name in degradation if name in _SLICKS]
    if joint is None or len(fitted_slicks) < 2:
        raise EraFitError(
            f"{circuit} has no native {era} fits (joint pace: {joint is not None}, "
            f"slicks: {len(fitted_slicks)}) — build_scenario would serve it the other "
            "era's constants under an era-matched label (F-24)"
        )


def trace_from_real_race(*, circuit, era, scenario, laps_by_driver, weather_rows, grid,
                         real_total_laps, seed, cfg, configs_dir=None) -> EventTrace:
    """One EventTrace carrying a real race's events, rescaled onto the sim distance.

    Cars are indexed in `laps_by_driver` order, which is how the harness knows which column
    is the driver being counterfactualled.
    """
    require_native_era_fits(circuit, era)
    n_laps, n_cars = scenario.total_laps, scenario.grid_size
    rng = np.random.default_rng([int(seed), 2024])

    def to_sim(lap: int) -> int:
        return min(n_laps, max(1, round(lap * n_laps / real_total_laps)))

    status = np.full(n_laps, events.GREEN, dtype=int)
    for rows in laps_by_driver.values():
        for lap_number, _stint, _compound, _pit_in, track_status in rows:
            state = _status_from_digits(track_status)
            if state is not None:
                # the worst state any car reported on that lap: a neutralisation is a
                # property of the track, and one car's missing digit should not erase it
                index = to_sim(lap_number) - 1
                status[index] = max(status[index], state)

    red_flag = status == events.RED
    weather, wetness = _weather_series(weather_rows, n_laps, scenario, cfg)

    rival_pit = np.full((n_laps, n_cars), -1, dtype=np.int8)
    rival_mode = np.full((n_laps, n_cars), _BALANCED, dtype=np.int8)
    for car, rows in enumerate(laps_by_driver.values()):
        if car >= n_cars:
            break
        for out_lap, compound in _stops_from_rows(rows):
            rival_pit[to_sim(out_lap) - 1, car] = compound_code(compound)

    return EventTrace(
        circuit=circuit, era=era, seed=int(seed), n_laps=n_laps, n_cars=n_cars,
        grid=_grid_order(grid, laps_by_driver, n_cars),
        driver_s=_seat_pace_s(
            laps_by_driver, circuit=circuit, era=era, n_cars=n_cars, rng=rng,
            sigma_driver_s=scenario.sigma_driver_s, configs_dir=configs_dir,
        ),
        status=status, red_flag=red_flag, weather=weather, wetness=wetness,
        failed=np.zeros((n_laps, n_cars), dtype=bool),
        rival_pit=rival_pit, rival_mode=rival_mode,
    )


def _seat_pace_s(laps_by_driver, *, circuit, era, n_cars, rng, sigma_driver_s, configs_dir):
    """Seat offsets in car order, which is `laps_by_driver` order — the same order the
    harness relies on to know which column is the driver being counterfactualled.

    Drawn first and then overwritten, as the env's own reset does it, so a seat the table
    has nothing for keeps a real offset. Zero would put it on the field average, and the
    phantom cars padding a short field would all become quicker than most of the grid.
    """
    drawn_s = rng.normal(0.0, sigma_driver_s, n_cars)
    named = resolve(
        list(laps_by_driver), circuit=circuit, era=era, n_cars=n_cars, configs_dir=configs_dir
    )
    return np.where(np.isnan(named.seat_pace_s), drawn_s, named.seat_pace_s)


def _status_from_digits(track_status) -> int | None:
    if not track_status:
        return None
    states = [_STATUS_DIGITS[digit] for digit in str(track_status)
              if digit in _STATUS_DIGITS]
    return max(states) if states else None


def _stops_from_rows(rows) -> list:
    """Each stint that ended in a pit becomes a stop on the next stint's out-lap, taking
    the next stint's compound — the same reading senna/strategy/extract.py applies."""
    stints: dict[int, list] = {}
    for lap_number, stint, compound, pit_in_time_s, *_ in rows:
        if stint is None:
            continue
        stints.setdefault(int(stint), []).append((int(lap_number), compound, pit_in_time_s))

    ordered = [sorted(stints[number]) for number in sorted(stints)]
    stops = []
    for current, following in zip(ordered[:-1], ordered[1:], strict=False):
        if not any(pit_in is not None for _, _, pit_in in current):
            continue
        out_lap, compound, _ = following[0]
        if compound is not None:
            stops.append((out_lap, str(compound)))
    return stops


def _weather_series(weather_rows, n_laps, scenario, cfg):
    """Rainfall flags to a wetness curve. The mapping is stylised: the samples say whether
    it was raining, not how wet the track was, so wetness integrates toward the env's own
    damp and wet targets and the crossover lap it implies is an assumption the write-up
    states (E-08)."""
    targets = scenario.env["weather"]["target_wetness"]
    sustained = int(cfg["m2"]["trace"]["wet_after_laps"])
    weather = np.full(n_laps, events.DRY, dtype=int)
    wetness = np.zeros(n_laps, dtype=float)
    if not weather_rows:
        return weather, wetness

    flags = _resample_flags(weather_rows, n_laps)
    run = 0
    level = 0.0
    for lap in range(n_laps):
        run = run + 1 if flags[lap] else 0
        if run >= sustained:
            weather[lap], target = events.WET, float(targets["wet"])
        elif run > 0:
            weather[lap], target = events.DAMP, float(targets["damp"])
        else:
            weather[lap], target = events.DRY, float(targets["dry"])
        # the same first-order approach the env's own integrator uses, so a synthesized
        # crossover sits where a simulated one would
        level += (target - level) / scenario.env["weather"]["n_sectors"]
        wetness[lap] = level
    return weather, wetness


def _resample_flags(weather_rows, n_laps) -> np.ndarray:
    """Weather samples arrive per minute, not per lap; nearest-in-time is enough at this
    resolution and avoids inventing a interpolation the source cannot support."""
    times = np.array([float(time_s) for time_s, _ in weather_rows])
    raining = np.array([bool(flag) for _, flag in weather_rows])
    if times.size == 0:
        return np.zeros(n_laps, dtype=bool)
    edges = np.linspace(times.min(), times.max(), n_laps)
    return raining[np.abs(times[None, :] - edges[:, None]).argmin(axis=1)]


def _grid_order(grid, laps_by_driver, n_cars) -> np.ndarray:
    """A permutation of 1..n_cars in car-index order. Real grids carry gaps (penalties,
    withdrawals) and pit-lane starts, and the env derives lap-0 order from these slots, so
    they are compacted: classified starters keep their relative order, pit-lane starts fall
    behind them, and a short field is padded out so the env still accepts the trace."""
    drivers = list(laps_by_driver)[:n_cars]
    classified, pit_lane = [], []
    for driver in drivers:
        position = grid.get(driver)
        (pit_lane if not position else classified).append((position or 0, driver))

    ordered = [driver for _, driver in sorted(classified)]
    ordered += [driver for _, driver in pit_lane]
    slot_by_driver = {driver: slot for slot, driver in enumerate(ordered, start=1)}

    slots = [slot_by_driver[driver] for driver in drivers]
    # phantom cars fill the rest of the grid from the back; they carry no stops, so they
    # add traffic without inventing a strategy the real race never ran
    slots += list(range(len(slots) + 1, n_cars + 1))
    return np.array(slots, dtype=int)
