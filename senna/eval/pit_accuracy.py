"""M6 — pit window accuracy: the share of stops within 3 laps of the post-hoc optimum.

The information set is the honest half of this metric, so it is stated rather than implied.
The optimum is the argmin over feasible laps for one stop on the frozen event trace, holding
the agent's other stops, its compound sequence and its energy actions fixed — a
coordinate-wise search around what the agent actually did. The joint re-plan is M3's
question. The agent decided with no knowledge of the future; the search sees the whole race.
The three-lap tolerance is the allowance for that asymmetry, kept from v2.

Candidates are rolled in full rather than costed from the oracle's stint tables. The tables
are blind to the pit-loss discount under a neutralisation, to dirty air and to the pit-lane
FIFO — which is precisely the set of things that move an optimal stop lap — so a table-based
sweep would confidently name the wrong lap. A roll is a few milliseconds; the accuracy is
worth more.
"""

from senna.env.scenario import START_COMPOUND, compound_code
from senna.eval.bootstrap import share_interval
from senna.strategy.oracle import legal_codes_at
from senna.strategy.policy import ScriptedActions
from senna.strategy.rollout import run_episode

_VARIANT_SEED = 0  # twin rolls are deterministic; the seed only anchors the policy stream


def _cliff_cap(scenario, name: str) -> int:
    fallback = scenario.env["obs"]["tyre_age_norm_laps"]
    margin = scenario.env["tyre_failure"]["cliff_age_margin_laps"]
    return scenario.deg_max_age.get(name, fallback) + margin


def stop_corridor(race, index: int, *, scenario, trace) -> list:
    """Every lap this stop could have moved to: strictly between its neighbouring stops,
    with neither adjacent stint past its compound's cliff, and with the compound the car
    actually took legal at that lap's pit entry (E-08)."""
    stops = list(race.pit_laps)
    compounds = list(race.compounds)
    n_laps = trace.n_laps

    previous_out = stops[index - 1] if index > 0 else 1
    previous_compound = compounds[index - 1] if index > 0 else START_COMPOUND
    next_out = stops[index + 1] if index + 1 < len(stops) else None
    compound = compounds[index]
    code = compound_code(compound)

    upper = next_out if next_out is not None else n_laps + 1
    corridor = []
    for candidate in range(max(previous_out + 1, 2), min(upper, n_laps + 1)):
        if candidate - previous_out - 1 > _cliff_cap(scenario, previous_compound):
            continue
        following = (next_out - candidate - 1 if next_out is not None
                     else n_laps - candidate)
        if following > _cliff_cap(scenario, compound):
            continue
        if code not in legal_codes_at(scenario, trace, candidate):
            continue
        corridor.append(candidate)
    return corridor


def stop_optima(race, index: int, *, scenario, trace, env) -> list:
    """Roll every lap in the corridor and return the argmin set. Ties are genuine — the
    twin is deterministic — so they are all returned and the hit rule takes the nearest."""
    corridor = stop_corridor(race, index, scenario=scenario, trace=trace)
    if not corridor:
        return []

    times = {}
    for candidate in corridor:
        variant = [action.copy() for action in race.actions]
        realised = race.pit_laps[index]
        variant[realised - 1][0] = 0  # lift the stop off the lap the agent took it on
        variant[candidate - 1][0] = compound_code(race.compounds[index]) + 1
        times[candidate] = run_episode(
            env, ScriptedActions(variant), seed=_VARIANT_SEED
        ).race_time_s

    best = min(times.values())
    return [lap for lap, time_s in times.items() if time_s <= best + 1e-9]


def pit_window_accuracy(rows, *, cfg) -> dict:
    """The share of judged stops landing within the tolerance of their nearest optimum."""
    excluded: dict[str, int] = {}
    hits = []
    for row in rows:
        if row["excluded"]:
            excluded[row["excluded"]] = excluded.get(row["excluded"], 0) + 1
            continue
        optima = row["optimal_laps"]
        if not optima:
            excluded["no_corridor"] = excluded.get("no_corridor", 0) + 1
            continue
        # nearest, not first: a tie means two laps were equally good, and grading against
        # the further one would penalise an agent that found the other
        nearest = min(abs(row["stop_lap"] - lap) for lap in optima)
        hits.append(nearest <= cfg["tolerance_laps"])

    interval = share_interval(
        hits, level=cfg["bootstrap"]["ci_level"],
        resamples=cfg["bootstrap"]["resamples"], seed=cfg["bootstrap"]["seed"],
    ) if hits else None

    share = interval.mean if interval else 0.0
    return {
        "share": share,
        "ci_low": interval.low if interval else 0.0,
        "ci_high": interval.high if interval else 0.0,
        "n_stops": len(hits),
        "target": cfg["target_share"],
        "excluded": excluded,
        "met": bool(share >= cfg["target_share"]),
    }
