"""The 5.6.3 ablation harness: every arm runs Stage C from scratch at the 4M ceiling,
through the same train_run loop as the headline, via a deterministic overlay of the
configs — the arm's env overrides and budget written into stage C, so each arm's
fingerprint describes exactly the world it trained in. Same repo configs and same arm
always produce the same overlay bytes; the overlay is a derived artifact (comments do
not survive the round-trip), never the source of truth.

    make ablate RUN=penalty_constraints SEED=101
    make ablate RUN=reward_v2 DRY=1          # prove the wiring before real hours
"""

import argparse
import shutil
from pathlib import Path

import yaml

from senna import config
from senna.train.ledger import RunLedger, close_run
from senna.train.run import CONFIG_FILES, run_identity, train_run
from senna.train.tracking import make_tracker


def overlay_configs(arm: str, *, base_dir: Path, dest: Path, dry_run: bool) -> Path:
    ablations = yaml.safe_load((base_dir / "ablations.yaml").read_text())
    if arm not in ablations["runs"]:
        raise KeyError(f"unknown ablation arm '{arm}' — ablations.yaml defines: "
                       f"{', '.join(ablations['runs'])}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(base_dir, dest)

    curriculum_path = dest / "curriculum.yaml"
    curriculum = yaml.safe_load(curriculum_path.read_text())
    stage_c = curriculum["stages"]["C"]
    stage_c["env"].update(ablations["runs"][arm].get("env", {}))
    stage_c["budget_steps"] = ablations["budget_steps"]
    stage_c["eval_every_steps"] = ablations["eval_every_steps"]
    if dry_run:
        tiny = ablations["dry_run"]
        stage_c["budget_steps"] = tiny["budget_steps"]
        stage_c["eval_every_steps"] = tiny["eval_every_steps"]
        training_path = dest / "training.yaml"
        training = yaml.safe_load(training_path.read_text())
        training["ppo"]["n_steps"] = tiny["n_steps"]
        training["ppo"]["batch_size"] = tiny["batch_size"]
        training_path.write_text(yaml.safe_dump(training))
    curriculum_path.write_text(yaml.safe_dump(curriculum))
    return dest


def run_ablation(arm: str, *, seed: int, dry_run: bool = False,
                 wandb_mode: str = "auto", workers: int | None = None,
                 vec: str = "subproc", configs_dir=None, models_dir=None,
                 tracker=None) -> Path:
    base_dir = Path(configs_dir or config.REPO_ROOT / "configs")
    models_dir = Path(models_dir or config.REPO_ROOT / "models")
    # keyed by arm AND seed so the two seeds of one arm can never rebuild an
    # overlay out from under a live run
    overlay = overlay_configs(arm, base_dir=base_dir,
                              dest=models_dir / "overlays" / f"{arm}-s{seed}",
                              dry_run=dry_run)

    # the same fingerprint train_run will compute from the overlay, needed early so
    # the ledger row exists while the run is live
    fingerprint = config.fingerprint([*CONFIG_FILES, "ablations"], overlay)
    run_tag = f"abl-{arm}"
    run_id = run_identity(seed=seed, fingerprint=fingerprint, run_tag=run_tag)
    if tracker is None:
        train_cfg = config.load("training", overlay)
        tracker = make_tracker(
            mode=wandb_mode, project=train_cfg["tracking"]["project"],
            run_name=f"{run_tag}-s{seed}-{fingerprint[:12]}", group=fingerprint[:12],
            config={"arm": arm, "seed": seed, "fingerprint": fingerprint},
            tags=["ablation", arm],
        )

    ledger = RunLedger(models_dir / "runs.json")
    ledger.record_start(
        run_id=run_id, kind=f"ablation:{arm}", seed=seed, fingerprint=fingerprint,
        budget_steps=config.load("curriculum", overlay)["stages"]["C"]["budget_steps"],
        wandb_run_id=tracker.run_id,
    )
    run_dir = train_run(
        seed=seed, from_stage="C", to_stage="C", fresh=True, workers=workers, vec=vec,
        wandb_mode=wandb_mode, configs_dir=overlay, tracker=tracker,
        models_dir=models_dir, run_tag=run_tag, run_id=run_id,
        extra_config_files=("ablations",),
    )
    close_run(ledger, run_id, run_dir, stage="C")
    return run_dir


def main() -> None:
    ablation_seeds = config.load("seeds")["train"]["ablation"]
    parser = argparse.ArgumentParser(description="run one 5.6.3 ablation arm (F08)")
    parser.add_argument("--run", required=True, help="arm id from ablations.yaml runs")
    parser.add_argument("--seed", type=int, default=ablation_seeds[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="tiny profile: prove the wiring, not the science")
    parser.add_argument("--wandb-mode", choices=["auto", "online", "offline", "disabled"],
                        default="auto")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--vec", choices=["subproc", "dummy"], default="subproc")
    args = parser.parse_args()

    run_dir = run_ablation(
        args.run, seed=args.seed, dry_run=args.dry_run, wandb_mode=args.wandb_mode,
        workers=args.workers, vec=args.vec,
    )
    print(f"ablation {args.run} (seed {args.seed}) complete: {run_dir}")


if __name__ == "__main__":
    main()
