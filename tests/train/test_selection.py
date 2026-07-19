"""Cross-seed headline selection and promotion (5.7, extended by the F08 tie-break):
best validation points across the seeds' selected checkpoints, ties to the earlier
global step and then the lower seed, and a promotion that re-verifies the best/
triplet against the gate log before copying (plan finding 7) — models/headline/ is
the artifact F09 and F10 consume.
"""

import json

import pytest
from senna.train.selection import (
    HeadlineCandidate,
    promote_headline,
    read_candidate,
    select_headline,
)


def fabricated_run(models_dir, *, run_id, seed, step, mean_points, best_step=None,
                   model_version=None):
    """A run dir shaped like train_run's output: the gate log's Stage C selection plus
    a best/ triplet whose payload bytes only need to exist. best_step lets a test drift
    the manifest away from the gate log on purpose."""
    run_dir = models_dir / run_id
    best = run_dir / "stageC" / "best"
    best.mkdir(parents=True)
    (run_dir / "curriculum_gates.json").write_text(json.dumps({
        "run_id": run_id,
        "stages": {"C": {"selected_checkpoint": {"step": step, "mean_points": mean_points}}},
    }))
    (best / "manifest.json").write_text(json.dumps({
        "model_version": model_version or f"version-{run_id}",
        "run_id": run_id,
        "seed": seed,
        "global_step": step if best_step is None else best_step,
    }))
    (best / "model.zip").write_bytes(b"model payload")
    (best / "vecnormalize.pkl").write_bytes(b"stats payload")
    return run_dir


def test_headline_selection_takes_the_best_validation_points_across_seeds(tmp_path):
    candidates = [
        read_candidate(fabricated_run(tmp_path, run_id="run-s101", seed=101,
                                      step=3_500_000, mean_points=5.1)),
        read_candidate(fabricated_run(tmp_path, run_id="run-s211", seed=211,
                                      step=3_000_000, mean_points=5.4)),
        read_candidate(fabricated_run(tmp_path, run_id="run-s331", seed=331,
                                      step=2_000_000, mean_points=5.4)),
    ]

    chosen = select_headline(candidates)
    assert chosen.mean_points == 5.4
    assert chosen.step == 2_000_000  # tie on points goes to the earlier step
    assert chosen.seed == 331

    # tie on points and step as well: the lower seed wins (the documented last resort)
    rerun = read_candidate(fabricated_run(tmp_path, run_id="run-s101-rerun", seed=101,
                                          step=2_000_000, mean_points=5.4))
    assert select_headline([*candidates, rerun]).seed == 101


def test_promotion_refuses_a_best_triplet_that_mismatches_the_gate_log(tmp_path):
    # finding 7: best/ equals the recorded selection only by a fragile coupling today,
    # so promotion asserts the manifest's global step against the gate log's
    drifted = fabricated_run(tmp_path, run_id="run-drift", seed=101, step=500,
                             mean_points=5.0, best_step=999)
    candidate = HeadlineCandidate(run_dir=drifted, run_id="run-drift", seed=101,
                                  step=500, mean_points=5.0)
    with pytest.raises(RuntimeError):
        promote_headline(candidate, tmp_path / "headline")
    assert not (tmp_path / "headline" / "model.zip").exists()  # nothing half-promoted

    clean = fabricated_run(tmp_path, run_id="run-clean", seed=211, step=750,
                           mean_points=5.5, model_version="mppo-abc-C-750")
    promoted = promote_headline(read_candidate(clean), tmp_path / "headline")

    dest = tmp_path / "headline"
    assert (dest / "model.zip").read_bytes() == b"model payload"
    assert (dest / "vecnormalize.pkl").read_bytes() == b"stats payload"
    manifest = json.loads((dest / "manifest.json").read_text())
    assert manifest["model_version"] == "mppo-abc-C-750"
    assert promoted["model_version"] == "mppo-abc-C-750"
    assert promoted["run_id"] == "run-clean"
    assert promoted["seed"] == 211
    assert promoted["step"] == 750
    assert promoted["mean_points"] == 5.5
