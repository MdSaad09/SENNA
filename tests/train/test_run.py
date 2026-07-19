"""The stage loop end to end (5.6.1, 5.7, R-12): a stubbed-gate wiring smoke on tiny
configs, the real Stage A smoke, and the F-26 wandb import discipline.
"""

import json
import re
from pathlib import Path

import pytest

import senna
from senna.train import run as run_module
from senna.train.gates import GateDecision
from senna.train.run import train_run
from senna.train.tracking import Tracker
from tests.train.conftest import SEED

EXPECTED_SERIES = {
    "rollout/ep_rew_mean",
    "rollout/ep_len_mean",
    "train/approx_kl",
    "train/clip_fraction",
    "train/entropy_loss",
    "train/value_loss",
    "train/policy_gradient_loss",
    "train/loss",
    "train/explained_variance",
    "train/learning_rate",
    "train/ent_coef",
    "reward/pace_ep_mean",
    "reward/position_ep_mean",
    "reward/terminal_ep_mean",
    "reward/dominance_ratio",
    "perf/steps_s",
    "curriculum/stage",
    "gate/passed",
}

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_WANDB_IMPORT = re.compile(r"^\s*(import wandb\b|from wandb\b)", re.MULTILINE)


class RecordingTracker(Tracker):
    def __init__(self):
        self.series_seen = set()
        self.summary = {}
        self.finished = False

    def log(self, series, *, step):
        self.series_seen |= set(series)

    def set_summary(self, mapping):
        self.summary.update(mapping)

    def finish(self):
        self.finished = True


def _triplet_complete(path):
    return all(
        (path / name).exists() for name in ("model.zip", "vecnormalize.pkl", "manifest.json")
    )


def test_wiring_smoke(tiny_configs, tmp_path, monkeypatch):
    decisions = iter([
        GateDecision(passed=False, reason="stub: warm-up", values={}),
        GateDecision(passed=True, reason="stub: pass", values={}),
    ])

    def stub_build_evaluator(*args, **kwargs):
        def evaluate(*eval_args, **eval_kwargs):
            return next(decisions, GateDecision(passed=True, reason="stub: pass", values={}))

        return evaluate

    monkeypatch.setattr(run_module, "build_evaluator", stub_build_evaluator)
    tracker = RecordingTracker()

    run_dir = train_run(
        seed=SEED, from_stage="A", to_stage="A", workers=2, vec="dummy",
        wandb_mode="disabled", configs_dir=tiny_configs, tracker=tracker,
        models_dir=tmp_path / "models",
    )

    assert run_dir.is_dir()
    assert _triplet_complete(run_dir / "stageA" / "last")
    assert _triplet_complete(run_dir / "stageA" / "final")

    manifest = json.loads((run_dir / "stageA" / "final" / "manifest.json").read_text())
    assert manifest["fingerprint"]
    assert _SHA256_HEX.match(manifest["model_zip_sha256"])
    assert _SHA256_HEX.match(manifest["vecnormalize_sha256"])

    missing = EXPECTED_SERIES - tracker.series_seen
    assert not missing, f"series never logged: {sorted(missing)}"
    assert tracker.finished


@pytest.mark.slow
def test_stage_a_smoke_5k(tmp_path):
    run_dir = train_run(
        seed=SEED, from_stage="A", to_stage="A", total_steps=5000, workers=2,
        vec="dummy", wandb_mode="disabled", models_dir=tmp_path / "models",
    )

    # too few steps to reach the eval cadence, so this pins the stage-exit eval:
    # a real gate evaluation ran and was logged before the run wound down
    gate_log = json.loads((run_dir / "curriculum_gates.json").read_text())
    assert gate_log["stages"]["A"]["evals"]
    assert _triplet_complete(run_dir / "stageA" / "final")


def test_wandb_is_imported_only_in_tracking():
    # F-26: one import site, training-side only — the fastf1-under-data rule's sibling
    package_root = Path(senna.__file__).resolve().parent
    importers = sorted(
        str(path.relative_to(package_root))
        for path in package_root.rglob("*.py")
        if _WANDB_IMPORT.search(path.read_text())
    )
    assert importers == ["train/tracking.py"]
