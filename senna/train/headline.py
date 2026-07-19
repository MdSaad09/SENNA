"""The 3-seed headline (5.6.1): the full A->B->C curriculum per seed, then cross-seed
selection on validation points and promotion to models/headline — the model version
F09 and F10 consume. Completed seeds are skipped via the ledger, so an interrupted
slate resumes where it left off at the cost of re-running one seed.

    make headline                # all three seeds, then select and promote
    make headline SEED=211       # one seed, no selection
"""

import argparse
from pathlib import Path

from senna import config
from senna.train.ledger import RunLedger, close_run
from senna.train.run import CONFIG_FILES, run_identity, train_run
from senna.train.selection import promote_headline, read_candidate, select_headline
from senna.train.tracking import make_tracker


def run_headline_seed(seed: int, *, wandb_mode: str = "auto",
                      workers: int | None = None, vec: str = "subproc",
                      configs_dir=None, models_dir=None, tracker=None) -> Path:
    models_dir = Path(models_dir or config.REPO_ROOT / "models")
    fingerprint = config.fingerprint(CONFIG_FILES, configs_dir)
    run_id = run_identity(seed=seed, fingerprint=fingerprint, run_tag="headline")
    ledger = RunLedger(models_dir / "runs.json")

    existing = ledger.rows().get(run_id)
    if existing and existing["status"] == "complete":
        print(f"headline seed {seed} already complete: {existing['run_dir']}")
        return Path(existing["run_dir"])

    if tracker is None:
        train_cfg = config.load("training", configs_dir)
        tracker = make_tracker(
            mode=wandb_mode, project=train_cfg["tracking"]["project"],
            run_name=f"headline-s{seed}-{fingerprint[:12]}", group=fingerprint[:12],
            config={"seed": seed, "fingerprint": fingerprint},
            tags=["headline"],
        )
    curriculum = config.load("curriculum", configs_dir)
    ledger.record_start(
        run_id=run_id, kind="headline", seed=seed, fingerprint=fingerprint,
        budget_steps=sum(stage["budget_steps"] for stage in curriculum["stages"].values()),
        wandb_run_id=tracker.run_id,
    )
    run_dir = train_run(
        seed=seed, workers=workers, vec=vec, wandb_mode=wandb_mode,
        configs_dir=configs_dir, tracker=tracker, models_dir=models_dir,
        run_tag="headline", run_id=run_id,
    )
    close_run(ledger, run_id, run_dir, stage="C")
    return run_dir


def run_headline(*, wandb_mode: str = "auto", workers: int | None = None,
                 vec: str = "subproc", configs_dir=None, models_dir=None) -> dict:
    models_dir = Path(models_dir or config.REPO_ROOT / "models")
    seeds = config.load("seeds", configs_dir)["train"]["headline"]
    run_dirs = [
        run_headline_seed(seed, wandb_mode=wandb_mode, workers=workers, vec=vec,
                          configs_dir=configs_dir, models_dir=models_dir)
        for seed in seeds
    ]
    chosen = select_headline([read_candidate(run_dir) for run_dir in run_dirs])
    promotion = promote_headline(chosen, models_dir / "headline")
    RunLedger(models_dir / "runs.json").annotate(
        chosen.run_id, promoted=True, model_version=promotion["model_version"],
    )
    print(f"headline: seed {chosen.seed} at step {chosen.step:,} "
          f"({chosen.mean_points:.3f} validation points) -> {models_dir / 'headline'}")
    print(f"model version: {promotion['model_version']}")
    return promotion


def main() -> None:
    parser = argparse.ArgumentParser(
        description="the 3-seed headline: train, select on validation points, promote"
    )
    parser.add_argument("--seed", type=int, default=None,
                        help="run one seed only, skipping selection and promotion")
    parser.add_argument("--wandb-mode", choices=["auto", "online", "offline", "disabled"],
                        default="auto")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--vec", choices=["subproc", "dummy"], default="subproc")
    args = parser.parse_args()

    if args.seed is not None:
        run_dir = run_headline_seed(args.seed, wandb_mode=args.wandb_mode,
                                    workers=args.workers, vec=args.vec)
        print(f"headline seed {args.seed} complete: {run_dir}")
        return
    run_headline(wandb_mode=args.wandb_mode, workers=args.workers, vec=args.vec)


if __name__ == "__main__":
    main()
