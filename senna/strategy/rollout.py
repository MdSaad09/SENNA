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
    laps: tuple = ()  # per-lap rows, only when the caller asks (F14 M4/M9/M10)


def run_episode(env, policy, *, seed, capture: bool = False,
                options: dict | None = None) -> EpisodeResult:
    """capture=True keeps a per-lap row per step — the energy, status and legality detail
    the metric suite needs and the terminal info dict flattens away. It is off by default
    because the training gates roll millions of these and would pay for a list they never
    read.

    options rides through to env.reset, which is how a caller pins a grid slot or hands
    the env a twin trace. Default None, so every existing caller keeps the env's own
    choice of grid."""
    obs, info = env.reset(seed=seed, options=options)
    policy.reset(obs, info, rng=np.random.default_rng([seed, _POLICY_STREAM]))

    actions, laps, total_reward = [], [], 0.0
    terminated = False
    while not terminated:
        action = np.asarray(policy.act(obs, info, env.action_masks()))
        actions.append(action)
        obs, reward, terminated, _, info = env.step(action)
        total_reward += float(reward)
        if capture:
            laps.append(_lap_row(info))

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
        laps=tuple(laps),
    )


def _lap_row(info: dict) -> dict:
    """The metric-facing view of one lap. Violations collapse to a count: which rule was
    broken matters while training a penalty variant, but M10 only asks how many."""
    energy = info["energy"]
    return {
        "lap": info["lap"],
        "track_status": info["track_status"],
        "harvest_mj": energy["harvest_mj"],
        "deploy_mj": energy["deploy_mj"],
        "soc_mj": energy["soc_mj"],
        "derated": energy["derated"],
        "forced_pit": info["events"]["forced_pit"],
        "violations": sum(info["violations"].values()),
    }
