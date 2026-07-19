"""The episode loops behind the competence gates (5.7). Stage A rolls the frozen solo
bank and compares mean race time to the scripted solo reference; Stage B records the
rule-based baseline's races once as EventTraces and replays the agent on those twins —
paired draws, not paired seeds (A-06, INDEX decision 19 Jul); Stage C means the
validation bank's points on the full stochastic env, train band only (E-06).

The baseline result stored per trace is the baseline's own TWIN roll, not the noisy
recording run: both sides of every pair then face identical deterministic physics, so
a policy replayed against its own trace is a dead tie — the property the tests pin.
"""

from dataclasses import dataclass

import numpy as np

from senna import config
from senna.env import F1RaceEnv
from senna.env.scenario import build_scenario
from senna.strategy.heuristic import EngineerHeuristic
from senna.strategy.oracle import solo_reference
from senna.strategy.rollout import EpisodeResult, run_episode
from senna.train.gates import PairedRace, StageAEval, StageCEval

_ERA = "2026"  # the curriculum trains the 2026 problem (5.7); 2024 is F14's era-matched study


@dataclass(frozen=True)
class RecordedRace:
    circuit: str
    seed: int
    trace: object          # EventTrace — kept loose so a stub recorder needs no env
    baseline: EpisodeResult | None


def stage_a_reference(circuit: str, *, configs_dir=None):
    """The Stage A bar: solo_reference on the circuit's scenario with the F06 oracle
    config — deterministic, so one call per run is enough."""
    scenario = build_scenario(circuit, _ERA, configs_dir=configs_dir)
    return solo_reference(scenario, cfg=config.load("baselines", configs_dir)["oracle"])


def run_stage_a_eval(policy, *, step: int, circuit: str, seeds, configs_dir=None) -> StageAEval:
    """Mean return and race time over the frozen solo bank. One env, reset per seed —
    a pure function of the policy, which is what makes plateau comparisons honest."""
    env = F1RaceEnv(circuit, _ERA, solo=True, weather="dry", hazards="none",
                    configs_dir=configs_dir)
    results = [run_episode(env, policy, seed=seed) for seed in seeds]
    return StageAEval(
        step=step,
        mean_return=float(np.mean([r.total_reward for r in results])),
        mean_race_time_s=float(np.mean([r.race_time_s for r in results])),
        dnf_count=sum(r.dnf for r in results),
    )


def record_stage_b_traces(*, banks: dict, overflow, configs_dir=None, recorder=None,
                          traces_dir=None):
    """One RecordedRace per frozen Stage B seed. A recording run that never reaches the
    flag (recorded_trace refuses it) is replaced by the next unused overflow seed, in
    order, and the substitution is returned for the gate log; an exhausted overflow
    raises — silence would bias the finish-ahead rate."""
    if recorder is None:
        recorder = _live_recorder(configs_dir)

    recorded, replaced = [], []
    spare = iter(overflow)
    for circuit, seeds in banks.items():
        for seed in seeds:
            current = seed
            while True:
                try:
                    race = recorder(circuit, current)
                    break
                except RuntimeError:
                    replacement = next(spare, None)
                    if replacement is None:
                        raise
                    replaced.append((current, replacement))
                    current = replacement
            recorded.append(race)
            if traces_dir is not None:
                race.trace.save_npz(traces_dir / f"{circuit}-{race.seed}.npz")
    return recorded, replaced


def _live_recorder(configs_dir):
    """Record the EngineerHeuristic live in the Stage B world (dry, SC/VSC, train band),
    then roll the same policy on the twin for the stored baseline result."""
    heuristic_cfg = config.load("baselines", configs_dir)["heuristic"]
    envs: dict[str, tuple] = {}

    def record(circuit: str, seed: int) -> RecordedRace:
        if circuit not in envs:
            live = F1RaceEnv(circuit, _ERA, rival_band="train", record=True,
                             weather="dry", hazards="sc_vsc", configs_dir=configs_dir)
            replay = F1RaceEnv(circuit, _ERA, configs_dir=configs_dir)
            envs[circuit] = (live, replay, EngineerHeuristic(live.scenario, heuristic_cfg))
        live, replay, heuristic = envs[circuit]

        run_episode(live, heuristic, seed=seed)
        trace = live.recorded_trace()  # RuntimeError here means the recording DNF'd
        replay.reset(seed=seed, options={"twin": trace})
        baseline = run_episode(replay, heuristic, seed=seed)
        return RecordedRace(circuit=circuit, seed=seed, trace=trace, baseline=baseline)

    return record


def run_stage_b_eval(policy, recorded, *, configs_dir=None,
                     env_cache: dict | None = None) -> list[PairedRace]:
    """Replay the agent on every recorded twin and pair it with the stored baseline
    roll. One env per circuit; the twin is swapped per race through reset options.
    Pass env_cache to keep the envs across eval calls — construction re-parses every
    physics yaml, and a Stage B gate check replays 200 races."""
    envs = env_cache if env_cache is not None else {}
    pairs = []
    for race in recorded:
        if race.circuit not in envs:
            envs[race.circuit] = F1RaceEnv(race.circuit, _ERA, configs_dir=configs_dir)
        env = envs[race.circuit]
        env.reset(seed=race.seed, options={"twin": race.trace})
        agent = run_episode(env, policy, seed=race.seed)
        pairs.append(PairedRace(
            seed=race.seed, circuit=race.circuit,
            agent_position=agent.final_position, agent_dnf=agent.dnf,
            baseline_position=race.baseline.final_position, baseline_dnf=race.baseline.dnf,
        ))
    return pairs


def run_stage_c_eval(policy, *, step: int, banks: dict, configs_dir=None,
                     env_cache: dict | None = None) -> StageCEval:
    """Mean points over the validation bank on the full stochastic env — weather,
    red flags, rival draws from the train band (E-06; the test band is F14's)."""
    envs = env_cache if env_cache is not None else {}
    points = []
    for circuit, seeds in banks.items():
        if circuit not in envs:
            envs[circuit] = F1RaceEnv(circuit, _ERA, rival_band="train",
                                      configs_dir=configs_dir)
        points.extend(run_episode(envs[circuit], policy, seed=seed).points
                      for seed in seeds)
    return StageCEval(step=step, mean_points=float(np.mean(points)))


class Sb3Policy:
    """The trained net behind the StrategyPolicy protocol: frozen VecNormalize
    statistics applied once, deterministic head, masks passed through — the only
    place training statistics touch a gate evaluation."""

    def __init__(self, model, normalize_obs):
        self._model = model
        self._normalize_obs = normalize_obs

    def reset(self, obs, info, *, rng=None) -> None:
        pass

    def act(self, obs, info, mask) -> np.ndarray:
        action, _ = self._model.predict(
            self._normalize_obs(obs), action_masks=np.asarray(mask), deterministic=True
        )
        return action
