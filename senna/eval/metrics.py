"""The metrics that are pure arithmetic over already-rolled races: M1, M4, M7, M9, M10
(spec 5.12). Nothing here builds an env or loads a checkpoint, which is what lets the
numbers Chapter 7 prints be checked against races whose answer is known by construction.

The heavier metrics live beside this module because they need the simulator to answer
their question at all: M3 re-solves each race (oracle_regret.py), M5 and M6 branch
alternative futures off a frozen trace (sc_quality.py, pit_accuracy.py), M11 re-rolls the
policy under sampled decisions (luck.py).
"""

import math

from senna.eval.bootstrap import mean_interval
from senna.train.gates import pair_outcome

_NEUTRALISED = ("vsc", "sc", "red")


def paired_position_delta(pairs, *, cfg) -> dict:
    """M1. Delegates the sign convention to the gate function the curriculum already
    uses: a finisher beats a DNF by the position gap, both-DNF is no evidence, and a
    dead heat counts against the agent. Restating that rule here would let the headline
    metric and the training gate drift apart."""
    outcomes = [
        pair_outcome(pair.agent_position, pair.agent_dnf,
                     pair.baseline_position, pair.baseline_dnf)
        for pair in pairs
    ]
    deltas = [float(delta) for _, delta in outcomes]
    interval = mean_interval(deltas, level=cfg["ci_level"], resamples=cfg["resamples"],
                             seed=cfg["seed"])
    excludes_zero = interval.excludes(0.0)
    return {
        "mean_delta": interval.mean,
        "ci_low": interval.low,
        "ci_high": interval.high,
        "n": interval.n,
        "finish_ahead_rate": sum(1.0 for ahead, _ in outcomes if ahead) / len(outcomes),
        "target": cfg["target_mean_delta"],
        "excludes_zero": excludes_zero,
        # 5.12 wants both halves: the mean clears the bar AND the interval rules out zero
        "met": bool(interval.mean >= cfg["target_mean_delta"] and excludes_zero),
    }


def energy_utilisation(races, *, cfg) -> dict:
    """M4. Green laps only — deployment under a neutralisation is not a strategic choice,
    and counting it would let a lucky safety car move the number. Reported as a pair with
    the derate share because either alone is gameable."""
    deployed_mj, budget_mj, green_laps, derated = 0.0, 0.0, 0, 0
    for race in races:
        for lap in race.laps:
            if lap["track_status"] in _NEUTRALISED:
                continue
            green_laps += 1
            deployed_mj += float(lap["deploy_mj"])
            budget_mj += float(race.e_dep_mj)
            derated += bool(lap["derated"])

    utilisation = deployed_mj / budget_mj if budget_mj else 0.0
    derate_share = derated / green_laps if green_laps else 0.0
    return {
        "utilisation": utilisation,
        "derate_share": derate_share,
        "target": cfg["target_utilisation"],
        "max_derate_share": cfg["max_derate_share"],
        "n_green_laps": green_laps,
        "met": bool(utilisation >= cfg["target_utilisation"]
                    and derate_share <= cfg["max_derate_share"]),
    }


def strategy_diversity(races_by_circuit) -> dict:
    """M7. Entropy in nats of the (stop count, first-stop compound) distribution, per
    circuit. A sanity metric and never a headline — dithering fakes diversity — so the
    histogram travels with the scalar and the mean is over circuits, not races: a busy
    circuit should not drown a dull one."""
    per_circuit = {}
    for circuit, races in races_by_circuit.items():
        histogram: dict[str, int] = {}
        for race in races:
            compounds = list(race.compounds)
            category = f"{len(race.pit_laps)}x{compounds[0] if compounds else 'none'}"
            histogram[category] = histogram.get(category, 0) + 1

        total = sum(histogram.values())
        entropy = -sum((count / total) * math.log(count / total)
                       for count in histogram.values()) if total else 0.0
        per_circuit[circuit] = {
            "entropy_nats": entropy,
            "n_races": total,
            "histogram": histogram,
        }

    entropies = [block["entropy_nats"] for block in per_circuit.values()]
    return {
        "per_circuit": per_circuit,
        "mean_entropy_nats": sum(entropies) / len(entropies) if entropies else 0.0,
    }


def tyre_failure_rate(races) -> dict:
    """M9. Races that lost at least one tyre, per hundred races — a race that loses two
    still counts once, because the denominator is races. Read jointly with M1 and the
    stint lengths: never stretching a stint drives this to zero for free."""
    failed = sum(1 for race in races if any(lap["forced_pit"] for lap in race.laps))
    n_races = len(races)
    return {
        "failures_per_100": 100.0 * failed / n_races if n_races else 0.0,
        "n_races": n_races,
        "n_failures": failed,
    }


def legality_audit(races) -> dict:
    """M10's other half. The property test covers the action space; this covers the eval
    logs — zero coerced actions across every race the report is built from. A snapped
    stop is legal but is not what the policy asked for, so it is counted separately and
    still costs the set its clean badge (A-07 replay honesty)."""
    illegal = sum(int(lap["violations"]) for race in races for lap in race.laps)
    snapped = sum(int(race.agent.snapped) for race in races)
    return {
        "illegal_actions": illegal,
        "snapped": snapped,
        "n_races": len(races),
        "clean": bool(illegal == 0 and snapped == 0),
    }
