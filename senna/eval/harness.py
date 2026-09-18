"""M2 — the ten era-matched counterfactuals: the agent's strategy against the team's own,
replayed through the events of the race the team actually ran (F-24).

The pair loop is deliberately re-implemented here rather than shared with the serving
path. senna/serve/runner.py answers the same question for the interface, but it is wired
to Postgres run rows and frame persistence; the twelve lines that matter are the two legs
and the trace they share, and copying those keeps the offline battery runnable with no
database and no API.

Statistics at n=10 are stated before the result, not chosen after it. The primary claim is
the exact paired sign test — it assumes nothing about the distribution of position deltas
and needs nine of ten races to clear alpha. A bootstrap interval over ten points is
reported alongside as description, never as the claim.
"""

import logging
from dataclasses import dataclass

from senna import config
from senna.env import F1RaceEnv
from senna.env.scenario import build_scenario
from senna.eval.bootstrap import mean_interval, paired_sign_test
from senna.eval.traces import require_native_era_fits, trace_from_real_race
from senna.strategy.extract import plan_from_rows
from senna.strategy.replay import RealStrategyReplay
from senna.strategy.rollout import run_episode
from senna.train.gates import pair_outcome
from senna.train.seeds import load_reserved_test_bank

log = logging.getLogger(__name__)

_LAPS_SQL = """
select l.driver, l.lap_number, l.stint, l.compound, l.pit_in_time_s, l.track_status
from laps l join sessions s on s.id = l.session_id join events e on e.id = s.event_id
where e.season = :season and e.round = :round and s.session_name = 'Race'
  and l.source like 'real%'
order by l.driver, l.lap_number
"""

_WEATHER_SQL = """
select w.time_s, w.rainfall
from weather w join sessions s on s.id = w.session_id join events e on e.id = s.event_id
where e.season = :season and e.round = :round and s.session_name = 'Race'
order by w.time_s
"""

_GRID_SQL = """
select r.driver_abbrev, r.grid_position, r.position, r.status
from results r join sessions s on s.id = r.session_id join events e on e.id = s.event_id
where e.season = :season and e.round = :round and s.session_name = 'Race'
"""


@dataclass(frozen=True)
class RaceInputs:
    laps_by_driver: dict
    weather_rows: list
    grid: dict
    real_total_laps: int
    real_finish: dict


async def load_race(conn, *, season: int, round_number: int) -> RaceInputs:
    from sqlalchemy import text

    params = {"season": season, "round": round_number}
    laps_by_driver: dict[str, list] = {}
    for driver, lap_number, stint, compound, pit_in_time_s, track_status in (
        await conn.execute(text(_LAPS_SQL), params)
    ).all():
        laps_by_driver.setdefault(driver, []).append(
            (lap_number, stint, compound, pit_in_time_s, track_status)
        )
    if not laps_by_driver:
        raise LookupError(f"no ingested race laps for {season} round {round_number}")

    weather_rows = [(float(t), bool(r)) for t, r in
                    (await conn.execute(text(_WEATHER_SQL), params)).all()]
    grid, finish = {}, {}
    for abbrev, grid_position, position, status in (
        await conn.execute(text(_GRID_SQL), params)
    ).all():
        grid[abbrev] = int(grid_position) if grid_position else None
        finish[abbrev] = {"position": position, "status": status}

    real_total_laps = max(rows[-1][0] for rows in laps_by_driver.values())
    return RaceInputs(laps_by_driver=laps_by_driver, weather_rows=weather_rows,
                      grid=grid, real_total_laps=int(real_total_laps), real_finish=finish)


def run_counterfactual(race_cfg, inputs, *, policy, era: str, cfg, configs_dir=None) -> dict:
    """One race: the agent and the driver's real strategy through the same real events."""
    circuit, driver = race_cfg["circuit"], race_cfg["driver"]
    require_native_era_fits(circuit, era, configs_dir=configs_dir)
    scenario = build_scenario(circuit, era, configs_dir=configs_dir)

    # the counterfactualled driver is car 0, so the ego column is the one whose strategy
    # is being replaced; every other car keeps its own real stops
    ordered = {driver: inputs.laps_by_driver[driver],
               **{d: rows for d, rows in inputs.laps_by_driver.items() if d != driver}}
    real_plan = plan_from_rows(
        [row[:4] for row in ordered[driver]],
        sim_total_laps=scenario.total_laps, real_total_laps=inputs.real_total_laps,
    )
    if any(name is None for _, name in real_plan.stops):
        raise LookupError(f"{circuit} {race_cfg['season']}: {driver} has an unnamed compound")

    replay_cfg = config.load("baselines", configs_dir)["replay"]
    seeds = load_reserved_test_bank(configs_dir, consumer="F14")[circuit][
        : cfg["m2"]["seeds_per_race"]
    ]

    deltas, rows = [], []
    for seed in seeds:
        trace = trace_from_real_race(
            circuit=circuit, era=era, scenario=scenario, laps_by_driver=ordered,
            weather_rows=inputs.weather_rows, grid=inputs.grid,
            real_total_laps=inputs.real_total_laps, seed=int(seed), cfg=cfg,
            configs_dir=configs_dir,
        )
        # the lineup as well as the trace: seat pace rides driver_s inside the twin, but
        # the tyre-style multiplier lives on the scenario, so the env needs to be told who
        # is driving for the counterfactual to be era-matched in wear too (F17)
        env = F1RaceEnv(circuit, era, twin=trace, drivers=list(ordered), configs_dir=configs_dir)
        baseline_policy = RealStrategyReplay(real_plan, scenario, replay_cfg)
        baseline = run_episode(env, baseline_policy, seed=int(seed))
        agent = run_episode(env, policy, seed=int(seed))

        _, delta = pair_outcome(agent.final_position, agent.dnf,
                                baseline.final_position, baseline.dnf)
        deltas.append(float(delta))
        rows.append({
            "seed": int(seed), "agent_position": agent.final_position,
            "baseline_position": baseline.final_position, "delta": delta,
            # a retirement and a slow race both read as a bad position; only one of them
            # is a strategy result, so the store keeps them apart
            "agent_dnf": agent.dnf, "baseline_dnf": baseline.dnf,
            "agent_stops": [[lap, name] for lap, name
                            in zip(agent.pit_laps, agent.compounds, strict=True)],
            "snapped_stops": baseline_policy.snapped,
        })

    return {
        "season": race_cfg["season"], "round": race_cfg["round"], "circuit": circuit,
        "driver": driver, "rationale": " ".join(race_cfg["rationale"].split()),
        "red_flag": race_cfg["red_flag"], "wet": race_cfg["wet"],
        "real_stops": [[lap, name] for lap, name in real_plan.stops],
        "real_finish": inputs.real_finish.get(driver, {}),
        "mean_delta": sum(deltas) / len(deltas),
        "per_seed": rows,
        # a strategy the mask had to alter is a weaker comparison, so the count travels
        # with the number rather than being quietly absorbed (A-07 replay honesty)
        "snapped_stops": sum(row["snapped_stops"] for row in rows),
    }


def summarise(races, *, cfg) -> dict:
    """The M2 headline. The sign test leads; the interval is descriptive at n=10."""
    deltas = [race["mean_delta"] for race in races]
    sign = paired_sign_test(deltas)
    interval = mean_interval(deltas, level=cfg["bootstrap"]["ci_level"],
                             resamples=cfg["bootstrap"]["resamples"],
                             seed=cfg["bootstrap"]["seed"])
    alpha = cfg["m2"]["sign_test_alpha"]
    return {
        "mean_delta": interval.mean,
        "ci_low": interval.low,
        "ci_high": interval.high,
        "ci_note": "descriptive only: a bootstrap over ten races is not a claim",
        "n_races": len(races),
        "sign_test": {"wins": sign.wins, "losses": sign.losses, "ties": sign.ties,
                      "p_value": sign.p_value, "alpha": alpha,
                      "significant": bool(sign.p_value < alpha)},
        "target": cfg["m2"]["target_mean_delta"],
        "stretch": cfg["m2"]["stretch_mean_delta"],
        "met": bool(interval.mean >= cfg["m2"]["target_mean_delta"]),
        "total_snapped_stops": sum(race["snapped_stops"] for race in races),
        "per_race": races,
    }
