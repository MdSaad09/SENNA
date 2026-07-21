"""Distillation data (5.8.2): per decision, what the policy saw, what it preferred
and what it played. The unmasked head distributions are the distillation targets —
they are a pure function of the observation, exactly the 5.8.1 preference score. The
mask is not obs-recoverable (per-circuit fitted compounds, the last-lap F-20
trigger), so it is recorded alongside instead, and fidelity is later measured after
applying it.
"""

from dataclasses import dataclass

import numpy as np
import torch as th

from senna.strategy.rollout import run_episode


@dataclass(frozen=True)
class DecisionRecord:
    obs: np.ndarray
    pit_probs_unmasked: np.ndarray
    mode_probs_unmasked: np.ndarray
    pit_probs_masked: np.ndarray
    mode_probs_masked: np.ndarray
    mask: np.ndarray        # flat (10,) bools, pit head then mode head
    reasons: dict           # reason code per masked-off action, from the env info dict
    circuit: str
    seed: int
    lap: int
    track_status: str
    pit_action: int
    mode_action: int


class DecisionLogger:
    """Wraps the frozen Sb3Policy behind the StrategyPolicy protocol and records one
    DecisionRecord per act() call. The protocol's reset() carries no episode
    identity, so the logger is told circuit and seed up front — one logger, one
    episode."""

    def __init__(self, inner, *, circuit: str, seed: int):
        self._inner = inner
        self._circuit = circuit
        self._seed = seed
        self.records: list[DecisionRecord] = []

    def reset(self, obs, info, *, rng=None) -> None:
        self._inner.reset(obs, info, rng=rng)

    def act(self, obs, info, mask) -> np.ndarray:
        action = np.asarray(self._inner.act(obs, info, mask))
        mask_flat = np.asarray(mask, dtype=bool)

        policy = self._inner.model.policy
        with th.no_grad():
            tensor, _ = policy.obs_to_tensor(self._inner.normalize_obs(obs))
            dist = policy.get_distribution(tensor)
            pit_unmasked, mode_unmasked = _head_probs(dist)
            dist.apply_masking(th.as_tensor(mask_flat).unsqueeze(0))
            pit_masked, mode_masked = _head_probs(dist)

        self.records.append(DecisionRecord(
            obs=np.asarray(obs, dtype=np.float32).copy(),
            pit_probs_unmasked=pit_unmasked, mode_probs_unmasked=mode_unmasked,
            pit_probs_masked=pit_masked, mode_probs_masked=mode_masked,
            mask=mask_flat.copy(),
            reasons=dict(info["mask"]["reasons"]),
            circuit=self._circuit, seed=self._seed,
            lap=int(info["lap"]), track_status=info["track_status"],
            pit_action=int(action[0]), mode_action=int(action[1]),
        ))
        return action


def _head_probs(dist) -> tuple[np.ndarray, np.ndarray]:
    pit, mode = dist.distributions
    return pit.probs.numpy()[0].copy(), mode.probs.numpy()[0].copy()


def log_episode(env, policy, *, circuit: str, seed: int) -> list[DecisionRecord]:
    """One evaluation rollout, decisions captured. The episode outcome is discarded —
    distillation cares what the policy preferred, not how the race went."""
    logger = DecisionLogger(policy, circuit=circuit, seed=seed)
    run_episode(env, logger, seed=seed)
    return logger.records


def derived_seeds(base: int, floor: int, count: int) -> list[int]:
    """Deterministic episode seeds for the distillation rollouts, all at or above the
    floor. Every frozen bank seed (configs/seeds.yaml) is six digits, so a 1e6 floor
    makes these disjoint from train, validation and the reserved F14 test bank by
    construction — no list to maintain, nothing to collide (E-06)."""
    rng = np.random.default_rng(base)
    seeds: list[int] = []
    seen: set[int] = set()
    while len(seeds) < count:
        for seed in rng.integers(floor, 2**31, size=count).tolist():
            if seed not in seen:
                seen.add(seed)
                seeds.append(seed)
                if len(seeds) == count:
                    break
    return seeds


def split_by_episode(records, holdout_frac: float, *, seed: int):
    """Fidelity holdout at episode granularity: consecutive laps are near-duplicates,
    and a state-level split would leak them across the boundary and inflate the
    badge (E-14 discipline, applied to fidelity)."""
    episodes = sorted({(r.circuit, r.seed) for r in records})
    n_holdout = max(1, round(len(episodes) * holdout_frac))
    if n_holdout >= len(episodes):
        raise ValueError(
            f"holdout would take {n_holdout} of {len(episodes)} episodes — "
            "log more rollouts or lower distill.holdout_episode_frac"
        )
    order = np.random.default_rng(seed).permutation(len(episodes))
    held = {episodes[i] for i in order[:n_holdout]}
    train = [r for r in records if (r.circuit, r.seed) not in held]
    holdout = [r for r in records if (r.circuit, r.seed) in held]
    return train, holdout
