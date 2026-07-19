"""Scripted baselines and the DP oracle (F06) — everything the agent is measured against.

The offline extractor (extract.py, the one pandas-using module here) is deliberately not
re-exported, so importing senna.strategy never pulls pandas into a process — the same
hot-loop discipline the env keeps (5.6.2).
"""

from senna.strategy.heuristic import EngineerHeuristic
from senna.strategy.oracle import OracleResult, solo_reference, solve_oracle, stint_cost_table
from senna.strategy.plans import PitPlan, PlanPolicy, greedy_mode
from senna.strategy.policy import ScriptedActions, StrategyPolicy
from senna.strategy.random_legal import RandomLegal
from senna.strategy.replay import RealStrategyReplay, load_real_plan
from senna.strategy.rollout import EpisodeResult, run_episode

__all__ = [
    "EngineerHeuristic",
    "EpisodeResult",
    "OracleResult",
    "PitPlan",
    "PlanPolicy",
    "RandomLegal",
    "RealStrategyReplay",
    "ScriptedActions",
    "StrategyPolicy",
    "greedy_mode",
    "load_real_plan",
    "run_episode",
    "solo_reference",
    "solve_oracle",
    "stint_cost_table",
]
