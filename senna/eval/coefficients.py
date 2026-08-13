"""The M2 energy-coefficient sensitivity (F15; eval.yaml's sensitivity.energy_coefficients
key carried "no reader yet" from F14 until here).

The 2024 counterfactual scenario borrows the 2026 energy-mode fit — conserve cost, attack
gain, derate penalty and the attack SOC floor (senna/env/scenario.py) — because no 2024
fit of those coefficients exists. That borrow is M2's stated assumption, and this module
prices it: the ten frozen races re-roll with the borrowed block at +/-50%, as a pair of
throwaway config overlays in the harvest study's mould (senna/eval/sensitivity.py). If M2
moves less than its own spread, "borrowed from the 2026 fit" is a documented coarseness;
if it moves more, the borrow is load-bearing and the write-up must say so.

Era-matched only: the borrow exists in the 2024 scenario, so pricing it with the 2026
headline would perturb coefficients that model actually trained on — a different
experiment. The run therefore refuses to fall back when models/era2024 is absent.
"""

import argparse
import logging
import shutil
import tempfile
from pathlib import Path

import yaml

from senna import config
from senna.eval import store

log = logging.getLogger(__name__)

# the energy-mode block scenario.py borrows for the 2024 era; dirty_air_threshold_s
# stays out — it is the sourced 5.5.3 traffic constant, not part of the borrowed fit
BORROWED = (
    "conserve_pace_cost_s_per_mj",
    "attack_pace_gain_s",
    "derate_penalty_s_per_mj",
    "attack_soc_floor_mj",
)

# every config the M2 roll reads: the perturbed file first, then the era constants,
# the circuit bank and the race list. The envelope hashes the base files — the two
# per-arm overlays could never share one hash, and the perturbation is in the payload
# drivers is here and not in train.CONFIG_FILES for the reason that file gives: a lineup
# is read only by a run that names one, and M2 names one for every race (F17). Leaving it
# out would let the seat pace change the number without changing the hash that claims to
# identify the inputs.
M2_CONFIG_FILES = ["physics_2026", "physics_2024", "circuits", "eval", "drivers"]


def build_overlays(*, base_configs_dir, tmp_root, perturbation: float) -> dict:
    """Two throwaway config trees, the borrowed block scaled by (1 +/- perturbation) and
    nothing else moved — a diff of an overlay is the complete statement of its arm."""
    overlays = {}
    for label, factor in (("up", 1 + perturbation), ("down", 1 - perturbation)):
        dest = Path(tmp_root) / label
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(Path(base_configs_dir), dest)

        physics_path = dest / "physics_2026.yaml"
        physics = yaml.safe_load(physics_path.read_text())
        for key in BORROWED:
            physics["fitted"][key] = float(physics["fitted"][key]) * factor
        physics_path.write_text(yaml.safe_dump(physics, sort_keys=False))
        overlays[label] = dest
    return overlays


def write_m2_sensitivity(store_dir, *, arms: dict, dropped: dict, perturbation: float,
                         model_version: str) -> Path:
    """The committed row the report reads. The paired guard runs before a byte lands:
    arms that lost different races are different experiments, and a row written anyway
    would print under a paired claim (the harvest study's discipline, inherited)."""
    if dropped["up"] != dropped["down"]:
        raise ValueError(
            f"the arms dropped different races (up {dropped['up']}, down "
            f"{dropped['down']}) — the comparison is no longer paired"
        )
    payload = {
        "perturbation": perturbation,
        "coefficients": list(BORROWED),
        "arms": arms,
        "dropped_races": dropped["up"],
        "reading": (
            f"the borrowed 2026 energy-mode fit scaled by +/-{perturbation:.0%} under the "
            "era-matched model — how much of M2 rides on coefficients the 2024 era never "
            "fitted, not a claim about either era's true physics"
        ),
    }
    return store.write_metric(store_dir, "m2_sensitivity", payload, envelope=store.envelope(
        model_versions={"era2024": model_version},
        # the run's whole config preimage, not just the mutated file: the M2 roll also
        # reads the race list, the 2024 era constants and the circuit bank (review, F15)
        config_hash=config.fingerprint(M2_CONFIG_FILES),
        seeds_fingerprint=config.fingerprint(["seeds"]),
        scope={"races": min(arm["n_races"] for arm in arms.values()),
               "arms": sorted(arms)},
    ))


def run_coefficient_sensitivity(*, configs_dir=None, models_dir=None) -> dict:
    """Roll the ten M2 races per arm. Needs the ingested Postgres store (the harness
    reads real laps, weather and grids) and models/era2024 — local only, never CI."""
    import asyncio

    from senna.data.db import database_url, engine_for
    from senna.eval import harness
    from senna.eval.run import load_frozen_policy

    cfg = config.load("eval", configs_dir)
    perturbation = float(cfg["sensitivity"]["energy_coefficients"]["perturbation"])
    era = cfg["era_finetune"]["era"]
    base_dir = Path(configs_dir) if configs_dir else config.REPO_ROOT / "configs"
    models = Path(models_dir) if models_dir else config.REPO_ROOT / "models"

    triplet = models / "era2024"
    if not triplet.exists():
        raise FileNotFoundError(
            "no era-matched triplet under models/era2024 — run make finetune first; "
            "perturbing the borrow under the 2026 headline is a different experiment"
        )
    policy, _, _, manifest = load_frozen_policy(triplet)

    async def gather(overlay) -> tuple[list, list]:
        engine = engine_for(database_url())
        rows, lost = [], []
        try:
            async with engine.connect() as conn:
                for race_cfg in cfg["m2"]["races"]:
                    identity = [race_cfg["season"], race_cfg["circuit"], race_cfg["driver"]]
                    try:
                        inputs = await harness.load_race(
                            conn, season=race_cfg["season"], round_number=race_cfg["round"])
                    except LookupError as err:
                        log.warning("dropped %s: %s", identity, err)
                        lost.append(identity)
                        continue
                    rows.append(harness.run_counterfactual(
                        race_cfg, inputs, policy=policy, era=era, cfg=cfg,
                        configs_dir=overlay))
        finally:
            await engine.dispose()
        return rows, lost

    arms, dropped = {}, {}
    with tempfile.TemporaryDirectory() as scratch:
        overlays = build_overlays(base_configs_dir=base_dir, tmp_root=scratch,
                                  perturbation=perturbation)
        for label, overlay in overlays.items():
            rows, lost = asyncio.run(gather(overlay))
            arms[label] = harness.summarise(rows, cfg=cfg)
            dropped[label] = lost
            log.info("%s arm: mean delta %+.2f over %d races",
                     label, arms[label]["mean_delta"], arms[label]["n_races"])

    return {"arms": arms, "dropped": dropped, "perturbation": perturbation,
            "model_version": manifest["model_version"]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M2 energy-coefficient sensitivity (the F14-deferred reader)")
    parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = config.load("eval")
    result = run_coefficient_sensitivity()
    committed = config.REPO_ROOT / cfg["store"]["committed_dir"]
    path = write_m2_sensitivity(
        committed, arms=result["arms"], dropped=result["dropped"],
        perturbation=result["perturbation"], model_version=result["model_version"])
    log.info("wrote %s", path)


if __name__ == "__main__":
    main()
