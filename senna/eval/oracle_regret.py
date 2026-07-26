"""M3 — oracle regret: the gap to a full-information strategist on the deterministic twin.

Both sides are measured on the same twin, so the comparison isolates the decision. The
agent's leg is its own twin roll rather than its noisy live race; scoring a live run against
a deterministic oracle would price the pace noise as if it were bad strategy.

The agent's realised plan is entered as a contender in the oracle's own search. That makes
the oracle's answer at least as good as the agent's pit sequence by construction, so a
negative regret can only come from the energy dimension — the oracle schedules energy
greedily per lap, which is a heuristic rather than a proven optimum (its published
assumption 4). Those negatives are reported rather than clipped: they are the assumption
becoming visible, and hiding them would make the ceiling look tighter than it is.

An easy oracle flatters the agent, which is why the seven assumptions in
senna/strategy/oracle.py travel with this number into the report.
"""

import logging

from senna.env import F1RaceEnv
from senna.env.scenario import build_scenario
from senna.strategy.oracle import solve_oracle
from senna.strategy.plans import PitPlan, PlanPolicy
from senna.strategy.rollout import run_episode

log = logging.getLogger(__name__)

_ORACLE_SEED = 0  # the seed solve_oracle rolls its contenders on; the twin is deterministic


def race_regret(race, *, configs_dir=None) -> dict:
    """Time and position regret for one recorded eval race."""
    from senna import config

    scenario = build_scenario(race.circuit, "2026", configs_dir=configs_dir)
    cfg = config.load("baselines", configs_dir)["oracle"]
    agent_plan = PitPlan(stops=tuple(zip(race.twin.pit_laps, race.twin.compounds,
                                         strict=True)))

    oracle = solve_oracle(scenario, race.trace, cfg=cfg, baselines=(agent_plan,))
    env = F1RaceEnv(race.circuit, "2026", twin=race.trace, configs_dir=configs_dir)
    oracle_race = run_episode(
        env, PlanPolicy(oracle.plan, mode="greedy", scenario=scenario), seed=_ORACLE_SEED
    )

    return {
        "circuit": race.circuit,
        "seed": race.seed,
        "time_regret_s": race.twin.race_time_s - oracle.race_time_s,
        "position_regret": race.twin.final_position - oracle_race.final_position,
        "agent_time_s": race.twin.race_time_s,
        "oracle_time_s": oracle.race_time_s,
        "oracle_stops": [[lap, name] for lap, name in oracle.plan.stops],
        "agent_stops": [[lap, name] for lap, name in agent_plan.stops],
        "considered": oracle.considered,
        "rolled": oracle.rolled,
    }


def regret_distribution(rows) -> dict:
    """The distribution 5.12 asks for — no hard target in run 1 — plus the search-size
    stats that say how hard the ceiling was to compute."""
    import numpy as np

    times = np.array([row["time_regret_s"] for row in rows], dtype=float)
    positions = np.array([row["position_regret"] for row in rows], dtype=float)
    quantiles = [0.05, 0.25, 0.5, 0.75, 0.95]
    return {
        "n_races": len(rows),
        "time_regret_s": {
            "mean": float(times.mean()) if times.size else 0.0,
            "median": float(np.median(times)) if times.size else 0.0,
            "quantiles": {str(q): float(np.quantile(times, q)) for q in quantiles}
            if times.size else {},
            "negative_count": int((times < 0).sum()),
        },
        "position_regret": {
            "mean": float(positions.mean()) if positions.size else 0.0,
            "median": float(np.median(positions)) if positions.size else 0.0,
        },
        "search": {
            "mean_considered": float(np.mean([r["considered"] for r in rows]))
            if rows else 0.0,
            "mean_rolled": float(np.mean([r["rolled"] for r in rows])) if rows else 0.0,
        },
        "per_race": rows,
    }
