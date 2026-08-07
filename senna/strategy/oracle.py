"""The full-information DP oracle (A-05) and the ceiling it sets for oracle regret (M3).

Two levels, because the dynamics allow it. On the deterministic twin a stint's cost is
plan-independent — fuel burn is fixed, the greedy energy schedule is decided lap by lap,
and the only cross-plan couplings are traffic and the pit-lane FIFO. So stage 1 costs
every stint exactly with per-compound tables and enumerates all 1..max_stops plans by
table lookup (cheap); stage 2 re-scores the best of those, plus any baseline plans handed
in, with full twin rolls that put traffic and FIFO back. The best rolled time wins.

Because each baseline's own plan is re-rolled here, the oracle can only tie or beat a
baseline on the pit dimension. The energy dimension is re-optimised greedily rather than
proven optimal (SOC couples laps, so greedy-per-lap is a heuristic, not a global optimum —
assumption 4 below), so "beats or ties a baseline" is a strong empirical property here,
not a theorem.

Published assumptions (the honest half of the metric — an easy oracle flatters the agent):
  1. full information: the frozen event trace is known before lap 1;
  2. rivals do not react — their recorded behaviour replays whatever the oracle does;
  3. deterministic physics: zero pace noise, mean pit service, tyre failure a hard cap;
  4. energy is greedy per lap, never jointly optimised with the tyre plan (the A-05 space);
  5. the start compound is MEDIUM — the env's grid rule, outside the agent's action too;
  6. stops capped at max_stops; stage-1 ranking ignores traffic and FIFO, the top-K rolls
     restore them, so the winner's reported time is exact;
  7. no mid-race replanning: one committed plan, memoryless greedy modes.
"""

from dataclasses import dataclass

import numpy as np

from senna.env import dynamics, events
from senna.env.scenario import COMPOUNDS, compound_code
from senna.env.twin import EventTrace
from senna.strategy.plans import PitPlan, PlanPolicy, greedy_mode
from senna.strategy.rollout import run_episode

_START = compound_code("MEDIUM")


@dataclass(frozen=True)
class OracleResult:
    plan: PitPlan
    race_time_s: float
    considered: int  # plans enumerated in stage 1
    rolled: int      # plans scored by a full twin roll in stage 2


def stint_cost_table(scenario, trace: EventTrace, compound: int) -> np.ndarray:
    """table[l1, l2] = the deterministic cost of running `compound` from lap l1 (fresh) to
    lap l2 on the trace, greedy energy each lap. A single ghost car — no traffic, no FIFO —
    so on a green trace this is exactly the joint lap-time model summed lap by lap."""
    n = trace.n_laps
    table = np.zeros((n + 1, n + 1))
    burn_kg = scenario.race_fuel_kg / n
    comp = np.array([compound])

    for l1 in range(1, n + 1):
        soc = scenario.usable_soc_mj
        running = 0.0
        for l2 in range(l1, n + 1):
            status = int(trace.status[l2 - 1])
            wetness = float(trace.wetness[l2 - 1])
            fuel_kg = scenario.race_fuel_kg - (l2 - 1) * burn_kg
            mode = greedy_mode(soc, status, _mode_mask(soc, scenario), scenario)
            modes = np.array([mode])
            harvest = np.array([dynamics.per_lap_harvest_mj(scenario, status)])
            request = dynamics.deploy_request_mj(modes, scenario)
            delivered, derate, soc_next = dynamics.resolve_energy(
                np.array([soc]), harvest, request, scenario
            )
            lap_s = dynamics.lap_time_s(
                compound=comp, age=np.array([l2 - l1]), fuel_kg=np.array([fuel_kg]),
                modes=modes, delivered_mj=delivered, request_mj=request, derate_s=derate,
                gap_ahead_s=np.array([np.inf]), wetness=wetness,
                track_status=np.array([status]), driver_s=np.array([0.0]),
                noise_s=np.array([0.0]), scenario=scenario,
            )
            running += float(lap_s[0])
            table[l1, l2] = running
            soc = float(soc_next[0])
    return table


def legal_codes_at(scenario, trace: EventTrace, out_lap: int) -> list:
    """The compounds the action mask would allow for a stop emerging on `out_lap`.

    Legality is decided at pit entry, and the action for lap L is chosen against the mask
    built at the end of lap L-1 — so the wetness that binds is the previous lap's, not the
    out-lap's (E-08). Scoring a plan the mask would have refused is the one way an oracle
    can beat an agent without being better than it.
    """
    validity = scenario.env["compound_validity"]
    wetness = float(trace.wetness[out_lap - 2])
    codes = []
    if wetness <= validity["slick_max_wetness"]:
        # the circuit's fitted slicks only: an unfitted one borrows another compound's
        # curve and would read as free grip (the F08 mask guard, same reasoning)
        codes.extend(compound_code(name) for name in scenario.available_compounds)
    low, high = validity["inter_band"]
    if low <= wetness <= high:
        codes.append(compound_code("INTERMEDIATE"))
    if wetness >= validity["wet_min_wetness"]:
        codes.append(compound_code("WET"))
    return codes


def _pit_loss_at(scenario, status: int) -> float:
    """The pit loss a stop pays under this track status — the same discount the env
    applies (engine._status_pit_multiplier): a bunched field roughly halves relative
    pit loss under SC, less so under VSC (E-03)."""
    mult = scenario.env["pit_loss_mult"]
    if status == events.SC:
        return scenario.pit_loss_mean_s * mult["sc"]
    if status == events.VSC:
        return scenario.pit_loss_mean_s * mult["vsc"]
    return scenario.pit_loss_mean_s


def _ends_dry(scenario, trace: EventTrace) -> bool:
    """Whether the race's last decision is a dry one — the condition under which the mask
    forces the mandatory second compound (F-20). On a frozen trace this is known in
    advance, so the enumerator can apply the rule exactly where the env would."""
    validity = scenario.env["compound_validity"]
    return (int(trace.weather[trace.n_laps - 2]) == events.DRY
            and float(trace.wetness[trace.n_laps - 2]) <= validity["slick_max_wetness"])


def enumerate_plans(scenario, trace: EventTrace, max_stops: int) -> list:
    """Every legal plan of 1..max_stops stops: stop laps strictly increasing, each stint no
    longer than its compound's cliff (so no plan banks on a forced failure), and — in a race
    that ends dry — two distinct compounds run (F-20, MEDIUM start included). The compound
    offered at each stop is whatever the mask would allow at that stop's pit entry, so a wet
    race enumerates intermediates and wets and a dry one enumerates exactly the slicks it
    always did."""
    n = trace.n_laps
    cliff = scenario.env["tyre_failure"]["cliff_age_margin_laps"]
    two_compound_binds = _ends_dry(scenario, trace)

    def cap(code: int) -> int:
        fallback = scenario.env["obs"]["tyre_age_norm_laps"]
        return scenario.deg_max_age.get(COMPOUNDS[code], fallback) + cliff

    plans: list = []

    def extend(prev_out: int, compound: int, stops: list, used: set) -> None:
        if n - prev_out <= cap(compound) and (len(used) >= 2 or not two_compound_binds):
            plans.append(PitPlan(stops=tuple(stops)))
        if len(stops) >= max_stops:
            return
        for out in range(prev_out + 1, min(n, prev_out + cap(compound) + 1) + 1):
            for code in legal_codes_at(scenario, trace, out):
                extend(out, code, [*stops, (out, COMPOUNDS[code])], used | {code})

    extend(1, _START, [], {_START})
    return plans


def _plan_table_cost(plan: PitPlan, tables: dict, scenario, trace: EventTrace) -> float:
    """Cost a plan exactly as the env executes it through PlanPolicy: the pit lap
    itself still runs on the outgoing tyre, and the new compound's age-0 lap is the
    one after — the F07 Stage A gate rolls agents against this number, so a one-lap
    stint offset here would bias the 1.5% bar by most of a second.

    The stop is charged at the pit loss its out-lap actually pays. A flat charge would
    overstate every plan that boxes under a neutralisation by most of half a pit loss
    (E-03), which is enough to drop the genuinely best plans below the top-K roll cut and
    hand M3 a ceiling the agent can beat without deserving to.
    """
    n = trace.n_laps
    cost = 0.0
    compound, start_lap = _START, 1
    for out, name in plan.stops:
        cost += _pit_loss_at(scenario, int(trace.status[out - 1]))
        cost += tables[compound][start_lap, out]
        compound, start_lap = compound_code(name), out + 1
    if start_lap <= n:  # a last-lap stop leaves zero laps on the new tyre
        cost += tables[compound][start_lap, n]
    return cost


def _plan_codes(scenario, trace: EventTrace, plans: list) -> set:
    """Every compound any enumerated plan runs, plus the grid start — the tables stage 1
    needs and no more, so a dry race never pays for an intermediate's O(n^2) table."""
    codes = {_START}
    for plan in plans:
        codes.update(compound_code(name) for _, name in plan.stops)
    return codes


def solve_oracle(scenario, trace: EventTrace, *, cfg: dict, baselines=(),
                 env_cache: dict | None = None) -> OracleResult:
    plans = enumerate_plans(scenario, trace, cfg["max_stops"])
    codes = _plan_codes(scenario, trace, plans) | {
        compound_code(name) for plan in baselines for _, name in plan.stops
    }
    tables = {code: stint_cost_table(scenario, trace, code) for code in codes}

    ranked = sorted(plans, key=lambda plan: _plan_table_cost(plan, tables, scenario, trace))
    finalists = ranked[: cfg["top_k_rolls"]]
    contenders = finalists + [plan for plan in baselines if plan not in finalists]

    # one env for every contender: construction re-parses every physics yaml (~140 ms) and
    # the twin is sticky across resets, so building one per plan spent about an hour of the
    # M3 battery on parsing the same constants 24,000 times
    env = env_cache.get(trace.circuit) if env_cache is not None else None
    if env is None:
        env = _twin_env(trace)
        if env_cache is not None:
            env_cache[trace.circuit] = env
    env.reset(seed=0, options={"twin": trace})

    best_plan, best_time = None, np.inf
    for plan in contenders:
        result = run_episode(env, PlanPolicy(plan, mode="greedy", scenario=scenario), seed=0)
        if result.race_time_s < best_time:
            best_plan, best_time = plan, result.race_time_s
    return OracleResult(
        plan=best_plan, race_time_s=best_time, considered=len(plans), rolled=len(contenders)
    )


def solo_reference(scenario, *, cfg: dict):
    """The Stage A competence bar (5.7): the fastest 1..max_stops plan on a green solo trace,
    scored by the stint tables alone (no traffic, no field). Deterministic — the gate needs
    a stable reference — and it reuses the same enumerator the oracle does."""
    n = scenario.total_laps
    trace = EventTrace.green(scenario.circuit, scenario.era, n, 1, grid=np.array([1]),
                             driver_s=np.zeros(1))
    tables = {
        code: stint_cost_table(scenario, trace, code)
        for code in {_START} | {compound_code(c) for c in scenario.available_compounds}
    }
    plans = enumerate_plans(scenario, trace, cfg["max_stops"])
    best = min(plans, key=lambda plan: _plan_table_cost(plan, tables, scenario, trace))
    return best, _plan_table_cost(best, tables, scenario, trace)


def _mode_mask(soc_mj: float, scenario) -> np.ndarray:
    mask = np.ones(10, dtype=bool)
    if soc_mj < scenario.attack_soc_floor_mj:
        mask[6 + dynamics.ATTACK] = False
    return mask


def _twin_env(trace: EventTrace):
    from senna.env import F1RaceEnv

    return F1RaceEnv(trace.circuit, trace.era, twin=trace)
