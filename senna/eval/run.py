"""`make suite` — roll every metric battery against the frozen model and write both stores.

Two stores, because "deterministic given the run store" has to be checkable from a clone.
The raw store under models/ holds episode-grain detail and is gitignored; the committed
store under docs/results/F14/store holds the smallest grain the report needs, and
`make report` reads only that.

Order matters in one place: the recorded races are the substrate M3, M5 and M6 branch
from, so they are rolled once and reused rather than re-rolled per metric.

    python -m senna.eval.run --smoke            # a few seeds per circuit, proves the wiring
    python -m senna.eval.run --only m1,m4
"""

import argparse
import json
import logging
from pathlib import Path

from senna import config
from senna.eval import metrics, pairing, record, store
from senna.eval.afterstate import neutralisation_windows
from senna.eval.luck import StochasticSb3Policy, decision_seed, luck_share, variance_components
from senna.eval.oracle_regret import race_regret, regret_distribution
from senna.eval.pit_accuracy import pit_window_accuracy, stop_optima
from senna.eval.sc_quality import sc_decision_quality, window_verdict

log = logging.getLogger(__name__)

_BATTERIES = ("m1", "m2", "m3", "m4", "m5", "m6", "m7", "m9", "m10", "m11", "bands")


def load_frozen_policy(triplet_dir: Path):
    """The served model behind the StrategyPolicy protocol — the F09/F10 recipe, with the
    VecNormalize statistics frozen (F-23) so evaluation sees the scales training saw."""
    from stable_baselines3.common.vec_env import DummyVecEnv

    from senna.env import F1RaceEnv
    from senna.train.checkpoints import load_triplet
    from senna.train.evals import Sb3Policy
    from senna.train.seeds import load_banks

    circuit = next(iter(load_banks().stage_c_validation))
    model, venv = load_triplet(triplet_dir, DummyVecEnv([lambda: F1RaceEnv(circuit, "2026")]))
    manifest = json.loads((triplet_dir / "manifest.json").read_text())
    return Sb3Policy(model, venv.normalize_obs), model, venv, manifest


def run_suite(*, only=None, smoke: bool = False, configs_dir=None, models_dir=None) -> dict:
    cfg = config.load("eval", configs_dir)
    models = Path(models_dir) if models_dir else config.REPO_ROOT / "models"
    raw = models / "eval"
    wanted = set(only or _BATTERIES)

    policy, model, venv, manifest = load_frozen_policy(models / "headline")
    banks = record.test_bank(configs_dir)
    if smoke:
        banks = {c: seeds[:2] for c, seeds in list(banks.items())[:2]}
    # a smoke run never writes where the report reads: its rows would carry the same
    # provenance as a full run and print under the full run's claim
    committed = config.REPO_ROOT / cfg["store"]["committed_dir"] / ("smoke" if smoke else "")

    envelope = store.envelope(
        model_versions={"headline": manifest["model_version"]},
        config_hash=manifest["fingerprint"],
        seeds_fingerprint=config.fingerprint(["seeds"], configs_dir),
        scope={"smoke": bool(smoke), "circuits": len(banks),
               "seeds_per_circuit": max(len(s) for s in banks.values()),
               "batteries": sorted(wanted)},
    )
    raw.mkdir(parents=True, exist_ok=True)
    written = {}

    log.info("recording %d races on the held-out bank", sum(len(s) for s in banks.values()))
    races, excluded = record.record_eval_races(
        policy, banks=banks, configs_dir=configs_dir, traces_dir=raw / "traces"
    )
    log.info("recorded %d races (%d excluded)", len(races), len(excluded))

    if "m1" in wanted:
        pairs, dropped = pairing.paired_races(policy, banks=banks,
                                              configs_dir=configs_dir)
        payload = metrics.paired_position_delta(pairs, cfg={**cfg["m1"], **cfg["bootstrap"]})
        payload["dropped_pairs"] = dropped
        payload["recording_exclusions"] = excluded
        payload["per_pair"] = [
            {"circuit": p.circuit, "seed": p.seed, "agent": p.agent_position,
             "baseline": p.baseline_position, "agent_dnf": p.agent_dnf,
             "baseline_dnf": p.baseline_dnf}
            for p in pairs
        ]
        written["m1_pairs"] = store.write_metric(committed, "m1_pairs", payload,
                                                 envelope=envelope)

    if "m4" in wanted:
        written["m4_energy"] = store.write_metric(
            committed, "m4_energy",
            metrics.energy_utilisation(
                races,
                cfg={**cfg["m4"],
                     "intra_lap_share": config.load("env", configs_dir)["harvest"]
                     ["intra_lap_share"]}),
            envelope=envelope)

    if "m9" in wanted:
        written["m9_failures"] = store.write_metric(
            committed, "m9_failures", metrics.tyre_failure_rate(races), envelope=envelope)

    if "m10" in wanted:
        written["m10_legality"] = store.write_metric(
            committed, "m10_legality", metrics.legality_audit(races), envelope=envelope)

    if "m3" in wanted:
        oracle_envs, oracle_scenarios = {}, {}
        rows = [race_regret(race, configs_dir=configs_dir, env_cache=oracle_envs,
                            scenarios=oracle_scenarios) for race in races]
        written["m3_regret"] = store.write_metric(
            committed, "m3_regret", regret_distribution(rows), envelope=envelope)

    if "m5" in wanted:
        written["m5_windows"] = store.write_metric(
            committed, "m5_windows", _sc_quality(races, cfg, policy, configs_dir),
            envelope=envelope)

    if "m6" in wanted:
        written["m6_pits"] = store.write_metric(
            committed, "m6_pits", _pit_accuracy(races, cfg, configs_dir), envelope=envelope)

    if "m7" in wanted:
        diversity = _diversity(policy, banks, cfg, configs_dir, smoke=smoke)
        written["m7_entropy"] = store.write_metric(committed, "m7_entropy", diversity,
                                                   envelope=envelope)

    if "m11" in wanted:
        written["m11_decomposition"] = store.write_metric(
            committed, "m11_decomposition",
            _luck(model, venv, banks, cfg, configs_dir, smoke=smoke), envelope=envelope)

    if "m2" in wanted:
        payload, era_version = _counterfactuals(cfg, models, configs_dir)
        written["m2_races"] = store.write_metric(
            committed, "m2_races", payload,
            envelope={**envelope,
                      "model_versions": {**envelope["model_versions"], "era2024": era_version}})

    if "bands" in wanted:
        written["band_robustness"] = store.write_metric(
            committed, "band_robustness",
            pairing.band_robustness(banks=banks, configs_dir=configs_dir), envelope=envelope)

    log.info("wrote %d metric files to %s", len(written), committed)
    return written


def _counterfactuals(cfg, models, configs_dir) -> tuple:
    """M2 over the ten frozen races. Runs on the era-matched model where one has been
    baked; falls back to the frozen 2026 headline and records that in the payload, because
    a counterfactual scored by the wrong-era model is a different claim (F-24)."""
    import asyncio

    from senna.data.db import database_url, engine_for
    from senna.eval import harness

    era = cfg["era_finetune"]["era"]
    triplet = models / "era2024"
    if triplet.exists():
        policy, _, _, manifest = load_frozen_policy(triplet)
        era_version = manifest["model_version"]
    else:
        policy, _, _, manifest = load_frozen_policy(models / "headline")
        era_version = "pending-F14"
        log.warning("no era-matched triplet: M2 falls back to the 2026 headline")

    async def gather() -> list:
        engine = engine_for(database_url())
        rows = []
        try:
            async with engine.connect() as conn:
                for race_cfg in cfg["m2"]["races"]:
                    inputs = await harness.load_race(
                        conn, season=race_cfg["season"], round_number=race_cfg["round"])
                    rows.append(harness.run_counterfactual(
                        race_cfg, inputs, policy=policy, era=era, cfg=cfg,
                        configs_dir=configs_dir))
                    log.info("counterfactual %s %s %s: mean delta %+.2f",
                             race_cfg["season"], race_cfg["circuit"], race_cfg["driver"],
                             rows[-1]["mean_delta"])
        finally:
            await engine.dispose()
        return rows

    payload = harness.summarise(asyncio.run(gather()), cfg=cfg)
    payload["era_matched_model"] = era_version
    return payload, era_version


def _sc_quality(races, cfg, policy, configs_dir) -> dict:
    from senna.env import F1RaceEnv

    verdicts, envs = [], {}
    for race in races:
        # one env per circuit, not per race: construction re-parses every physics yaml and
        # the twin swaps through reset options anyway
        if race.circuit not in envs:
            envs[race.circuit] = F1RaceEnv(race.circuit, "2026", configs_dir=configs_dir)
        env = envs[race.circuit]
        env.reset(seed=race.seed, options={"twin": race.trace})
        for window in neutralisation_windows(race.trace, last_lap=len(race.twin.actions)):
            verdicts.append(window_verdict(window, race=race.twin, scenario=env.scenario,
                                           env=env, cfg=cfg["m5"], tail_policy=policy))
    payload = sc_decision_quality(verdicts, cfg=cfg["m5"])
    payload["per_window"] = verdicts
    return payload


def _pit_accuracy(races, cfg, configs_dir) -> dict:
    from senna.env import F1RaceEnv, events

    rows, envs = [], {}
    for race in races:
        if race.circuit not in envs:
            envs[race.circuit] = F1RaceEnv(race.circuit, "2026", configs_dir=configs_dir)
        env = envs[race.circuit]
        env.reset(seed=race.seed, options={"twin": race.trace})
        for index, stop_lap in enumerate(race.twin.pit_laps):
            # a stop under a red flag is a free tyre change, not a timing decision (E-04)
            red = bool(race.trace.status[stop_lap - 1] == events.RED)
            optima = ([] if red else
                      stop_optima(race.twin, index, scenario=env.scenario,
                                  trace=race.trace, env=env))
            rows.append({"circuit": race.circuit, "seed": race.seed, "stop_lap": stop_lap,
                         "optimal_laps": optima,
                         "excluded": "red_flag" if red else None})
    payload = pit_window_accuracy(rows, cfg={**cfg["m6"], "bootstrap": cfg["bootstrap"]})
    payload["per_stop"] = rows
    return payload


def _diversity(policy, banks, cfg, configs_dir, *, smoke: bool) -> dict:
    """M7 draws its own seeds rather than reusing the test bank: the bank is 20 races per
    circuit and an entropy over 20 draws is mostly sampling noise. The derivation is
    documented and disjoint from every frozen bank."""
    import numpy as np

    per_circuit = 20 if smoke else cfg["m7"]["races_per_circuit"]
    stream = cfg["m7"]["seed_stream"]
    races_by_circuit = {}
    for circuit in banks:
        seeds = np.random.SeedSequence([_circuit_key(circuit), stream]).generate_state(
            per_circuit)
        races_by_circuit[circuit] = record.roll_live_batch(
            policy, circuit=circuit, seeds=seeds.tolist(), configs_dir=configs_dir)
    payload = metrics.strategy_diversity(races_by_circuit)
    payload["seed_derivation"] = (
        f"SeedSequence([sha256(circuit)[:4], {stream}]) — a stable key, so the draw "
        "reproduces across processes, and its own stream so it stays off the frozen banks")
    payload["races_per_circuit"] = per_circuit
    return payload


def _circuit_key(circuit: str) -> int:
    """A stable integer per circuit. Python's hash() is salted per process, so a run
    seeded from it could not be reproduced — the one thing a seed derivation must do."""
    import hashlib

    return int.from_bytes(hashlib.sha256(circuit.encode()).digest()[:4], "big")


def _luck(model, venv, banks, cfg, configs_dir, *, smoke: bool) -> dict:
    from senna.env import F1RaceEnv
    from senna.strategy.rollout import run_episode

    reps = 3 if smoke else cfg["m11"]["decision_reps"]
    stream = cfg["m11"]["decision_stream"]
    grids, entropies = {}, []
    for circuit, seeds in banks.items():
        env = F1RaceEnv(circuit, "2026", rival_band="test", configs_dir=configs_dir)
        grid = []
        for seed in seeds:
            row = []
            for rep in range(reps):
                sampled = StochasticSb3Policy(
                    model, venv.normalize_obs,
                    decision_seed=decision_seed(int(seed), rep, stream=stream))
                row.append(run_episode(env, sampled, seed=int(seed)).final_position)
                # how wide the probe was: the share only means something relative to it
                entropies.append(sampled.mean_head_entropy)
            grid.append(row)
        grids[circuit] = grid

    payload = luck_share(grids, cfg=cfg, head_entropies=entropies)
    payload["per_circuit"] = {c: variance_components(g) for c, g in grids.items()}
    payload["decision_reps"] = reps
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="run the F14 metric suite (5.12)")
    parser.add_argument("--only", help=f"comma-separated batteries: {', '.join(_BATTERIES)}")
    parser.add_argument("--smoke", action="store_true",
                        help="two circuits, two seeds — proves the wiring in seconds")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_suite(only=args.only.split(",") if args.only else None, smoke=args.smoke)


if __name__ == "__main__":
    main()
