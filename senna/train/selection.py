"""Cross-seed headline selection and promotion (5.7, extended by the F08 tie-break):
highest validation points across the seeds' selected checkpoints, ties to the earlier
global step — same measured quality, less opportunity to overfit the validation bank —
and then the lower seed, the documented last resort. Promotion re-verifies the best/
triplet against the gate log before copying: the coupling that makes best/ the
selected checkpoint holds only while min_improvement_points is zero, so trusting it
silently would be a latent bug. models/headline/ is the artifact F09 and F10 consume.

    make eval RUN=models/<run_dir>     # re-score a run's selected checkpoint
"""

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class HeadlineCandidate:
    run_dir: Path
    run_id: str
    seed: int
    step: int
    mean_points: float


def read_candidate(run_dir: Path) -> HeadlineCandidate:
    run_dir = Path(run_dir)
    gates = json.loads((run_dir / "curriculum_gates.json").read_text())
    selected = gates["stages"].get("C", {}).get("selected_checkpoint")
    if not selected:
        raise ValueError(f"{run_dir}: no stage C selection recorded — did the run "
                         "reach an evaluation before stopping?")
    manifest = json.loads((run_dir / "stageC" / "best" / "manifest.json").read_text())
    return HeadlineCandidate(
        run_dir=run_dir, run_id=gates["run_id"], seed=int(manifest["seed"]),
        step=int(selected["step"]), mean_points=float(selected["mean_points"]),
    )


def select_headline(candidates) -> HeadlineCandidate:
    if not candidates:
        raise ValueError("no headline candidates to select from")
    return max(candidates, key=lambda c: (c.mean_points, -c.step, -c.seed))


def promote_headline(candidate: HeadlineCandidate, dest: Path) -> dict:
    best = candidate.run_dir / "stageC" / "best"
    manifest = json.loads((best / "manifest.json").read_text())
    if int(manifest["global_step"]) != candidate.step:
        raise RuntimeError(
            f"{best}: manifest global_step {manifest['global_step']} does not match "
            f"the gate log's selected step {candidate.step} — best/ is not the "
            "selected checkpoint, refusing to promote"
        )
    promotion = {
        "model_version": manifest["model_version"],
        "run_id": candidate.run_id,
        "seed": candidate.seed,
        "step": candidate.step,
        "mean_points": candidate.mean_points,
        "promoted_at": datetime.now(UTC).isoformat(),
    }
    # the checkpoints.py swap: the destination is never observable half-promoted
    dest = Path(dest)
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(best, tmp)
    (tmp / "promotion.json").write_text(json.dumps(promotion, indent=2))
    if dest.exists():
        stale = dest.with_name(dest.name + ".stale")
        if stale.exists():
            shutil.rmtree(stale)
        os.replace(dest, stale)
        os.replace(tmp, dest)
        shutil.rmtree(stale)
    else:
        os.replace(tmp, dest)
    return promotion


def score_triplet(triplet_dir: Path, *, configs_dir=None) -> float:
    """Re-score a saved triplet on the validation banks — the make eval path. One
    throwaway env provides the spaces, the frozen statistics come from the triplet,
    and the bank is rolled exactly as a Stage C gate evaluation would (E-06: train
    band; the test bank stays reserved)."""
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    from senna.env import F1RaceEnv
    from senna.train.checkpoints import load_triplet
    from senna.train.evals import Sb3Policy, run_stage_c_eval
    from senna.train.seeds import load_banks

    banks = load_banks(configs_dir)
    circuit = next(iter(banks.stage_c_validation))
    venv = DummyVecEnv([lambda: Monitor(F1RaceEnv(circuit, "2026", configs_dir=configs_dir))])
    model, loaded = load_triplet(Path(triplet_dir), venv)
    policy = Sb3Policy(model, loaded.normalize_obs)
    return run_stage_c_eval(policy, step=0, banks=banks.stage_c_validation,
                            configs_dir=configs_dir).mean_points


def main() -> None:
    parser = argparse.ArgumentParser(
        description="re-score a run's selected checkpoint on the validation banks"
    )
    parser.add_argument("--rescore", type=Path, required=True, metavar="RUN_DIR",
                        help="a models/<run> dir with a stage C selection")
    args = parser.parse_args()

    candidate = read_candidate(args.rescore)
    rescored = score_triplet(candidate.run_dir / "stageC" / "best")
    print(f"{candidate.run_id}: recorded {candidate.mean_points:.3f} points at step "
          f"{candidate.step:,}; rescored {rescored:.3f}")
    ledger_path = args.rescore.parent / "runs.json"
    if ledger_path.exists():
        from senna.train.ledger import RunLedger

        RunLedger(ledger_path).annotate(candidate.run_id, rescored_points=rescored)
        print(f"ledger updated: {ledger_path}")


if __name__ == "__main__":
    main()
