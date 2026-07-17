"""Generator-level Monte Carlo — lap-time and stint distributions for 5.4.1.

This is NOT the F05 environment: no agent, no rivals, no action masks. It is
the smallest sampler that turns the fitted and transformed constants into the
green-lap and stint distributions the validation suite compares against the
real held-out races. Everything stochastic hangs off the seed passed in — no
module-level RNG (5.5.5 discipline, kept even here).
"""

import numpy as np
import pandas as pd

from senna.physics.fits.fuel import fuel_profile

_COLUMNS = ["race", "car", "lap_number", "lap_time_s", "compound", "tyre_age", "is_green", "pit"]


def plan_stints(n_laps: int, degradation: dict, *, pit_loss_mean_s: float) -> list[tuple[str, int]]:
    """Min-total-time 1- or 2-stop plan honouring the two-compound rule.

    A tyre loses time at a rate that climbs with age, so a stint's cost grows
    faster than its length — quadratically for a linear wear rate a. The
    optimiser trades that convex cost against pit_loss; higher wear pulls the
    crossover earlier, shortening stints, the physical response the generator
    must reproduce. Planning works on the wear rate a and the compound pace
    offset; the fine grip-curve shape b drives the sampled lap times, where its
    lap-to-lap effect actually matters.
    """
    compounds = sorted(degradation)
    best_plan = None
    best_cost = np.inf
    for n_stops in (1, 2):
        for split in _splits(n_laps, n_stops + 1):
            for choice in _compound_choices(compounds, n_stops + 1):
                if len(set(choice)) < 2:  # the mandatory two-compound rule (F-20)
                    continue
                cost = n_stops * pit_loss_mean_s + sum(
                    _stint_cost(degradation[c], laps) for c, laps in zip(choice, split, strict=True)
                )
                if cost < best_cost:
                    best_cost = cost
                    best_plan = list(zip(choice, split, strict=True))
    return best_plan


def _stint_cost(terms: dict, laps: int) -> float:
    """Compound pace over the stint plus wear that accumulates with age."""
    ages = np.arange(laps, dtype=float)
    return float(laps * terms["offset_s"] + terms["a"] * float(np.sum(ages)))


def _splits(n_laps: int, n_stints: int) -> list[tuple[int, ...]]:
    """Every way to cut n_laps into n_stints positive stints (n_laps is small)."""
    if n_stints == 1:
        return [(n_laps,)]
    splits = []
    for first in range(1, n_laps - n_stints + 2):
        for rest in _splits(n_laps - first, n_stints - 1):
            splits.append((first, *rest))
    return splits


def _compound_choices(compounds: list[str], n_stints: int) -> list[tuple[str, ...]]:
    if n_stints == 1:
        return [(c,) for c in compounds]
    return [
        (c, *rest)
        for c in compounds
        for rest in _compound_choices(compounds, n_stints - 1)
    ]


def sample_races(
    spec: dict, *, n_races: int, n_cars: int, seed: int, stint_jitter_laps_sigma: float
) -> pd.DataFrame:
    n_laps = spec["n_laps"]
    base_plan = plan_stints(n_laps, spec["degradation"], pit_loss_mean_s=spec["pit_loss_mean_s"])
    race_seeds = np.random.SeedSequence(seed).spawn(n_races)
    rows = []
    for race, race_seed in enumerate(race_seeds):
        rng = np.random.default_rng(race_seed)
        is_green, status = _race_hazards(rng, n_laps, spec["hazards"])
        fuel_kg = _race_fuel_kg(status, spec["race_fuel_kg"], spec["sc_burn_factor"])
        for car in range(n_cars):
            _append_car(rows, spec, race, car, rng, base_plan, is_green, status, fuel_kg,
                        stint_jitter_laps_sigma)
    return pd.DataFrame(rows, columns=_COLUMNS)


def _race_hazards(rng, n_laps: int, hazards: dict) -> tuple[np.ndarray, list[str]]:
    """Per-lap SC/VSC shared across the field; VSC only where SC did not fire."""
    sc = rng.random(n_laps) < hazards["sc_lambda_per_lap"]
    vsc = (rng.random(n_laps) < hazards["vsc_lambda_per_lap"]) & ~sc
    status = ["4" if s else "6" if v else "1" for s, v in zip(sc, vsc, strict=True)]
    return ~(sc | vsc), status


def _race_fuel_kg(status: list[str], race_fuel_kg: float, sc_burn_factor: float) -> np.ndarray:
    laps = pd.DataFrame(
        {"lap_number": np.arange(1, len(status) + 1), "track_status": status}
    )
    return fuel_profile(laps, race_fuel_kg=race_fuel_kg, sc_burn_factor=sc_burn_factor).to_numpy()


def _append_car(
    rows, spec, race, car, rng, base_plan, is_green, status, fuel_kg, jitter_sigma
) -> None:
    n_laps = spec["n_laps"]
    driver_s = rng.normal(0.0, spec["sigma_driver_s"])
    noise_s = rng.normal(0.0, spec["sigma_lap_s"], n_laps)
    compound_of, age_of, pit_on = _lay_out_stints(base_plan, n_laps, rng, jitter_sigma)
    for lap in range(1, n_laps + 1):
        i = lap - 1
        terms = spec["degradation"][compound_of[i]]
        lap_s = (
            spec["t0_s"]
            + driver_s
            + terms["offset_s"]
            + terms["a"] * age_of[i] ** terms["b"]
            + spec["k_m_s_per_kg"] * fuel_kg[i]
            + spec["evolution_s_per_lap"] * lap
            + noise_s[i]
        )
        if not is_green[i]:
            lap_s *= spec["status_mult"]["sc" if status[i] == "4" else "vsc"]
        if pit_on[i]:
            lap_s += rng.normal(spec["pit_loss_mean_s"], spec["pit_loss_sigma_s"])
        rows.append(
            {
                "race": race,
                "car": car,
                "lap_number": lap,
                "lap_time_s": lap_s,
                "compound": compound_of[i],
                "tyre_age": age_of[i],
                "is_green": bool(is_green[i]),
                "pit": bool(pit_on[i]),
            }
        )


def _lay_out_stints(base_plan, n_laps: int, rng, jitter_sigma):
    """Jitter the plan's switch laps, then expand to per-lap compound and age."""
    lengths = _jittered_lengths(base_plan, n_laps, rng, jitter_sigma)
    compound_of = []
    age_of = []
    pit_on = [False] * n_laps
    lap = 0
    for stint_index, ((compound, _), length) in enumerate(zip(base_plan, lengths, strict=True)):
        if stint_index > 0:
            pit_on[lap] = True  # the out-lap of every stop after the first carries pit loss
        for age in range(length):
            compound_of.append(compound)
            age_of.append(float(age))
            lap += 1
    return compound_of, age_of, pit_on


def _jittered_lengths(base_plan, n_laps: int, rng, jitter_sigma) -> list[int]:
    lengths = [length for _, length in base_plan]
    for i in range(len(lengths) - 1):
        shift = int(round(rng.normal(0.0, jitter_sigma)))
        moved = min(max(lengths[i] + shift, 1), lengths[i] + lengths[i + 1] - 1)
        lengths[i + 1] += lengths[i] - moved
        lengths[i] = moved
    return lengths
