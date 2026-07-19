"""The distillation dataset (5.8.2): a DecisionLogger that records what the policy
saw and preferred, seeds structurally disjoint from every frozen bank (E-06), and an
episode-level holdout so neighbouring laps can never leak the fidelity badge up
(E-14 applied to fidelity). SB3 loads at module scope because the logger test wraps
a real MaskablePPO.
"""

import numpy as np
import pytest

from senna import config
from senna.env import F1RaceEnv
from senna.explain.dataset import DecisionLogger, DecisionRecord, derived_seeds, split_by_episode
from senna.strategy.rollout import run_episode
from senna.train.evals import Sb3Policy
from senna.train.seeds import load_banks
from tests.explain.conftest import CIRCUIT, SEED


def test_probs_respect_masks(tiny_agent):
    model, venv = tiny_agent
    env = F1RaceEnv(CIRCUIT, "2026")
    logger = DecisionLogger(Sb3Policy(model, venv.normalize_obs), circuit=CIRCUIT, seed=SEED)

    played = run_episode(env, logger, seed=SEED)

    assert len(logger.records) >= 10  # one record per act() call, a race is ~57 laps
    for record, action in zip(logger.records, played.actions, strict=True):
        assert record.circuit == CIRCUIT
        assert record.seed == SEED
        assert record.obs.shape == (32,)

        # the distillation targets are proper distributions over each full head
        assert np.sum(record.pit_probs_unmasked) == pytest.approx(1.0, abs=1e-6)
        assert np.sum(record.mode_probs_unmasked) == pytest.approx(1.0, abs=1e-6)

        # the masked view carries ~0 on every action the mask took off the table
        pit_mask, mode_mask = record.mask[:6], record.mask[6:]
        assert np.all(record.pit_probs_masked[~pit_mask] < 1e-6)
        assert np.all(record.mode_probs_masked[~mode_mask] < 1e-6)
        assert np.sum(record.pit_probs_masked) == pytest.approx(1.0, abs=1e-6)
        assert np.sum(record.mode_probs_masked) == pytest.approx(1.0, abs=1e-6)

        # the record holds the action actually played, and it was legal
        assert record.pit_action == action[0]
        assert record.mode_action == action[1]
        assert pit_mask[record.pit_action]
        assert mode_mask[record.mode_action]


def _lap_record(circuit: str, seed: int, lap: int) -> DecisionRecord:
    uniform_pit = np.full(6, 1 / 6)
    uniform_mode = np.full(4, 0.25)
    return DecisionRecord(
        obs=np.zeros(32, dtype=np.float32),
        pit_probs_unmasked=uniform_pit, mode_probs_unmasked=uniform_mode,
        pit_probs_masked=uniform_pit, mode_probs_masked=uniform_mode,
        mask=np.ones(10, dtype=bool), reasons={},
        circuit=circuit, seed=seed, lap=lap, track_status="green",
        pit_action=0, mode_action=1,
    )


def test_holdout_split_is_episode_level():
    holdout_frac = config.get(config.load("explain"), "distill.holdout_episode_frac")
    records = [
        _lap_record(circuit, seed, lap)
        for circuit in ("bahrain_grand_prix", "italian_grand_prix")
        for seed in (1_000_101, 1_000_202, 1_000_303)
        for lap in range(1, 6)
    ]

    train, holdout = split_by_episode(records, holdout_frac, seed=SEED)

    assert len(train) + len(holdout) == len(records)
    assert holdout and train  # a badge measured on nothing would be vacuous
    # consecutive laps are near-duplicates: an episode lives wholly on one side
    train_episodes = {(r.circuit, r.seed) for r in train}
    holdout_episodes = {(r.circuit, r.seed) for r in holdout}
    assert not train_episodes & holdout_episodes

    again = split_by_episode(records, holdout_frac, seed=SEED)
    assert {(r.circuit, r.seed) for r in again[1]} == holdout_episodes


def test_derived_seeds_disjoint_from_banks():
    cfg = config.load("explain")
    base = config.get(cfg, "distill.rollout_seed_base")
    floor = config.get(cfg, "distill.seed_floor")

    seeds = derived_seeds(base, floor, 512)
    assert len(seeds) == 512
    assert len(set(seeds)) == 512  # one seed, one episode — never a duplicate rollout
    assert all(s >= floor for s in seeds)
    assert list(derived_seeds(base, floor, 512)) == list(seeds)  # frozen, not a fresh draw

    banks = load_banks()
    bank_seeds = set(banks.stage_a) | set(banks.stage_b_overflow)
    for per_circuit in (*banks.stage_b.values(), *banks.stage_c_validation.values()):
        bank_seeds.update(per_circuit)
    # every frozen bank seed is six digits, so a floor of 1e6 is disjoint by construction
    assert floor > max(bank_seeds)
    assert not set(seeds) & bank_seeds
