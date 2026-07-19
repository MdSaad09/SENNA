"""One episode driver, reused by the baselines, the oracle's twin rolls, the F07 gate
evaluations and the F14 paired comparisons. It seeds the env and the policy on separate
streams — the env off the race seed, the policy off a decoupled sub-stream — so a random
baseline is reproducible without ever sharing draws with the race it runs in.
"""

from dataclasses import dataclass

import numpy as np

_POLICY_STREAM = 91  # a fixed sub-stream so a policy's RNG never collides with the env's


@dataclass(frozen=True)
class EpisodeResult:
    final_position: int
    race_time_s: float
    points: float
    dnf: bool
    pit_laps: list
    compounds: list
    total_reward: float
    actions: list
    snapped: int  # times a policy's proposal was altered to stay legal (replay honesty)


def run_episode(env, policy, *, seed) -> EpisodeResult:
    obs, info = env.reset(seed=seed)
    policy.reset(obs, info, rng=np.random.default_rng([seed, _POLICY_STREAM]))

    actions, total_reward = [], 0.0
    terminated = False
    while not terminated:
        action = np.asarray(policy.act(obs, info, env.action_masks()))
        actions.append(action)
        obs, reward, terminated, _, info = env.step(action)
        total_reward += float(reward)

    return EpisodeResult(
        final_position=info["final_position"],
        race_time_s=info["race_time_s"],
        points=info["points"],
        dnf=info["dnf"],
        pit_laps=info["pit_laps"],
        compounds=info["compounds"],
        total_reward=total_reward,
        actions=actions,
        snapped=int(getattr(policy, "snapped", 0)),
    )
