"""M11 / A-08 — the luck-share decomposition: how much of a finishing position the event
draw explains and how much the decisions do. Pinned here are the three pieces that can be
tested without a race: the decision-seed derivation, the stochastic policy that gives a
deterministic served network a decision distribution at all, and the one-way
random-effects method-of-moments estimator, including both degenerate grids.

No torch, no checkpoints, no env. The estimator arithmetic is separable from the rollouts
that feed it, and keeping it separable is what lets a known intraclass correlation be
recovered from a synthetic grid instead of asserted against whatever the agent happened
to do.
"""

import math

import numpy as np
import pytest

from senna import config
from senna.eval.luck import (
    StochasticSb3Policy,
    decision_seed,
    luck_share,
    variance_components,
)
from tests.eval.conftest import SEED

_POLICY_STREAM = 91  # senna.strategy.rollout's fixed sub-stream — M11 must stay off it


class StubMaskedModel:
    """Stands in for MaskablePPO: it keeps what it was seeded with and what each predict
    was asked for, so the policy's contract can be pinned without a checkpoint."""

    def __init__(self):
        self.seeds = []
        self.predictions = []

    def set_random_seed(self, seed):
        self.seeds.append(int(seed))

    def predict(self, obs, action_masks=None, deterministic=True):
        self.predictions.append({
            "obs": np.asarray(obs),
            "action_masks": np.asarray(action_masks),
            "deterministic": deterministic,
        })
        return np.array([0, 1]), None


def _grid_with_known_components(rng, *, n_seeds, n_reps, between_sd, within_sd):
    row_effects = rng.normal(0.0, between_sd, n_seeds)
    return row_effects[:, None] + rng.normal(0.0, within_sd, (n_seeds, n_reps))


def test_decision_seed_is_reproducible_and_distinct():
    stream = config.load("eval")["m11"]["decision_stream"]

    assert decision_seed(SEED, 0, stream=stream) == decision_seed(SEED, 0, stream=stream)
    assert decision_seed(SEED, 0, stream=stream) != decision_seed(SEED, 1, stream=stream)
    # reps are nested in event seeds: rep 3 of one race is not rep 3 of the next
    assert decision_seed(SEED, 3, stream=stream) != decision_seed(SEED + 1, 3, stream=stream)

    # the decision draws must not consume the same variates the rollout policy does,
    # or the "same events, different decisions" contrast stops being a contrast
    assert stream != _POLICY_STREAM
    assert decision_seed(SEED, 0, stream=stream) != decision_seed(SEED, 0, stream=_POLICY_STREAM)


def test_stochastic_policy_seeds_the_model_and_samples():
    model = StubMaskedModel()
    stream = config.load("eval")["m11"]["decision_stream"]
    seed = decision_seed(SEED, 4, stream=stream)
    policy = StochasticSb3Policy(model, lambda obs: obs, decision_seed=seed)

    obs = np.zeros(32, dtype=np.float32)
    mask = np.array([True, False, True, True, True, True, True, True, False, True])
    policy.reset(obs, {})
    action = policy.act(obs, {}, mask)

    assert model.seeds == [seed]
    call = model.predictions[-1]
    assert call["deterministic"] is False  # a deterministic head has no decision variance
    assert np.array_equal(call["action_masks"], mask)
    assert np.array_equal(np.asarray(action), np.array([0, 1]))


def test_mom_estimator_recovers_known_variance_components():
    rng = np.random.default_rng(SEED)
    between_sd, within_sd = 2.0, 1.0
    grid = _grid_with_known_components(
        rng, n_seeds=200, n_reps=25, between_sd=between_sd, within_sd=within_sd
    )

    components = variance_components(grid)

    assert components["n_seeds"] == 200
    assert components["n_reps"] == 25
    assert components["between"] == pytest.approx(between_sd**2, rel=0.3)
    assert components["within"] == pytest.approx(within_sd**2, rel=0.3)
    true_icc = between_sd**2 / (between_sd**2 + within_sd**2)
    assert components["share"] == pytest.approx(true_icc, abs=0.1)
    assert components["clipped"] is False
    assert components["flag"] is None


def test_mom_clips_a_negative_between_component():
    # every seed produced the same four finishes in a different order, so there is no seed
    # effect at all and the method of moments can only land MSB below MSW
    grid = np.array([
        [1.0, 2.0, 3.0, 4.0],
        [4.0, 3.0, 2.0, 1.0],
        [2.0, 4.0, 1.0, 3.0],
        [3.0, 1.0, 4.0, 2.0],
    ])

    components = variance_components(grid)

    assert components["between"] == 0.0  # a negative variance is not a finding, it is noise
    assert components["clipped"] is True
    assert components["within"] > 0.0
    assert components["share"] == 0.0


def test_degenerate_grids_are_flagged_not_crashed():
    # a collapsed head: every rep of a seed returns the same finish, so the decisions
    # explain nothing and the share is 1.0 by definition rather than by evidence
    collapsed = np.array([[3.0] * 5, [7.0] * 5, [11.0] * 5])
    components = variance_components(collapsed)

    assert components["within"] == 0.0
    assert components["share"] == 1.0
    assert components["flag"] == "degenerate_zero_within"

    constant = np.full((3, 5), 6.0)
    undefined = variance_components(constant)

    assert undefined["flag"] == "undefined_zero_variance"
    assert math.isnan(undefined["share"])  # nothing varied, so no split of the variance exists


def test_luck_share_aggregates_across_circuits_with_a_ci():
    cfg = config.load("eval")
    rng = np.random.default_rng(SEED + 1)
    circuits = ("bahrain_grand_prix", "italian_grand_prix", "monaco_grand_prix",
                "spanish_grand_prix", "japanese_grand_prix")
    grids = {
        circuit: _grid_with_known_components(
            rng, n_seeds=20, n_reps=cfg["m11"]["decision_reps"],
            between_sd=0.5 + 0.5 * i, within_sd=1.0,
        )
        for i, circuit in enumerate(circuits)
    }

    summary = luck_share(grids, cfg=cfg)

    assert summary["n_circuits"] == len(circuits)
    assert set(summary["per_circuit"]) == set(circuits)
    shares = [summary["per_circuit"][circuit]["share"] for circuit in circuits]
    assert summary["mean_share"] == pytest.approx(float(np.mean(shares)))
    assert 0.0 <= summary["ci_low"] <= summary["mean_share"] <= summary["ci_high"] <= 1.0
