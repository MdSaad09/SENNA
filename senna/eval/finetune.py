"""The era-matched Stage C fine-tune (F-24, A-10, OQ-9's default answer).

The counterfactual chapter replays 2023/24 races. Scoring a 2026-physics agent on them
would confound strategy quality with regulation change — the agent would "win" partly
because it drives a different car, and an examiner would rightly ask which effect was
measured. So the same policy is warm-started onto the 2024 constants and it is that model
the counterfactuals run.

The mechanism is F08's overlay trick, not a new training path: copy the configs, rewrite
Stage C's era, circuit list and budget, and hand the directory to the ordinary train_run.
The overlay's bytes are what the fingerprint hashes, so the fine-tuned checkpoint gets a
model_version that cannot collide with the headline's, and the run is self-describing —
the configs it trained under sit beside its weights.

Two choices worth stating. The budget is half the Stage C ceiling because a warm start
adapts a policy to twenty cars, a hundred kilos of fuel and a two-megajoule per-lap budget;
it does not rediscover strategy from nothing. And the circuit list is the 23 with genuine
2024 fits — build_scenario falls back to the 2026 fits for the other two, which would
quietly train an "era-matched" model on the very physics the era match exists to remove.
"""

import logging
import shutil
from pathlib import Path

import yaml

from senna import config

log = logging.getLogger(__name__)

_RUN_TAG = "era2024"


def overlay_configs(*, base_dir, dest, cfg: dict) -> Path:
    """A copy of the configs with Stage C re-pointed at the 2024 world. Everything else is
    byte-identical, so a diff of the overlay is the complete statement of what this run
    changed."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(Path(base_dir), dest)

    finetune = cfg["era_finetune"]
    curriculum = yaml.safe_load((dest / "curriculum.yaml").read_text())
    stage_c = curriculum["stages"]["C"]
    stage_c["era"] = finetune["era"]
    stage_c["circuits"] = list(finetune["circuits"])
    stage_c["budget_steps"] = finetune["budget_steps"]
    stage_c["eval_every_steps"] = finetune["eval_every_steps"]
    (dest / "curriculum.yaml").write_text(yaml.safe_dump(curriculum, sort_keys=False))
    return dest


def run_finetune(*, seed: int | None = None, configs_dir=None, models_dir=None,
                 dry_run: bool = False, wandb_mode: str = "auto",
                 workers: int | None = None, vec: str = "subproc") -> Path:
    """Warm-start the frozen headline onto the 2024 constants and promote the result."""
    from senna.train.ledger import RunLedger, close_run
    from senna.train.run import train_run
    from senna.train.selection import promote_headline, read_candidate

    cfg = config.load("eval", configs_dir)
    finetune = cfg["era_finetune"]
    models = Path(models_dir) if models_dir else config.REPO_ROOT / "models"
    resume = config.REPO_ROOT / finetune["resume"]
    if seed is None:
        seed = _headline_seed(resume)

    overlay = overlay_configs(
        base_dir=Path(configs_dir) if configs_dir else config.REPO_ROOT / "configs",
        dest=models / "overlays" / f"{_RUN_TAG}-s{seed}", cfg=cfg,
    )
    log.info("fine-tuning %s onto era %s for %s steps",
             resume.name, finetune["era"], finetune["budget_steps"])

    run_dir = train_run(
        seed=seed, from_stage="C", to_stage="C", resume=resume, configs_dir=overlay,
        models_dir=models, run_tag=_RUN_TAG, wandb_mode=wandb_mode,
        total_steps=256 if dry_run else None, workers=workers, vec=vec,
        extra_config_files=("eval",),
    )

    candidate = read_candidate(run_dir)
    promotion = promote_headline(candidate, models / "era2024")
    ledger = RunLedger(models / "runs.json")
    close_run(ledger, candidate.run_id, run_dir, stage="C")
    ledger.annotate(candidate.run_id, promoted=True, era=finetune["era"],
                    model_version=promotion["model_version"])
    log.info("promoted %s to models/era2024", promotion["model_version"])
    return run_dir


def _headline_seed(resume: Path) -> int:
    """The fine-tune inherits the seed of the checkpoint it warm-starts from, so its run
    identity names the lineage rather than inventing a new one."""
    import json

    return int(json.loads((resume / "manifest.json").read_text())["seed"])


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="era-matched Stage C fine-tune (F-24)")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="tiny budget: proves the wiring before real hours burn")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--vec", choices=("subproc", "dummy"), default="subproc")
    parser.add_argument("--wandb-mode", default="auto")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_finetune(seed=args.seed, dry_run=args.dry_run, workers=args.workers,
                 vec=args.vec, wandb_mode=args.wandb_mode)


if __name__ == "__main__":
    main()
