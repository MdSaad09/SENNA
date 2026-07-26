"""M1's paired legs (A-06), and the robustness table the F06 band decision owes.

Pairing is on event traces, not on seeds. The RNG stream is consumed policy-dependently —
a tyre only rolls for failure past its cliff, a stop only draws service time when it
happens — so two policies handed the same seed diverge in their events after the first
different stop, and the "identical draws" the metric claims would be fiction. The fix F06
built and this module uses: the baseline records its race, and both legs then roll on that
frozen trace.

The stored baseline result is the baseline's own twin roll, never its noisy recording run.
Both sides then face identical deterministic physics, and a policy paired against itself is
a dead tie — the invariant that says the harness measures decisions rather than noise.
"""

from senna import config
from senna.env import F1RaceEnv
from senna.strategy.heuristic import EngineerHeuristic
from senna.strategy.rollout import run_episode
from senna.train.gates import PairedRace


def paired_races(agent_policy, *, banks, era: str = "2026", rival_band: str = "test",
                 configs_dir=None, baseline_factory=None, circuits=None) -> tuple:
    """One PairedRace per (circuit, seed): the baseline records, both legs replay it.

    Returns the pairs and the seeds that produced none, so the published denominator can
    be checked against the bank rather than trusted."""
    heuristic_cfg = config.load("baselines", configs_dir)["heuristic"]
    pairs, dropped = [], []
    for circuit, seeds in banks.items():
        if circuits is not None and circuit not in circuits:
            continue
        live = F1RaceEnv(circuit, era, rival_band=rival_band, record=True,
                         configs_dir=configs_dir)
        replay = F1RaceEnv(circuit, era, configs_dir=configs_dir)
        baseline = (baseline_factory(live.scenario) if baseline_factory is not None
                    else EngineerHeuristic(live.scenario, heuristic_cfg))

        for seed in seeds:
            seed = int(seed)
            run_episode(live, baseline, seed=seed)
            try:
                trace = live.recorded_trace()
            except RuntimeError:
                # the baseline retired before the flag, so there is no trace to pair on.
                # Counted here rather than inferred from another battery: a silently
                # dropped seed biases the finish-ahead rate, which is what the Stage B
                # gate refuses for the same reason
                dropped.append({"circuit": circuit, "seed": seed, "reason": "baseline_dnf"})
                continue

            replay.reset(seed=seed, options={"twin": trace})
            baseline_result = run_episode(replay, baseline, seed=seed)
            replay.reset(seed=seed, options={"twin": trace})
            agent_result = run_episode(replay, agent_policy, seed=seed)

            pairs.append(PairedRace(
                seed=seed, circuit=circuit,
                agent_position=agent_result.final_position, agent_dnf=agent_result.dnf,
                baseline_position=baseline_result.final_position,
                baseline_dnf=baseline_result.dnf,
            ))
    return pairs, dropped


def band_robustness(*, banks, era: str = "2026", configs_dir=None, circuits=None) -> dict:
    """The scripted baselines under both rival bands on the same seeds (INDEX decision,
    19 Jul). The test band pushes each archetype further toward its own character, so a
    baseline's drop between bands measures opponent difficulty on its own — without it, a
    test-band agent result cannot be separated from "the opponents simply got harder".
    """
    heuristic_cfg = config.load("baselines", configs_dir)["heuristic"]
    by_band = {}
    for band in ("train", "test"):
        positions = []
        for circuit, seeds in banks.items():
            if circuits is not None and circuit not in circuits:
                continue
            env = F1RaceEnv(circuit, era, rival_band=band, configs_dir=configs_dir)
            heuristic = EngineerHeuristic(env.scenario, heuristic_cfg)
            positions.extend(run_episode(env, heuristic, seed=int(seed)).final_position
                             for seed in seeds)
        by_band[band] = {
            "mean_position": sum(positions) / len(positions) if positions else 0.0,
            "n_races": len(positions),
        }
    by_band["test_minus_train"] = (by_band["test"]["mean_position"]
                                   - by_band["train"]["mean_position"])
    return by_band
