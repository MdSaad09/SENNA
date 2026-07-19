"""The F08 ablation harness (5.6.3): every arm dry-runs on the tiny profile before any
real hours burn, the arm tag enters the run identity (plan finding 6), the ledger row
is the machine-readable record each run leaves behind, and the W&B id finally reaches
the manifest (finding 5). Gate evaluations are stubbed as in test_run.py — the wiring
is under test here, never the gates.
"""

import json
import re
from pathlib import Path

import pytest
from senna.train.ablate import run_ablation
from senna.train.ledger import RunLedger

from senna import config
from senna.train import run as run_module
from senna.train.gates import GateDecision
from senna.train.run import train_run
from senna.train.seeds import SeedBankReservedError, load_reserved_test_bank
from senna.train.tracking import Tracker, _WandbTracker
from tests.train.conftest import SEED

ARMS = ("no_curriculum", "penalty_constraints", "reward_v2", "terminal_only")

_HEX_FINGERPRINT = re.compile(r"[0-9a-f]{12,64}")


class StubTracker(Tracker):
    def __init__(self, run_id="w-846-stub"):
        self.run_id = run_id


def _never_passing_evaluator(*args, **kwargs):
    def evaluate(*eval_args, **eval_kwargs):
        return GateDecision(passed=False, reason="stub: never passes", values={})

    return evaluate


@pytest.fixture
def stub_gates(monkeypatch):
    monkeypatch.setattr(run_module, "build_evaluator", _never_passing_evaluator)


def _triplet_complete(path):
    return all(
        (path / name).exists() for name in ("model.zip", "vecnormalize.pkl", "manifest.json")
    )


def test_every_ablation_config_dry_runs(tiny_configs, tmp_path, stub_gates):
    models_dir = tmp_path / "models"
    arms = config.load("ablations")["runs"]
    assert set(ARMS) <= set(arms)  # the 5.6.3 matrix, from the yaml and not this test

    for arm in arms:
        run_dir = run_ablation(
            arm, seed=SEED, dry_run=True, vec="dummy", workers=2,
            tracker=StubTracker(), configs_dir=tiny_configs, models_dir=models_dir,
        )
        assert _triplet_complete(run_dir / "stageC" / "final")
        assert (run_dir / "curriculum_gates.json").exists()
        assert run_dir.name in RunLedger(models_dir / "runs.json").rows()


def test_two_arms_same_seed_get_distinct_run_dirs(tiny_configs, tmp_path, stub_gates):
    models_dir = tmp_path / "models"
    run_dirs = {}
    for arm in ("no_curriculum", "terminal_only"):
        run_dirs[arm] = run_ablation(
            arm, seed=SEED, dry_run=True, vec="dummy", workers=2,
            tracker=StubTracker(), configs_dir=tiny_configs, models_dir=models_dir,
        )

    # finding 6: same seed, same day — the arm id must keep the run identities apart
    assert run_dirs["no_curriculum"] != run_dirs["terminal_only"]
    for arm, run_dir in run_dirs.items():
        assert run_dir.name.startswith(f"abl-{arm}-")


def test_ledger_rows_carry_seed_hash_budget_and_wandb_id(tiny_configs, tmp_path, stub_gates):
    models_dir = tmp_path / "models"
    run_dir = run_ablation(
        "no_curriculum", seed=SEED, dry_run=True, vec="dummy", workers=2,
        tracker=StubTracker(run_id="w-846-ledger"), configs_dir=tiny_configs,
        models_dir=models_dir,
    )

    row = RunLedger(models_dir / "runs.json").rows()[run_dir.name]
    assert row["kind"]
    assert row["seed"] == SEED
    assert _HEX_FINGERPRINT.fullmatch(row["fingerprint"])
    assert row["budget_steps"] > 0
    assert row["wandb_run_id"] == "w-846-ledger"
    assert row["status"] == "complete"
    assert row["exit_reason"]


def test_wandb_run_id_reaches_the_manifest(tiny_configs, tmp_path, stub_gates):
    run_dir = train_run(
        seed=SEED, from_stage="A", to_stage="A", workers=2, vec="dummy",
        configs_dir=tiny_configs, tracker=StubTracker(run_id="w-846-test"),
        models_dir=tmp_path / "models",
    )
    manifest = json.loads((run_dir / "stageA" / "final" / "manifest.json").read_text())
    assert manifest["wandb_run_id"] == "w-846-test"

    # finding 5: the wandb tracker must expose the id run.py reads via getattr
    class FakeRun:
        id = "abc"

        def finish(self):
            pass

    assert _WandbTracker(FakeRun()).run_id == "abc"
    assert Tracker().run_id is None


def test_stage_c_fresh_start_requires_the_explicit_flag(tiny_configs, tmp_path, stub_gates):
    with pytest.raises(ValueError, match="resume"):
        train_run(
            seed=SEED, from_stage="C", to_stage="C", workers=2, vec="dummy",
            configs_dir=tiny_configs, tracker=StubTracker(),
            models_dir=tmp_path / "models",
        )

    run_dir = train_run(
        seed=SEED, from_stage="C", to_stage="C", fresh=True, workers=2, vec="dummy",
        configs_dir=tiny_configs, tracker=StubTracker(),
        models_dir=tmp_path / "models",
    )
    assert _triplet_complete(run_dir / "stageC" / "final")


def test_selection_code_cannot_read_the_test_bank():
    # E-06 / E-14 discipline: the test bank refuses the harness, and no F08 module may
    # even name the F14 consumer literal that would unlock it
    with pytest.raises(SeedBankReservedError):
        load_reserved_test_bank(consumer="F08")

    train_pkg = Path(run_module.__file__).resolve().parent
    for module in ("ablate.py", "selection.py", "ledger.py"):
        assert "F14" not in (train_pkg / module).read_text(), module
