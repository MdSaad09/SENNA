"""The rollout substrate every metric reads from, and the only door to the reserved test
bank (E-06, E-14).

Each eval race is rolled twice on purpose. The live roll is the agent in the deployment
world — stochastic pace, drawn pit service, real tyre-failure hazard — and it is what
M4, M9 and M10 report on, because those metrics ask what the agent actually does. The
twin roll replays the events the live roll realised with the noise switched off, and it
is what M3, M5 and M6 branch from, because those metrics ask what else the agent could
have done in the same race. Comparing an alternative against a noisy baseline would price
the noise, not the decision.

The recorded trace is the object that makes the second question answerable at all: it
pins the grid, the neutralisations, the weather and every rival's applied choice, so an
alternative ego strategy meets exactly the race the agent met (A-05, A-06).
"""

import logging
from dataclasses import dataclass

from senna.env import F1RaceEnv
from senna.strategy.rollout import EpisodeResult, run_episode
from senna.train.seeds import load_reserved_test_bank

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalRace:
    circuit: str
    seed: int
    trace: object              # EventTrace — the events the live roll realised
    agent: EpisodeResult       # the live roll: what the agent did in the stochastic world
    twin: EpisodeResult        # the same policy replayed on its own trace, noise off
    e_dep_mj: float            # the circuit's per-lap deployment budget (M4's denominator)

    @property
    def laps(self):
        return self.agent.laps


def test_bank(configs_dir=None) -> dict:
    """The 480 held-out seeds (24 circuits x 20). The loader refuses every consumer but
    this package, so importing it here is the whole access-control story."""
    return load_reserved_test_bank(configs_dir, consumer="F14")


def record_eval_races(policy, *, banks, era: str = "2026", rival_band: str = "test",
                      configs_dir=None, traces_dir=None, circuits=None) -> tuple:
    """Roll every (circuit, seed) live, capture its trace, then replay the same policy on
    that trace. Returns the races and the seeds that had to be dropped.

    A live roll whose ego retires before the flag has no usable trace — recorded_trace
    refuses to hand back a race it only partly saw, since the tail would silently read as
    green. The test bank has no overflow to substitute from, so those races are excluded
    by seed and counted; a silent drop would bias every metric downstream.
    """
    races, excluded = [], []
    for circuit, seeds in banks.items():
        if circuits is not None and circuit not in circuits:
            continue
        live = F1RaceEnv(circuit, era, rival_band=rival_band, record=True,
                         configs_dir=configs_dir)
        replay = F1RaceEnv(circuit, era, configs_dir=configs_dir)
        for seed in seeds:
            agent = run_episode(live, policy, seed=seed, capture=True)
            try:
                trace = live.recorded_trace()
            except RuntimeError:
                excluded.append({"circuit": circuit, "seed": int(seed), "reason": "ego_dnf"})
                log.info("record %s seed %s: ego retired, no usable trace", circuit, seed)
                continue

            replay.reset(seed=seed, options={"twin": trace})
            twin = run_episode(replay, policy, seed=seed, capture=True)
            if traces_dir is not None:
                traces_dir.mkdir(parents=True, exist_ok=True)
                trace.save_npz(traces_dir / f"{circuit}-{seed}.npz")

            races.append(EvalRace(circuit=circuit, seed=int(seed), trace=trace, agent=agent,
                                  twin=twin, e_dep_mj=float(live.scenario.e_dep_mj)))
    return races, excluded


def roll_live_batch(policy, *, circuit, seeds, era: str = "2026", rival_band: str = "test",
                    configs_dir=None, env=None) -> list:
    """Live races with no trace capture — M7's diversity sweep and M11's decision grid roll
    thousands of these and never look back at the events."""
    if env is None:
        env = F1RaceEnv(circuit, era, rival_band=rival_band, configs_dir=configs_dir)
    return [run_episode(env, policy, seed=int(seed), capture=True) for seed in seeds]
