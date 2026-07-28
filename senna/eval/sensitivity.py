"""The harvest-cap robustness pass (E-02, Saad's F14 decision 1).

The FIA cut maximum permitted recharge from 8 MJ to 7 MJ in April 2026 (Issue 18 Art
C5.2.10). Every circuit in configs/circuits.yaml still carries the 8.5 MJ baseline the
frozen headline trained under, and correcting it there would desync the fingerprint the
served triplet records and invalidate the whole evaluation chapter. So the newer figure is
exercised here instead, against a throwaway configs overlay that the repository never
keeps.

What this measures, stated once and carried into the report: how the FROZEN agent copes
when the cap tightens. It is not what a model re-optimised for 7 MJ would do. Those are
different questions and only the second one needs a retrain; conflating them would let a
robustness result read as a regulation-compliance claim.

Both arms roll the same seeds, so the comparison is paired by construction — the only
thing that differs between them is the number in the yaml.
"""

import argparse
import logging
import shutil
import tempfile
from pathlib import Path

import yaml

from senna import config
from senna.eval import metrics, record

log = logging.getLogger(__name__)


def overlay_configs(*, base_dir, dest, h_max_mj: float) -> Path:
    """A copy of the configs with every circuit's harvest cap rewritten. Nothing else
    moves, so a diff of the overlay is the complete statement of the counterfactual."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(Path(base_dir), dest)

    circuits_path = dest / "circuits.yaml"
    circuits = yaml.safe_load(circuits_path.read_text())
    for entry in circuits.values():
        entry["h_max_mj"] = float(h_max_mj)
    circuits_path.write_text(yaml.safe_dump(circuits, sort_keys=False))
    return dest


def trained_cap(circuits, configs_dir=None) -> float:
    """The cap the frozen model trained under. AR-05 permits per-event values, so a mixed
    bank has no single "trained cap" to compare against and the arms would be mislabelled
    by whichever circuit happened to be first."""
    circuits_cfg = config.load("circuits", configs_dir)
    caps = {float(config.get(circuits_cfg, f"{circuit}.h_max_mj")) for circuit in circuits}
    if len(caps) != 1:
        raise ValueError(
            f"the bank spans {len(caps)} different harvest caps ({sorted(caps)}) — a "
            "single-number sensitivity comparison would mislabel its own arms; narrow "
            "--circuits to one cap or report per-circuit"
        )
    return caps.pop()


def run_sensitivity(*, configs_dir=None, models_dir=None, circuits=None) -> dict:
    """Roll the frozen agent at the trained cap and the refined one, on the same seeds."""
    from senna.eval.run import load_frozen_policy

    cfg = config.load("eval", configs_dir)
    block = cfg["sensitivity"]["harvest_cap"]
    base_dir = Path(configs_dir) if configs_dir else config.REPO_ROOT / "configs"
    models = Path(models_dir) if models_dir else config.REPO_ROOT / "models"

    policy, _, _, manifest = load_frozen_policy(models / "headline")
    banks = record.test_bank(configs_dir)
    per_circuit = int(block["races_per_circuit"])
    banks = {c: seeds[:per_circuit] for c, seeds in banks.items()
             if circuits is None or c in circuits}
    if not banks:
        raise ValueError(
            f"no circuit in the reserved bank matches {circuits} — nothing to roll"
        )

    baseline_mj = trained_cap(banks, configs_dir)
    arms, dropped = {}, {}
    with tempfile.TemporaryDirectory() as scratch:
        # both arms get an overlay, including the one that reproduces the committed value.
        # Selecting by value would collapse the two into one run the moment a circuit's
        # cap already equalled the refined figure, and the report would print that as a
        # measured null result
        for label, h_max_mj in (("trained", baseline_mj), ("refined", float(block["h_max_mj"]))):
            overlay = overlay_configs(base_dir=base_dir, dest=Path(scratch) / label,
                                      h_max_mj=h_max_mj)
            races, excluded = record.record_eval_races(policy, banks=banks,
                                                       configs_dir=overlay)
            dropped[label] = {(row["circuit"], row["seed"]) for row in excluded}
            energy = metrics.energy_utilisation(
                races, cfg={**cfg["m4"],
                            "intra_lap_share": config.load("env", overlay)["harvest"]
                            ["intra_lap_share"]})
            arms[label] = {
                "h_max_mj": h_max_mj,
                "utilisation": energy["utilisation"],
                "attainable_ceiling": energy["attainable_ceiling"],
                "derate_share": energy["derate_share"],
                "mean_position": sum(r.agent.final_position for r in races) / len(races),
                "failures_per_100": metrics.tyre_failure_rate(races)["failures_per_100"],
                "n_races": len(races),
            }
            log.info("%s cap %.1f MJ: utilisation %.3f, derates %.3f, mean P%.2f",
                     label, h_max_mj, arms[label]["utilisation"],
                     arms[label]["derate_share"], arms[label]["mean_position"])

    # the whole comparison rests on both arms racing the same seeds; a retirement under one
    # cap and not the other would silently make them different experiments
    if dropped["trained"] != dropped["refined"]:
        raise ValueError(
            f"the arms dropped different races (trained {sorted(dropped['trained'])}, "
            f"refined {sorted(dropped['refined'])}) — the comparison is no longer paired"
        )

    return {
        "arms": arms,
        "delta": {
            key: arms["refined"][key] - arms["trained"][key]
            for key in ("utilisation", "derate_share", "mean_position", "failures_per_100")
        },
        "trained_h_max_mj": baseline_mj,
        "refined_h_max_mj": float(block["h_max_mj"]),
        "excluded_races": sorted(dropped["trained"]),
        "n_circuits": len(banks),
        "model_version": manifest["model_version"],
        "reading": (
            f"the frozen agent's robustness under a {block['h_max_mj']} MJ cap, not what a "
            f"model re-optimised for {block['h_max_mj']} MJ would do — the reported numbers "
            f"stay on the {baseline_mj} MJ cap it trained under"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="harvest-cap sensitivity (E-02)")
    parser.add_argument("--circuits", help="comma-separated subset; default is the bank")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from senna.eval import store

    cfg = config.load("eval")
    subset = args.circuits.split(",") if args.circuits else None
    payload = run_sensitivity(circuits=subset)

    # a subset run never lands where the report reads: its rows would carry a full run's
    # provenance and print under a full run's claim, which is the incident the smoke
    # directory already exists to prevent
    committed = config.REPO_ROOT / cfg["store"]["committed_dir"] / ("subset" if subset else "")
    store.write_metric(committed, "harvest_sensitivity", payload, envelope=store.envelope(
        model_versions={"headline": payload["model_version"]},
        config_hash=config.fingerprint(["circuits"]),
        seeds_fingerprint=config.fingerprint(["seeds"]),
        # circuits rolled, not names given: a mistyped --circuits would otherwise inflate
        # the provenance the same way a race count once did
        scope={"smoke": False, "subset": bool(subset), "circuits": payload["n_circuits"],
               "seeds_per_circuit": cfg["sensitivity"]["harvest_cap"]["races_per_circuit"]},
    ))
    log.info("wrote harvest_sensitivity to %s", committed)


if __name__ == "__main__":
    main()
