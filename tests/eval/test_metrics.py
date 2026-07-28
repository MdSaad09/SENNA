"""Metric arithmetic on races whose answer is known by construction (5.12 M1, M4, M7,
M9, M10). Every function here takes already-rolled results, so the numbers Chapter 7
prints are checkable without a simulator: a hand-built set of paired races has one
correct mean delta, one correct finish-ahead rate, and one correct verdict against the
targets in configs/eval.yaml.

The sign convention is the load-bearing part. M1 delegates to senna.train.gates
pair_outcome — a finisher beats a DNF, both-DNF is no evidence, a dead heat counts
against the agent — and this module cross-checks the metric against that function
directly rather than restating the rule.
"""

import math
from dataclasses import dataclass
from statistics import fmean

import pytest

from senna import config
from senna.eval.metrics import (
    energy_utilisation,
    legality_audit,
    paired_position_delta,
    strategy_diversity,
    tyre_failure_rate,
)
from senna.strategy.rollout import EpisodeResult
from senna.train.gates import PairedRace, pair_outcome
from tests.eval.conftest import CIRCUIT, SEED

EVAL_CFG = config.load("eval")
M1_CFG = {**EVAL_CFG["m1"], **EVAL_CFG["bootstrap"]}
M4_CFG = EVAL_CFG["m4"]

E_DEP_MJ = 5.0  # a plausible per-lap deployment budget; only the ratio matters here
SECOND_CIRCUIT = "monaco_grand_prix"


@dataclass
class HandBuiltRace:
    """What the M4/M9/M10 metrics consume: per-lap rows plus the episode they came from."""

    laps: list
    agent: EpisodeResult
    e_dep_mj: float = E_DEP_MJ


def paired_races(deltas, *, circuit=CIRCUIT):
    """One classified pair per position delta, positive meaning the agent finished that
    many places ahead. Both cars straddle mid-grid, so even a 15-place delta lands on a
    real 22-car finishing position."""
    built = []
    for i, delta in enumerate(deltas):
        agent_position = 12 - delta // 2
        built.append(
            PairedRace(
                seed=SEED * 1000 + i, circuit=circuit,
                agent_position=agent_position, agent_dnf=False,
                baseline_position=agent_position + delta, baseline_dnf=False,
            )
        )
    return built


def episode(*, pit_laps=(18,), compounds=("SOFT", "MEDIUM"), snapped=0, position=6):
    return EpisodeResult(
        final_position=position, race_time_s=5400.0, points=8.0, dnf=False,
        pit_laps=list(pit_laps), compounds=list(compounds), total_reward=0.0,
        actions=[], snapped=snapped,
    )


def lap_row(lap, *, track_status="green", deploy_mj=0.0, harvest_mj=0.0, soc_mj=2.0,
            derated=False, forced_pit=False, violations=0):
    return {
        "lap": lap, "track_status": track_status, "harvest_mj": harvest_mj,
        "deploy_mj": deploy_mj, "soc_mj": soc_mj, "derated": derated,
        "forced_pit": forced_pit, "violations": violations,
    }


def race(laps, *, agent=None, e_dep_mj=E_DEP_MJ):
    return HandBuiltRace(laps=laps, agent=agent if agent is not None else episode(),
                         e_dep_mj=e_dep_mj)


def test_m1_reproduces_known_deltas_on_hand_built_races():
    # 15 races two places up, 5 races one place down: mean +1.25 over 20 pairs
    outcome = paired_position_delta(paired_races([2] * 15 + [-1] * 5), cfg=M1_CFG)

    assert outcome["n"] == 20
    assert outcome["mean_delta"] == pytest.approx(1.25)
    assert outcome["finish_ahead_rate"] == pytest.approx(0.75)
    assert outcome["target"] == M1_CFG["target_mean_delta"] == 1.0
    assert outcome["ci_low"] < outcome["mean_delta"] < outcome["ci_high"]
    assert outcome["excludes_zero"]
    assert outcome["met"]

    # the same shape at half the gap: a clean CI is not enough, +1.0 is the bar
    narrow = paired_position_delta(paired_races([1] * 15 + [-1] * 5), cfg=M1_CFG)
    assert narrow["mean_delta"] == pytest.approx(0.5)
    assert narrow["excludes_zero"]
    assert not narrow["met"]

    # a big mean built out of a huge spread: the CI straddles zero, so the claim fails
    volatile = paired_position_delta(
        paired_races([15, -10, 15, -10, 15, -10, 15, -10, 5, -5]), cfg=M1_CFG
    )
    assert volatile["mean_delta"] == pytest.approx(2.0)
    assert volatile["ci_low"] < 0.0 < volatile["ci_high"]
    assert not volatile["excludes_zero"]
    assert not volatile["met"]


def test_m1_delta_sign_matches_pair_outcome():
    beat_a_dnf = PairedRace(
        seed=SEED, circuit=CIRCUIT, agent_position=5, agent_dnf=False,
        baseline_position=18, baseline_dnf=True,
    )
    both_out = PairedRace(
        seed=SEED + 1, circuit=CIRCUIT, agent_position=19, agent_dnf=True,
        baseline_position=20, baseline_dnf=True,
    )
    dead_heat = PairedRace(
        seed=SEED + 2, circuit=CIRCUIT, agent_position=7, agent_dnf=False,
        baseline_position=7, baseline_dnf=False,
    )

    assert pair_outcome(5, False, 18, True) == (True, 13)
    assert pair_outcome(19, True, 20, True) == (False, 0)  # both out: no evidence, not +1
    assert pair_outcome(7, False, 7, False) == (False, 0)  # a tie counts against the agent

    races = [beat_a_dnf, both_out, dead_heat]
    outcome = paired_position_delta(races, cfg=M1_CFG)
    outcomes = [
        pair_outcome(p.agent_position, p.agent_dnf, p.baseline_position, p.baseline_dnf)
        for p in races
    ]

    assert outcome["n"] == 3
    assert outcome["mean_delta"] == pytest.approx(fmean(delta for _, delta in outcomes))
    assert outcome["mean_delta"] == pytest.approx(13 / 3)
    assert outcome["finish_ahead_rate"] == pytest.approx(fmean(float(a) for a, _ in outcomes))
    assert outcome["finish_ahead_rate"] == pytest.approx(1 / 3)


def test_m4_counts_green_laps_only():
    green = [lap_row(lap, deploy_mj=4.6) for lap in range(1, 11)]
    # deployment under a neutralisation is not a strategic choice, so absurd values on
    # those laps must not reach either the utilisation or the derate denominator
    neutralised = [
        lap_row(11, track_status="sc", deploy_mj=100.0, derated=True),
        lap_row(12, track_status="vsc", deploy_mj=100.0, derated=True),
        lap_row(13, track_status="red", deploy_mj=100.0, derated=True),
    ]
    outcome = energy_utilisation([race(green + neutralised)], cfg=M4_CFG)

    assert outcome["n_green_laps"] == 10
    assert outcome["utilisation"] == pytest.approx(0.92)
    assert outcome["derate_share"] == pytest.approx(0.0)
    assert outcome["target"] == M4_CFG["target_utilisation"] == 0.90
    assert outcome["max_derate_share"] == M4_CFG["max_derate_share"] == 0.05
    assert outcome["met"]

    derated_green = [lap_row(1, deploy_mj=4.6, derated=True), *green[1:]]
    over_the_bar = energy_utilisation([race(derated_green + neutralised)], cfg=M4_CFG)

    assert over_the_bar["utilisation"] == pytest.approx(0.92)
    assert over_the_bar["derate_share"] == pytest.approx(0.1)
    assert not over_the_bar["met"]  # 5.12 reads utilisation and derates as a pair


def test_m7_entropy_is_zero_for_one_strategy_and_rises_with_variety():
    one_stop_soft = episode(pit_laps=[18], compounds=["SOFT", "MEDIUM"])
    two_stop_medium = episode(pit_laps=[14, 32], compounds=["MEDIUM", "SOFT", "SOFT"])

    single = strategy_diversity({CIRCUIT: [one_stop_soft] * 4})
    assert single["per_circuit"][CIRCUIT]["entropy_nats"] == pytest.approx(0.0)
    assert single["per_circuit"][CIRCUIT]["n_races"] == 4
    assert single["mean_entropy_nats"] == pytest.approx(0.0)

    split = strategy_diversity({CIRCUIT: [one_stop_soft, two_stop_medium] * 3})
    varied = split["per_circuit"][CIRCUIT]
    assert varied["entropy_nats"] == pytest.approx(math.log(2), abs=1e-9)
    assert varied["n_races"] == 6
    assert len(varied["histogram"]) == 2
    assert sum(varied["histogram"].values()) == 6

    # the headline averages circuits, not races: a busy circuit cannot drown a dull one
    both = strategy_diversity(
        {CIRCUIT: [one_stop_soft] * 4, SECOND_CIRCUIT: [one_stop_soft, two_stop_medium] * 3}
    )
    assert both["mean_entropy_nats"] == pytest.approx(math.log(2) / 2, abs=1e-9)


def test_m9_failure_rate_is_per_hundred_races():
    finished_on_its_tyres = [race([lap_row(lap) for lap in range(1, 6)]) for _ in range(49)]
    # one race loses two tyres; the denominator is races, so it still counts once
    lost_a_tyre = race(
        [lap_row(1), lap_row(2, forced_pit=True), lap_row(3), lap_row(4, forced_pit=True)]
    )

    outcome = tyre_failure_rate([*finished_on_its_tyres, lost_a_tyre])
    assert outcome["n_races"] == 50
    assert outcome["n_failures"] == 1
    assert outcome["failures_per_100"] == pytest.approx(2.0)

    clean = tyre_failure_rate(finished_on_its_tyres)
    assert clean["n_failures"] == 0
    assert clean["failures_per_100"] == pytest.approx(0.0)


def test_m10_counts_snapped_and_violations():
    legal = [race([lap_row(lap) for lap in range(1, 4)]) for _ in range(3)]
    audit = legality_audit(legal)

    assert audit["n_races"] == 3
    assert audit["illegal_actions"] == 0
    assert audit["snapped"] == 0
    assert audit["clean"]

    # a snapped stop is legal but not what the policy asked for; the honesty counter
    # means the audit stops calling the set clean (A-07 replay honesty)
    altered = legality_audit([*legal, race([lap_row(1)], agent=episode(snapped=1))])
    assert altered["snapped"] == 1
    assert altered["illegal_actions"] == 0
    assert not altered["clean"]

    coerced = legality_audit([*legal, race([lap_row(1), lap_row(2, violations=2)])])
    assert coerced["illegal_actions"] == 2
    assert coerced["snapped"] == 0
    assert not coerced["clean"]
