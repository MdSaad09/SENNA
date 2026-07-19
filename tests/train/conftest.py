"""Shared builders for the F07 training suite: hand-built gate histories, paired-race
sets and a tiny-config tree for the wiring smoke. Suite seed 846 keeps it apart from
fits (99), synth (271), env (512) and strategy (704), so a cross-suite coincidence
cannot mask a bug (5.5.5). No SB3 or wandb here — the heavy imports stay inside the
test modules that need them.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from senna.train.gates import PairedRace, StageAEval

SEED = 846
CIRCUIT = "bahrain_grand_prix"  # a raced 2026 event with real fitted params in configs
REPO_CONFIGS = Path(__file__).resolve().parents[2] / "configs"

# a plausible solo race time — the gates only ever see deltas relative to it
REFERENCE_TIME_S = 5400.0
EVAL_STEP = 49_152  # the Stage A/B eval cadence from the plan; any fixed spacing would do


def a_history(*mean_returns, times=None, dnf_counts=None, step0=EVAL_STEP):
    """A Stage A eval history at a fixed cadence; times default to exactly the bar."""
    if times is None:
        times = [REFERENCE_TIME_S] * len(mean_returns)
    if dnf_counts is None:
        dnf_counts = [0] * len(mean_returns)
    return [
        StageAEval(step=step0 + i * EVAL_STEP, mean_return=r, mean_race_time_s=t, dnf_count=d)
        for i, (r, t, d) in enumerate(zip(mean_returns, times, dnf_counts, strict=True))
    ]


def pairs(n, ahead_frac, *, ahead_delta=2, rest_delta=-1, circuit=CIRCUIT):
    """n paired races, round(n * ahead_frac) with the agent ahead, none DNF'd.

    rest_delta=0 makes the remainder exact ties; negative puts the baseline ahead.
    """
    n_ahead = round(n * ahead_frac)
    built = []
    for i in range(n):
        if i < n_ahead:
            agent, baseline = 4, 4 + ahead_delta
        else:
            agent, baseline = 8, 8 + rest_delta
        built.append(
            PairedRace(
                seed=SEED * 1000 + i, circuit=circuit, agent_position=agent,
                agent_dnf=False, baseline_position=baseline, baseline_dnf=False,
            )
        )
    return built


@pytest.fixture
def tiny_configs(tmp_path):
    """The repo configs with training and curriculum shrunk so a stage fits in seconds:
    n_steps 64, eval every 128 steps, every budget ceiling 256."""
    configs_dir = tmp_path / "configs"
    shutil.copytree(REPO_CONFIGS, configs_dir)

    training_path = configs_dir / "training.yaml"
    training = yaml.safe_load(training_path.read_text())
    training["ppo"]["n_steps"] = 64
    training["ppo"]["batch_size"] = 64
    training_path.write_text(yaml.safe_dump(training))

    curriculum_path = configs_dir / "curriculum.yaml"
    curriculum = yaml.safe_load(curriculum_path.read_text())
    for stage in curriculum["stages"].values():
        stage["budget_steps"] = 256
        stage["eval_every_steps"] = 128
    curriculum_path.write_text(yaml.safe_dump(curriculum))

    return configs_dir
